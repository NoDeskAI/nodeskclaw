FROM python:3.13-slim-bookworm

ARG NANOBOT_VERSION=0.2.0
ARG IMAGE_VERSION=v0.2.0
ARG PIP_INDEX_URL=""
ARG PIP_TRUSTED_HOST=""
ARG APT_MIRROR=""

ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}

RUN if [ -n "$APT_MIRROR" ]; then \
      sed -i "s|deb.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources; \
    fi && \
    apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl gettext-base && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "nanobot-ai==${NANOBOT_VERSION}"

COPY nodeskclaw-tunnel-bridge/ /tmp/nodeskclaw-tunnel-bridge/
RUN pip install --no-cache-dir /tmp/nodeskclaw-tunnel-bridge/ && \
    rm -rf /tmp/nodeskclaw-tunnel-bridge/

COPY config.json.template /opt/nanobot/config.json.template
COPY docker-entrypoint.sh /opt/nanobot/docker-entrypoint.sh
RUN chmod +x /opt/nanobot/docker-entrypoint.sh

RUN echo "${IMAGE_VERSION}" > /opt/nanobot/.nanobot-version

EXPOSE 18790
WORKDIR /opt/nanobot

ENTRYPOINT ["/opt/nanobot/docker-entrypoint.sh"]
CMD ["nanobot", "gateway"]
