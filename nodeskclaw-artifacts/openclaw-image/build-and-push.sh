#!/bin/bash
# 构建 amd64 架构的 OpenClaw 镜像并推送到火山云 CR
set -e

REGISTRY="nodesk-center-cn-beijing.cr.volces.com/base-image/nodeskclaw-openclaw-base"
TAG="$(date +%Y%m%d)-$(git rev-parse --short HEAD 2>/dev/null || echo 'manual')"

echo "构建镜像: ${REGISTRY}:${TAG} (linux/amd64)"
docker build --platform linux/amd64 \
  --build-arg http_proxy= \
  --build-arg https_proxy= \
  --build-arg HTTP_PROXY= \
  --build-arg HTTPS_PROXY= \
  -t "${REGISTRY}:${TAG}" .

echo "推送镜像..."
docker push "${REGISTRY}:${TAG}"

echo "完成: ${REGISTRY}:${TAG}"
