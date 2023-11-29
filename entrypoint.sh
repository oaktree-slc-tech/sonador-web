#! /bin/bash

cd /srv/www/sonador/
mkdir -p config/dbmigrations{,/{auth,secure,wgtsocial,wgtauth{,/{registration,social}},wgtregistration,visionaire}}
touch config/dbmigrations{,/{auth,secure,wgtsocial,wgtauth{,/{registration,social}},wgtregistration,visionaire}}/__init__.py
cd /srv/www/sonador/sonador
python3 /apps/visionaire/management/commands/imaging-env-init.py
echo "running uvicorn"
python3 uvicorn-sonador.y
echo "Changing dir"
cd /srv/www/sonador
