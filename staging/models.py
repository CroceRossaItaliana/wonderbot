from django.db import models

import staging.cmd as cmd
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
        self._git_clone()
        self._python_venv_setup()
        self._database_create()
        self._django_apply_migrations()
        self._django_collect_static()
        self._jorvik_configure()
        self._uwsgi_touch()
        self.status = self.ACTIVE
        self.save()

    def do_refresh(self):
        self._database_refresh()
        self._django_apply_migrations()
        self._uwsgi_touch()
        self.status = self.ACTIVE
        self.save()

    def do_update(self):
        self._git_pull()
        self._django_collect_static()
        self.do_refresh()

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
        self._postgres_cmd("CREATE DATABASE %s;" % self.db_name)
        self._postgres_cmd("CREATE USER %s WITH PASSWORD '%s';" % (self.db_user, self.db_pass))
        self._postgres_cmd("GRANT ALL PRIVILEGES ON DATABASE %s TO %s;" % (self.db_name, self.db_user))
        self._postgres_cmd("GRANT ALL PRIVILEGES ON DATABASE %s TO %s;" % (self.db_name, "staging"))
        self._postgres_cmd("FLUSH PRIVILEGES;")
        self._postgres_import_dump()

    def _postgres_import_dump(self):
        cmd.bash_execute("pg_restore -d %s -U %s -j %d %s" % (
                         self.db_name, "staging",
                         DB_DUMP_WORKERS, DB_DUMP_FILENAME))

    def _database_delete(self):
        if not self.db_user:
            return
        self._postgres_cmd("REVOKE ALL ON DATABASE %s FROM %s;" % (self.db_name, self.db_user))
        self._postgres_cmd("DROP USER %s;" % (self.db_user,))
        self._postgres_cmd("DROP DATABASE %s;" % (self.db_name,))

    def _jorvik_configure(self):
        # Write database configuration
        configuration = "[client]\n" \
                        "host = localhost\n" \
                        "port = 5432\n" \
                        "database = %(db_name)s\n" \
                        "user = %(db_user)s\n" \
                        "password = %(db_pass)s\n" % {
            "db_name": self.db_name, "db_user": self.db_user,
            "db_pass": self.db_pass
        }
        cmd.file_write("%s/config/pgsql.cnf" % self._get_nginx_root(),
                       configuration)

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