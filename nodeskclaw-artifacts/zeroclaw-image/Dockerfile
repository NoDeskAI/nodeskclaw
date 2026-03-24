FROM debian:bookworm-slim

ARG ZEROCLAW_VERSION=v0.6.1
ARG IMAGE_VERSION=v0.6.1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl python3-minimal python3-pip && \
    rm -rf /var/lib/apt/lists/*

COPY nodeskclaw-tunnel-bridge/ /tmp/nodeskclaw-tunnel-bridge/
RUN pip3 install --no-cache-dir --break-system-packages /tmp/nodeskclaw-tunnel-bridge/ && \
    rm -rf /tmp/nodeskclaw-tunnel-bridge/

RUN mkdir -p /opt/zeroclaw && \
    curl -fsSL "https://github.com/zeroclaw-labs/zeroclaw/releases/download/${ZEROCLAW_VERSION}/zeroclaw-x86_64-unknown-linux-gnu.tar.gz" \
    -o /tmp/zeroclaw.tar.gz && \
    tar xzf /tmp/zeroclaw.tar.gz -C /opt/zeroclaw/ && \
    chmod +x /opt/zeroclaw/zeroclaw && \
    rm -f /tmp/zeroclaw.tar.gz

COPY docker-entrypoint.sh /opt/zeroclaw/docker-entrypoint.sh
RUN chmod +x /opt/zeroclaw/docker-entrypoint.sh

ENV PATH="/opt/zeroclaw:${PATH}"

RUN echo "${IMAGE_VERSION}" > /opt/zeroclaw/.zeroclaw-version

EXPOSE 8080
WORKDIR /opt/zeroclaw

ENTRYPOINT ["/opt/zeroclaw/docker-entrypoint.sh"]
CMD ["zeroclaw", "gateway", "--port", "8080"]
