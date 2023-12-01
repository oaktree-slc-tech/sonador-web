#! /bin/bash
PROJECT_ROOT=${PROJECT_ROOT:-/srv/www/sonador}
CONFIG_ROOT=${CONFIG_ROOT:-$PROJECT_ROOT/config}
mkdir -p $CONFIG_ROOT/dbmigrations{,/{auth,secure,wgtsocial,wgtauth{,/{registration,social}},wgtregistration,visionaire}}
touch $CONFIG_ROOT/dbmigrations{,/{auth,secure,wgtsocial,wgtauth{,/{registration,social}},wgtregistration,visionaire}}/__init__.py

# Run initialize script for the environment
python3 $PROJECT_ROOT/sonador/manage.py imaging-env-init
python3 $PROJECT_ROOT/sonador/uvicorn-sonador.py
