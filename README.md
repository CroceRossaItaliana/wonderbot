Wonderbot
=========

How to set up the tool
----------------------

Required packages:

* nginx
* uwsgi
* redis
* celery
* postgresql

Create a `staging` user that owns the `/staging` folder.

Structure of the folder:

```
/staging
|-- log
|-- scripts
|   |-- copia_backup.sh
|   |-- postgres_start.sh
|   |-- postgres_stop.sh
|-- skeleton
|   |-- config
|   |   |-- api.cnf (this is not on gh)
|-- wonderbot (all wonderbot files)
|-- robots.txt
```

Crean old db version

```
/root
|-- scripts
|   |-- clean.sh
```

root crontab:
```59 23 * * * root sh /root/scripts/clean.sh```

nginix conf in `staging.cnf`
