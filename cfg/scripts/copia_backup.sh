#!/bin/sh

DATA=$(date -d "1 day ago" '+%Y%m%d')
echo $DATA
FILE=$(find /var/lib/postgresql/backup_produzione/ -type f -print | grep $DATA)
echo $FILE
cp $FILE /staging/dump.gz
echo "dump copied to /staging/dump.gz"
gunzip -f /staging/dump.gz
echo "done"
