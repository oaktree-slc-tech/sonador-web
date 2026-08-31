# syntax = docker/dockerfile:experimental
FROM ubuntu:26.04
ARG PYTHONUNBUFFERED=1
ARG CI_COMMIT_SHA

# Ubuntu 26.04 ships Python 3.14 and marks the system interpreter as externally
# managed (PEP 668), which blocks system-wide pip installs. This is a
# single-purpose application image, so allow pip to install into it.
ENV PIP_BREAK_SYSTEM_PACKAGES=1

# Install Python runtime and dependencies. Ubuntu 24.04+ base images ship a default
# UID 1000 'ubuntu' user, so instead of creating a colliding user we repoint that
# account to the sonador home directory and rename it (the app runs as UID 1000
# throughout); the useradd fallback covers any base that doesn't ship the user.
#
# Kafka native dependencies, for the HIPAA audit trail (confluent-kafka in
# requirements.txt). The Orthanc cloud plugin image installs librdkafka-dev for the same
# reason. Two notes for whoever touches this next:
#  - librdkafka-dev: the confluent-kafka manylinux wheel statically bundles its own
#    librdkafka, so the import works without this. It is installed so the platform
#    library is present if a base image or Python version ever ships without a matching
#    wheel and pip falls back to building from source.
#  - libsasl2-modules-gssapi-mit: required at RUNTIME to use sasl.mechanisms = 'GSSAPI'
#    (Kerberos) against a secured broker. TLS and SASL PLAIN/SCRAM/OAUTHBEARER work with
#    the bundled build; GSSAPI is the one mechanism that needs a system SASL module, and
#    its absence surfaces only when a deployment enables it.
RUN apt-get update && apt-get install -y git python3 python3-pip virtualenv python3-configobj \
  librdkafka-dev libsasl2-modules-gssapi-mit \
  && mkdir -p /srv/www/sonador \
  && ( usermod -l sonador -d /srv/www/sonador -s /bin/bash ubuntu \
       || useradd -ms /bin/bash -u 1000 -d /srv/www/sonador sonador ) \
  && mkdir -p /srv/www/sonador/docroot/static \
  && chown 1000:1000 -R /srv/www/sonador
RUN --mount=type=secret,id=auto-devops-build-secrets . /run/secrets/auto-devops-build-secrets \
  && echo "Build container for Sonador $CI_COMMIT_SHA" \
  && mkdir -p /srv/www/sonador/config \ 
  && cd /srv/www/sonador && git clone https://code.oak-tree.tech/oak-tree/medical-imaging/sonador.git \
  && cd /srv/www/sonador/sonador && git checkout $CI_COMMIT_SHA \
  && git submodule update --init --recursive \
  && cd .. && chown -R 1000:1000 /srv/www/sonador/sonador && chown -R 1000:1000 /srv/www/sonador/config
USER 0
RUN pip3 install --timeout 300 -r /srv/www/sonador/sonador/requirements.txt \
  && pip3 install uvicorn \
  && mkdir -p /opt/ && chown -R 1000:1000 /opt/

# Install Node.js runtime and components
USER 1000
RUN nodeenv --node=18.18.2 /opt/nodejs/
ENV PATH=/opt/nodejs/bin:${PATH}
RUN npm install -g gulp yarn@1.22.19 \
  && yarn config set @sonador:registry https://code.oak-tree.tech/api/v4/projects/335/packages/npm/ -g \
  && npm config set @sonador:registry https://code.oak-tree.tech/api/v4/projects/335/packages/npm/ -g \
  && cd /srv/www/sonador/sonador/ \
  && npm install gulp yarn@1.22.19 && npm install
# Build OHIF and viewer components
RUN cd /srv/www/sonador/sonador/ && gulp jsBuildAce && gulp jsBuildMagnificLightbox \
  && cd /srv/www/sonador/sonador/apps/visionaire/jslib/ohif \
  && yarn install && yarn build:package \
  && cd /srv/www/sonador/sonador/ && gulp deployOHIF

# Install PostgreSQL (for production). psycopg2 is source-only and the base image
# ships no compiler or Python headers, so use psycopg2-binary instead; 2.9.11 is
# the first release with cp314 wheels (Ubuntu 26.04 ships Python 3.14) and the
# wheel bundles libpq, so no libpq-dev build dependency is required.
USER 0
RUN pip3 install --timeout 30 "psycopg2-binary>=2.9.11"

# Install sudo
RUN apt-get install -y sudo \
  && cp /srv/www/sonador/sonador/config/entrypoint.sh /srv/www/sonador/ \
  && chmod +x /srv/www/sonador/entrypoint.sh && chown 1000:1000 /srv/www/sonador/sonador/config/entrypoint.sh 

EXPOSE 8070
USER 1000

# Collect static assets
RUN cd /srv/www/sonador/sonador/ \
  && SONADOR_SITECONFIG=/srv/www/sonador/sonador/config/sonador.site.config \
    DJANGO_SETTINGS_MODULE=sonador.settings \
    python3 manage.py collectstatic

WORKDIR /srv/www/sonador
CMD /srv/www/sonador/entrypoint.sh
