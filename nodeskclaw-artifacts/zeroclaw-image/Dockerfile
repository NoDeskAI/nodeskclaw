FROM debian:bookworm-slim

ARG ZEROCLAW_VERSION=v0.1.0
ARG IMAGE_VERSION=v0.1.0
ARG TARGETARCH=amd64

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

RUN mkdir -p /opt/zeroclaw && \
    curl -fsSL "https://github.com/nicholasgasior/zeroclaw/releases/download/${ZEROCLAW_VERSION}/zeroclaw-linux-${TARGETARCH}" \
    -o /opt/zeroclaw/zeroclaw && \
    chmod +x /opt/zeroclaw/zeroclaw

COPY docker-entrypoint.sh /opt/zeroclaw/docker-entrypoint.sh
RUN chmod +x /opt/zeroclaw/docker-entrypoint.sh

ENV PATH="/opt/zeroclaw:${PATH}"

RUN echo "${IMAGE_VERSION}" > /opt/zeroclaw/.zeroclaw-version

EXPOSE 8080
WORKDIR /opt/zeroclaw

ENTRYPOINT ["/opt/zeroclaw/docker-entrypoint.sh"]
CMD ["zeroclaw", "gateway", "--port", "8080"]
