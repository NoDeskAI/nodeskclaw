FROM python:3.13-slim-bookworm

ARG NANOBOT_VERSION=latest
ARG IMAGE_VERSION=latest

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl gettext-base && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "nanobot-ai==${NANOBOT_VERSION}"

COPY nanobot.yaml.template /opt/nanobot/nanobot.yaml.template
COPY docker-entrypoint.sh /opt/nanobot/docker-entrypoint.sh
RUN chmod +x /opt/nanobot/docker-entrypoint.sh

RUN echo "${IMAGE_VERSION}" > /opt/nanobot/.nanobot-version

EXPOSE 18790
WORKDIR /opt/nanobot

ENTRYPOINT ["/opt/nanobot/docker-entrypoint.sh"]
CMD ["nanobot", "gateway", "--config", "/opt/nanobot/nanobot.yaml"]
