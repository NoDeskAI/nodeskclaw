FROM rust:1.82-slim-bookworm AS builder

RUN apt-get update && \
    apt-get install -y pkg-config libssl-dev && \
    rm -rf /var/lib/apt/lists/*

COPY zeroclaw-security-layer/ /opt/zeroclaw-security-layer/
WORKDIR /opt/zeroclaw-security-layer

RUN cargo build --release --example test_runtime

FROM debian:bookworm-slim

RUN apt-get update && \
    apt-get install -y ca-certificates libssl3 && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/zeroclaw-security-layer/target/release/examples/test_runtime /usr/local/bin/test_runtime

ENV SECURITY_LAYER_ENABLED=true
ENV SECURITY_WS_ENDPOINT=ws://host.docker.internal:8000

CMD ["/usr/local/bin/test_runtime"]
