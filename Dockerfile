# syntax = docker/dockerfile:experimental
FROM ubuntu:20.04
ARG PYTHONUNBUFFERED=1
ARG CI_COMMIT_SHA

# Install Python runtime and dependencies
RUN apt-get update && apt-get install -y git python3 python3-pip virtualenv python3-configobj
RUN --mount=type=secret,id=auto-devops-build-secrets . /run/secrets/auto-devops-build-secrets \
  && export CI_COMMIT_SHA=${CI_COMMIT_SHA:-master} \
  && echo "Build container for Sonador $CI_COMMIT_SHA" \
  && mkdir -p /srv/www/sonador/config && mkdir -p /srv/www/sonador/docroot \
  && cd /srv/www/sonador && git clone https://code.oak-tree.tech/oak-tree/medical-imaging/sonador.git \
  && cd /srv/www/sonador/sonador && git checkout $CI_COMMIT_SHA \
  && git submodule update --init --recursive --remote \
  && pip3 install --timeout 300 -r requirements.txt

# Install Node.js runtime and components
RUN nodeenv --node=12.16.3 /opt/nodejs/
ENV PATH=/opt/nodejs/bin:${PATH}
RUN npm install -g gulp yarn \
  && cd /srv/www/sonador/sonador/ \
  && npm install gulp yarn && npm install 

# Build OHIF and viewer components
RUN cd /srv/www/sonador/sonador/ && gulp js

# Install Apache Server and Configure Web Application
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get install -y tzdata \
  && ln -fs /usr/share/zoneinfo/UTC /etc/localtime \
  && dpkg-reconfigure tzdata 
RUN apt-get install -y apache2 \
    build-essential \
    postgresql-client \
    net-tools vim telnet \
    libapache2-mod-wsgi-py3 \
  && ln -sf /proc/$$/fd/1 /var/log/apache2/access.log \
  && ln -sf /proc/$$/fd/2 /var/log/apache2/error.log 
RUN mkdir -p /srv/www/sonador/logs && cd /srv/www/sonador/sonador/ \
  && ln -s /srv/www/sonador/sonador/config/apache2.docker.conf  /etc/apache2/sites-available/sonador.conf \
  && chown www-data:www-data -R /srv/www/sonador/sonador \
  && a2ensite sonador

# Install PostgreSQL (for production)
RUN apt-get install libpq-dev && pip3 install --timeout 30 psycopg2

# Install sudo
RUN apt-get install -y sudo

WORKDIR /srv/www/sonador
EXPOSE 8070
CMD apachectl -D FOREGROUND
