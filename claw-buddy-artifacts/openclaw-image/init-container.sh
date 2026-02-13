#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# OpenClaw Init Container 脚本
#
# 职责: 在主容器启动前，处理 PVC 中的用户数据初始化
#   - 首次部署（PVC 为空）: 拷贝模板目录到 PVC
#   - 版本相同: 跳过
#   - 版本不同（镜像升级）: 轻量升级（更新版本标记 + 合并内置插件）
#
# PVC 挂载点: /init-data（Init Container 中）
# 镜像内数据: /root/.openclaw（Dockerfile 预置）
# =============================================================================

PVC_DIR="/init-data"
IMAGE_VERSION_FILE="/root/.openclaw-version"
PVC_VERSION_FILE="${PVC_DIR}/.openclaw-version"
IMAGE_DATA_DIR="/root/.openclaw"
PVC_DATA_DIR="${PVC_DIR}/.openclaw"

# 读取镜像内的版本号
IMAGE_VERSION="unknown"
if [ -f "${IMAGE_VERSION_FILE}" ]; then
  IMAGE_VERSION=$(cat "${IMAGE_VERSION_FILE}" | tr -d '[:space:]')
fi

echo "[init] OpenClaw Init Container 启动"
echo "[init] 镜像版本: ${IMAGE_VERSION}"

# ---- Case 1: 首次部署（PVC 中没有版本标记文件） ----

if [ ! -f "${PVC_VERSION_FILE}" ]; then
  echo "[init] 首次部署 - PVC 为空，初始化用户数据..."

  # 拷贝 .openclaw 完整目录
  cp -a "${IMAGE_DATA_DIR}" "${PVC_DATA_DIR}"
  echo "[init]   已拷贝 ${IMAGE_DATA_DIR} -> ${PVC_DATA_DIR}"

  # 拷贝版本标记
  cp "${IMAGE_VERSION_FILE}" "${PVC_VERSION_FILE}"
  echo "[init]   已写入版本标记: ${IMAGE_VERSION}"

  # 拷贝 shell 配置
  for f in .bashrc .profile; do
    if [ -f "/root/${f}" ]; then
      cp "/root/${f}" "${PVC_DIR}/${f}"
      echo "[init]   已拷贝 ${f}"
    fi
  done

  echo "[init] 首次初始化完成"
  exit 0
fi

# ---- 读取 PVC 中的版本号 ----

PVC_VERSION=$(cat "${PVC_VERSION_FILE}" | tr -d '[:space:]')
echo "[init] PVC 版本: ${PVC_VERSION}"

# ---- Case 2: 版本相同，跳过 ----

if [ "${IMAGE_VERSION}" = "${PVC_VERSION}" ]; then
  echo "[init] 版本一致 (${IMAGE_VERSION})，跳过初始化"
  exit 0
fi

# ---- Case 3: 版本不同，轻量升级 ----

echo "[init] 版本不同 (${PVC_VERSION} -> ${IMAGE_VERSION})，执行轻量升级..."

# 3a. 更新版本标记
cp "${IMAGE_VERSION_FILE}" "${PVC_VERSION_FILE}"
echo "[init]   已更新版本标记: ${IMAGE_VERSION}"

# 3b. 合并内置插件（保留用户自定义插件，更新/新增内置插件）
if [ -d "${IMAGE_DATA_DIR}/extensions" ]; then
  mkdir -p "${PVC_DATA_DIR}/extensions"
  # 使用 cp -n 不覆盖已存在的文件（保留用户自定义），cp -a 保留权限
  # 注意: cp -n 在某些系统上不可用，改用 rsync 风格的逻辑
  for ext_dir in "${IMAGE_DATA_DIR}/extensions"/*/; do
    if [ -d "${ext_dir}" ]; then
      ext_name=$(basename "${ext_dir}")
      target="${PVC_DATA_DIR}/extensions/${ext_name}"
      if [ ! -d "${target}" ]; then
        cp -a "${ext_dir}" "${target}"
        echo "[init]   新增内置插件: ${ext_name}"
      else
        echo "[init]   跳过已存在的插件: ${ext_name}"
      fi
    fi
  done
fi

# 3c. 确保所有子目录存在（新版本可能新增了子目录）
for subdir in agents/main/sessions config credentials extensions workspace memory data temp canvas devices identity cron; do
  mkdir -p "${PVC_DATA_DIR}/${subdir}"
done

# 3d. 更新 shell 配置
for f in .bashrc .profile; do
  if [ -f "/root/${f}" ]; then
    cp "/root/${f}" "${PVC_DIR}/${f}"
    echo "[init]   已更新 ${f}"
  fi
done

echo "[init] 轻量升级完成: ${PVC_VERSION} -> ${IMAGE_VERSION}"
exit 0
