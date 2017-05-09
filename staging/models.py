from django.db import models

from staging.validators import validate_environment_name
from wonderbot.settings import DEFAULT_REPOSITORY_URL, DEFAULT_BRANCH, HIGH_LEVEL_DOMAIN


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
    created = models.DateTimeField(auto_created=True)
    updated = models.DateTimeField(auto_now=True)

    def url(self):
        return "%s://%s.%s" % (self.protocol, self.name, HIGH_LEVEL_DOMAIN)
    
    def __str__(self):
        return "%s (%s, %s)" % (self.name, self.protocol, self.get_status_display())

    def queue_for_creation(self):
        self.status = self.CREATING
        self.save()
        pass

    def queue_for_deletion(self):
        self.status = self.DELETING
        self.save()
        pass

    def queue_for_update(self):
        self.status = self.UPDATING
        self.save()

        pass

    def queue_for_refresh(self):
        self.status = self.REFRESHING
        self.save()

        pass
