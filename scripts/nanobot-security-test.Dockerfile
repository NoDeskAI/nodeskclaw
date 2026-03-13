FROM python:3.12-slim-bookworm

COPY nanobot-security-layer/ /opt/nanobot-security-layer/
RUN pip install --no-cache-dir /opt/nanobot-security-layer

RUN mkdir -p /opt/test && \
    cp /opt/nanobot-security-layer/test_security_runtime.py /opt/test/test_security_runtime.py

ENV SECURITY_LAYER_ENABLED=true
ENV SECURITY_WS_ENDPOINT=ws://host.docker.internal:8000

CMD ["python", "/opt/test/test_security_runtime.py"]
