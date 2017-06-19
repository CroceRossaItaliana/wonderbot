from django.db import models

import staging.cmd as cmd
from staging.github import github_finished, github_pending
from staging.utils import random_username, random_password
from staging.validators import validate_environment_name
from wonderbot.settings import DEFAULT_REPOSITORY_URL, DEFAULT_BRANCH, HIGH_LEVEL_DOMAIN, UWSGI_SOCKETS_PATH, \
    NGINX_ROOTS, DB_DUMP_FILENAME, DB_DUMP_WORKERS


class Environment(models.Model):

    # Status constants
    CREATING = 'creating'
    ACTIVE = 'active'
    UPDATING = 'updating'
    REFRESHING = 'refresing'
    DELETING = 'deleting'
    STATUS = ((CREATING, "Creating"),
              (ACTIVE, "Active"),
              (UPDATING, "Updating"),
              (REFRESHING, "Refreshing"),
              (DELETING, "Deleting"))
    
    # Protocol constants
    HTTP = "http"
    HTTPS = "https"
    PROTOCOL = ((HTTP, "HTTP"),
                (HTTPS, "HTTPS (SSL)"))

    # Model fields
    name = models.CharField(validators=[validate_environment_name], db_index=True, unique=True, max_length=64)
    status = models.CharField(choices=STATUS, default=CREATING, blank=False, null=False, max_length=16)
    repository = models.CharField(blank=False, null=False, default=DEFAULT_REPOSITORY_URL, max_length=64)
    branch = models.CharField(blank=False, null=False, default=DEFAULT_BRANCH, max_length=64)
    sha = models.CharField(blank=True, max_length=40)
    protocol = models.CharField(blank=False, null=False, default=HTTP, choices=PROTOCOL, max_length=8)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    # Database info
    db_name = models.CharField(blank=True, null=True, max_length=64)
    db_user = models.CharField(blank=True, null=True, max_length=64)
    db_pass = models.CharField(blank=True, null=True, max_length=64)

    @property
    def short_sha(self):
        return self.sha[:8]

    def host(self):
        return "%s.%s" % (self.name, HIGH_LEVEL_DOMAIN)

    def url(self):
        return "%s://%s" % (self.protocol, self.host())
    
    def __str__(self):
        return "%s (%s, %s)" % (self.name, self.protocol, self.get_status_display())

    def queue_for_creation(self):
        self.status = self.CREATING
        self.save()
        from wonderbot.celery import environment_create
        environment_create.delay(self)

    def queue_for_recreation(self):
        self.status = self.CREATING
        self.save()
        from wonderbot.celery import environment_recreate
        environment_recreate.delay(self)

    def queue_for_deletion(self):
        self.status = self.DELETING
        self.save()
        from wonderbot.celery import environment_delete
        environment_delete.delay(self)

    def queue_for_update(self):
        self.status = self.UPDATING
        self.save()
        from wonderbot.celery import environment_update
        environment_update.delay(self)

    def queue_for_refresh(self):
        self.status = self.REFRESHING
        self.save()
        from wonderbot.celery import environment_refresh
        environment_refresh.delay(self)

    def do_creation(self):
        github_pending(self.sha)
        self._git_clone()
        self._python_venv_setup()
        self._database_create()
        self._jorvik_configure()
        self._django_apply_migrations()
        self._django_collect_static()
        self._uwsgi_touch()
        self.status = self.ACTIVE
        self.save()
        github_finished(self)

    def do_refresh(self):
        self._database_refresh()
        self._jorvik_configure()
        self._django_apply_migrations()
        self._uwsgi_touch()
        self.status = self.ACTIVE
        self.save()

    def do_update(self):
        github_pending(self.sha)
        self._git_pull()
        self._django_collect_static()
        self.do_refresh()
        github_finished(self)

    def do_delete(self, delete_object=True):
        self._nginx_delete()
        self._database_delete()
        if delete_object:
            self.delete()

    def _nginx_delete(self):
        self._delete_nginx_root()

    def _git_clone(self):
        cmd.bash_execute("git clone -b %s %s %s" % (self.branch, self.repository, self.name),
                         cwd=NGINX_ROOTS)

    def _git_pull(self):
        cmd.bash_execute("git pull",
                         cwd=self._get_nginx_root())

    def _python_venv_setup(self):
        cmd.bash_execute("python3 -m virtualenv -ppython3 .venv", cwd=self._get_nginx_root())
        cmd.bash_execute("pip install -r requirements.txt", cwd=self._get_nginx_root(), venv=".venv")

    def _database_create(self):
        self._postgres_generate_credentials()
        self._postgres_cmd("CREATE USER %s WITH PASSWORD '%s';" % (self.db_user, self.db_pass))
        self._postgres_cmd("CREATE DATABASE %s OWNER %s;" % (self.db_name, self.db_user))
        self._postgres_cmd("GRANT ALL PRIVILEGES ON DATABASE %s TO %s;" % (self.db_name, self.db_user))
        self._postgres_cmd("GRANT ALL PRIVILEGES ON DATABASE %s TO %s;" % (self.db_name, "staging"))
        self._postgres_import_dump()

    def _postgres_import_dump(self):
        cmd.bash_execute("pg_restore -Fc -d %s -U %s -j %d --no-owner --no-privileges %s" % (
                         self.db_name, "staging",
                         DB_DUMP_WORKERS, DB_DUMP_FILENAME))
        self._postgres_cmd("GRANT ALL PRIVILEGES ON DATABASE %s TO %s;" % (self.db_name, self.db_user))
        self._postgres_cmd("ALTER DATABASE %s OWNER TO %s;" % (self.db_name, self.db_user))
        self._postgres_cmd("ALTER SCHEMA public OWNER TO %s;" % (self.db_user,), database=self.db_name)
        self._postgres_cmd("ALTER SCHEMA information_schema OWNER TO %s;" % (self.db_user,), database=self.db_name)
        self._postgres_cmd("GRANT ALL ON ALL TABLES IN SCHEMA public TO %s;" % (self.db_user,), database=self.db_name)
        self._postgres_cmd("GRANT ALL ON ALL TABLES IN SCHEMA information_schema TO %s;" % (self.db_user,), database=self.db_name)
        self._postgres_cmd("GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO %s;" % (self.db_user,), database=self.db_name)
        self._postgres_cmd("GRANT ALL ON ALL SEQUENCES IN SCHEMA information_schema TO %s;" % (self.db_user,), database=self.db_name)
        self._postgres_cmd("GRANT ALL ON ALL FUNCTIONS IN SCHEMA public TO %s;" % (self.db_user,), database=self.db_name)
        self._postgres_cmd("GRANT ALL ON ALL FUNCTIONS IN SCHEMA information_schema TO %s;" % (self.db_user,), database=self.db_name)
        # Generate ALTER TABLE ... OWNER TO query for each of the tables in the 'public' schema
        cmd.bash_execute("psql %s -c \"SELECT 'ALTER TABLE '|| schemaname || '.' || tablename ||' OWNER TO %s;' "
                                      "FROM pg_tables WHERE NOT schemaname IN ('pg_catalog', 'information_schema') "    
                                      "ORDER BY schemaname, tablename;\" "
                         "| cat | grep \"ALTER TABLE\" | "
                         "psql %s" % (self.db_name, self.db_user, self.db_name))
        # Run VACUUM commands to optimise space utilisation
        self._postgres_cmd("VACUUM;", database=self.db_name)
        self._postgres_cmd("VACUUM FULL;", database=self.db_name)

    def _database_delete(self):
        if not self.db_user:
            return
        self._postgres_cmd("REVOKE ALL ON DATABASE %s FROM %s;" % (self.db_name, self.db_user))
        self._postgres_restart()
        self._postgres_cmd("DROP DATABASE %s;" % (self.db_name,))
        self._postgres_cmd("DROP USER %s;" % (self.db_user,))
        # Make sure to free up disk space immediately
        self._postgres_cmd("VACUUM;")
        self._postgres_cmd("VACUUM FULL;")


    def _jorvik_configure(self):
        # Write database configuration
        database = "[client]\n" \
                   "host = localhost\n" \
                   "port = 5432\n" \
                   "database = %(db_name)s\n" \
                   "user = %(db_user)s\n" \
                   "password = %(db_pass)s\n" % {
            "db_name": self.db_name, "db_user": self.db_user,
            "db_pass": self.db_pass
        }
        cmd.file_write("%s/config/pgsql.cnf" % self._get_nginx_root(),
                       database)

        # Write media configuration
        media = "[media]\n" \
                "media_root = %(root)s/media/\n" \
                "media_url = /media/\n" \
                "[static]\n" \
                "static_root = %(root)s/static/\n" \
                "static_url = /static/\n" % {"root": self._get_nginx_root()}
        cmd.file_write("%s/config/media.cnf" % self._get_nginx_root(), media)

        # Write uwsgi.ini file
        uwsgi_ini = "[uwsgi]\n" \
                    "plugins = python3\n" \
                    "module = jorvik.wsgi:application\n" \
                    "virtualenv = %d/.venv\n" \
                    "chdir = %d\n" \
                    "processes = 4\n" \
                    "threads = 2\n" \
                    "vacuum = True\n"
        cmd.file_write("%s/uwsgi.ini" % self._get_nginx_root(), uwsgi_ini)

    def _uwsgi_touch(self):
        cmd.bash_execute("touch uwsgi.ini", cwd=self._get_nginx_root())

    def _database_refresh(self):
        self._database_delete()
        self._database_create()

    def _django_cmd(self, command):
        return cmd.bash_execute("DJANGO_SETTINGS_MODULE=jorvik.settings python manage.py %s" % command,
                                cwd=self._get_nginx_root(), venv=".venv")

    def _postgres_cmd(self, command, user="staging", password=None, database="staging"):
        if password:
            command = "PGPASSWORD=%s %s" % (password, command)
        command = "psql -U %s %s -c \"%s\"" % (user, database, command)
        return cmd.bash_execute(command)

    def _postgres_generate_credentials(self):
        username = random_username(8)
        self.db_name = "staging_%s" % username
        self.db_user = "staging_%s" % username
        self.db_pass = random_password(24)
        self.save()

    def _postgres_stop(self):
        cmd.bash_execute("/usr/bin/sudo /staging/scripts/postgres_stop.sh")

    def _postgres_start(self):
        cmd.bash_execute("/usr/bin/sudo /staging/scripts/postgres_start.sh")

    def _postgres_restart(self):
        self._postgres_stop()
        self._postgres_start()

    def _django_apply_migrations(self):
        self._django_cmd("migrate --noinput")

    def _django_collect_static(self):
        self._django_cmd("collectstatic --noinput")

    def _get_nginx_root(self):
        return "%s/%s" % (NGINX_ROOTS, self.name)

    def _get_nginx_static(self):
        return "%s/static" % (self._get_nginx_root(),)

    def _delete_nginx_root(self):
        cmd.dir_delete(self._get_nginx_root())

    def _create_nginx_root(self):
        self._delete_nginx_root()
        cmd.dir_create(self._get_nginx_root())

    def _create_nginx_static(self):
        cmd.dir_create(self._get_nginx_static())

    def get_display_class(self):
        return {self.ACTIVE: "",
                self.CREATING: "warning",
                self.DELETING: "error danger",
                self.UPDATING: "warning",
                self.REFRESHING: "warning",}[self.status]


class AllowedRepository(models.Model):
    url = models.CharField(blank=False, null=False, max_length=128, db_index=True, unique=True)
    allowed_by = models.CharField(blank=False, null=False, max_length=128)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
