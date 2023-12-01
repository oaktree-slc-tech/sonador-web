# syntax = docker/dockerfile:experimental
FROM ubuntu:22.04
ARG PYTHONUNBUFFERED=1
ARG CI_COMMIT_SHA

# Install Python runtime and dependencies
RUN apt-get update && apt-get install -y git python3 python3-pip virtualenv python3-configobj uvicorn \
  && useradd -ms /bin/bash -u 1000 -d /srv/www/sonador sonador 
USER 1000
RUN --mount=type=secret,id=auto-devops-build-secrets . /run/secrets/auto-devops-build-secrets \
  && export CI_COMMIT_SHA=${CI_COMMIT_SHA:-master} \
  && echo "Build container for Sonador $CI_COMMIT_SHA" \
  && mkdir -p /srv/www/sonador/config && mkdir -p /srv/www/sonador/docroot \
  && cd /srv/www/sonador && git clone https://code.oak-tree.tech/oak-tree/medical-imaging/sonador.git \
  && cd /srv/www/sonador/sonador && git checkout $CI_COMMIT_SHA \
  && git submodule update --init --recursive
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

# Install PostgreSQL (for production)
USER 0
RUN apt-get install -y libpq-dev && pip3 install --timeout 30 psycopg2

# Install sudo
RUN apt-get install -y sudo \
  && cp /srv/www/sonador/sonador/config/entrypoint.sh /srv/www/sonador/ \
  && chmod +x /srv/www/sonador/entrypoint.sh

EXPOSE 8070
USER 1000
WORKDIR /srv/www/sonador
CMD /srv/www/sonador/entrypoint.sh
