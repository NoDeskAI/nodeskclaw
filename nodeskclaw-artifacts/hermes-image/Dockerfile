FROM python:3.12-slim

ARG HERMES_VERSION=v2026.4.23
ARG IMAGE_VERSION=v0.9.0
ARG PIP_INDEX_URL=""
ARG PIP_TRUSTED_HOST=""
ARG APT_MIRROR=""

ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST} \
    HERMES_HOME=/root/.hermes

RUN if [ -n "$APT_MIRROR" ]; then \
      sed -i "s|deb.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources; \
    fi && \
    apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl git procps && \
    rm -rf /var/lib/apt/lists/*

COPY hermes-nodeskclaw-bridge/ /tmp/hermes-nodeskclaw-bridge/

RUN git clone --depth 1 --branch "${HERMES_VERSION}" https://github.com/NousResearch/hermes-agent.git /tmp/hermes-agent && \
    pip install --no-cache-dir "/tmp/hermes-agent[homeassistant,cron,messaging,dingtalk,feishu]" && \
    pip install --no-cache-dir /tmp/hermes-nodeskclaw-bridge && \
    rm -rf /tmp/hermes-agent /tmp/hermes-nodeskclaw-bridge

RUN mkdir -p /root/.hermes/{logs,skills,scripts,cron,sessions,memories}

COPY nodeskclaw-artifacts/hermes-image/docker-entrypoint.sh /opt/hermes/docker-entrypoint.sh
RUN chmod +x /opt/hermes/docker-entrypoint.sh

RUN echo "${IMAGE_VERSION}" > /opt/hermes/.hermes-version

EXPOSE 8642
WORKDIR /root

ENTRYPOINT ["/opt/hermes/docker-entrypoint.sh"]
