from __future__ import absolute_import, unicode_literals
import os
from celery import Celery

# set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wonderbot.settings')

app = Celery('wonderbot', broker='redis://localhost')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    print('Request: {0!r}'.format(self.request))


@app.task(bind=True)
def environment_create(self, environment):
    environment.do_creation()


@app.task(bind=True)
def environment_refresh(self, environment):
    environment.do_refresh()


@app.task(bind=True)
def environment_update(self, environment):
    environment.do_update()


@app.task(bind=True)
def environment_delete(self, environment):
    environment.do_delete()


