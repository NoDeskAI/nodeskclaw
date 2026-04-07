# =============================================================================
# OpenClaw 定制镜像
# 用途: NoDeskClaw 部署到 K8s 的 OpenClaw 实例镜像
# 构建方式: npm 全局安装 openclaw，不从源码构建
# 设计: bookworm-slim 基础镜像 + 最小 apt 依赖 + npm install
# =============================================================================

ARG NODE_VERSION=22

FROM node:${NODE_VERSION}-bookworm-slim

# ---------- 构建参数 ----------
ARG OPENCLAW_VERSION=2026.4.5
ARG IMAGE_VERSION=v2026.4.5

# ---------- 元数据标签 ----------
LABEL maintainer="Xy718Labs"
LABEL org.opencontainers.image.title="OpenClaw"
LABEL org.opencontainers.image.version="${IMAGE_VERSION}"
LABEL org.opencontainers.image.description="OpenClaw AI Agent 平台 - NoDeskClaw 定制镜像"

# ---------- 系统依赖（BuildKit apt 缓存，重复构建秒过）----------
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        git openssh-client ca-certificates \
        curl wget \
        python3 python3-pip \
        jq procps net-tools && \
    ln -sf /usr/bin/python3 /usr/bin/python && \
    git config --global url."https://github.com/".insteadOf ssh://git@github.com/ && \
    git config --global --add url."https://github.com/".insteadOf git@github.com:

# ---------- Python 依赖 ----------
RUN --mount=type=cache,target=/root/.cache/pip \
    pip3 install --break-system-packages requests tos

# ---------- 全局安装 OpenClaw（BuildKit npm 缓存）----------
RUN --mount=type=cache,target=/root/.npm \
    npm install -g openclaw@${OPENCLAW_VERSION} @nodeskai/genehub

# ---------- 预置用户数据目录结构 ----------
RUN mkdir -p /root/.openclaw/agents/main/sessions \
             /root/.openclaw/config \
             /root/.openclaw/credentials \
             /root/.openclaw/extensions \
             /root/.openclaw/workspace \
             /root/.openclaw/memory \
             /root/.openclaw/data \
             /root/.openclaw/temp \
             /root/.openclaw/canvas \
             /root/.openclaw/devices \
             /root/.openclaw/identity \
             /root/.openclaw/cron \
             /root/.openclaw/skills

# ---------- 配置模板 ----------
COPY openclaw.json.template /root/.openclaw/openclaw.json.template
COPY repair-sessions-index.js /repair-sessions-index.js
COPY repair-user-data.js /repair-user-data.js

# ---------- 版本标记 ----------
RUN echo "${IMAGE_VERSION}" > /root/.openclaw-version

# ---------- 启动脚本 + Init Container 脚本 ----------
COPY docker-entrypoint.sh /docker-entrypoint.sh
COPY init-container.sh /init-container.sh
RUN chmod +x /docker-entrypoint.sh /init-container.sh

# ---------- 运行配置 ----------
WORKDIR /root
EXPOSE 18789 9721

ENTRYPOINT ["/docker-entrypoint.sh"]
