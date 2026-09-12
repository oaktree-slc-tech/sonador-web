#! /bin/bash
PROJECT_ROOT=${PROJECT_ROOT:-/srv/www/sonador}
CONFIG_ROOT=${CONFIG_ROOT:-$PROJECT_ROOT/config}
mkdir -p $CONFIG_ROOT/dbmigrations{,/{auth,secure,wgtsocial,wgtauth{,/{registration,social}},wgtregistration,visionaire}}
touch $CONFIG_ROOT/dbmigrations{,/{auth,secure,wgtsocial,wgtauth{,/{registration,social}},wgtregistration,visionaire}}/__init__.py

# Run initialize script for the environment
python3 $PROJECT_ROOT/sonador/manage.py imaging-env-init || exit 1

# Refuse to serve traffic when the deployment does not satisfy the registered system checks.
# Session storage in particular is a configuration guarantee the authentication workflows
# depend on and cannot verify per request.
python3 $PROJECT_ROOT/sonador/manage.py check --database default || exit 1
python3 $PROJECT_ROOT/sonador/manage.py verify-login-protections || exit 1

python3 $PROJECT_ROOT/sonador/uvicorn-sonador.py
