#!/usr/bin/env bash
set -euo pipefail

REGISTRY="nodesk-center-cn-beijing.cr.volces.com/base-image"
IMAGE_NAME="clawbuddy-llm-proxy"
NAMESPACE="clawbuddy-system"
DEPLOYMENT="clawbuddy-llm-proxy"
CONTAINER="llm-proxy"

TAG="$(date +%Y%m%d)-$(git rev-parse --short HEAD)"
FULL_IMAGE="${REGISTRY}/${IMAGE_NAME}:${TAG}"

echo "=== 1/5 构建镜像 ==="
echo "  镜像: ${FULL_IMAGE}"
docker build --platform linux/amd64 -t "${FULL_IMAGE}" .

echo ""
echo "=== 2/5 推送镜像 ==="
docker push "${FULL_IMAGE}"

echo ""
echo "=== 3/5 更新 Deployment ==="
kubectl set image "deployment/${DEPLOYMENT}" "${CONTAINER}=${FULL_IMAGE}" -n "${NAMESPACE}"

echo ""
echo "=== 4/5 等待滚动更新 ==="
kubectl rollout status "deployment/${DEPLOYMENT}" -n "${NAMESPACE}" --timeout=120s

echo ""
echo "=== 5/5 验证 ==="
kubectl get pods -n "${NAMESPACE}" -l "app=${DEPLOYMENT}" -o wide
echo ""
echo "部署完成: ${FULL_IMAGE}"
