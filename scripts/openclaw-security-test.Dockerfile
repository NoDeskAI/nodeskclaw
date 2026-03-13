FROM node:22-slim

COPY openclaw-security-layer/ /opt/openclaw-security-layer/
WORKDIR /opt/openclaw-security-layer

RUN node -e "\
  const p = JSON.parse(require('fs').readFileSync('package.json','utf8')); \
  delete p.devDependencies; \
  require('fs').writeFileSync('package.json', JSON.stringify(p, null, 2))" && \
  npm install --no-save tsx

ENV SECURITY_LAYER_ENABLED=true
ENV SECURITY_WS_ENDPOINT=ws://host.docker.internal:8000

CMD ["npx", "tsx", "test_security_runtime.mts"]
