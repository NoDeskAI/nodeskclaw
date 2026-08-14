# 构建镜像源预设

Docker 构建过程中需要从 PyPI、npm、Debian/Alpine 软件源下载依赖包。在部分国家和地区，默认源的网络延迟较高，可通过预设文件切换到就近的镜像源。

## 预设文件

| 文件 | 适用地区 |
|------|----------|
| `cn.env` | 中国大陆（清华 PyPI + npmmirror + 阿里云 apt/apk） |

## 使用方式

### deploy/release.sh

```bash
./deploy/release.sh create v0.5.0 --mirrors cn
```

或写入 `deploy/.env.local` 永久生效：

```bash
echo 'MIRRORS=cn' >> deploy/.env.local
```

### nodeskclaw-artifacts/build.sh

```bash
./nodeskclaw-artifacts/build.sh openclaw --mirrors cn
```

## 变量说明

| 变量 | 作用 | 默认值（空 = 官方源） |
|------|------|----------------------|
| `PIP_INDEX_URL` | pip / uv Python 包源 | pypi.org |
| `PIP_TRUSTED_HOST` | pip 信任域名 | — |
| `NPM_REGISTRY` | npm 包源 | registry.npmjs.org |
| `APT_MIRROR` | Debian apt 镜像主机名 | deb.debian.org |
| `ALPINE_MIRROR` | Alpine apk 镜像主机名 | dl-cdn.alpinelinux.org |

## 自定义预设

复制 `cn.env` 并修改为自己的镜像地址即可：

```bash
cp cn.env custom.env
# 编辑 custom.env 中的 URL
./deploy/release.sh create v0.5.0 --mirrors custom
```

## Docker Hub 基础镜像加速

Dockerfile 中的 `FROM python:3.12-slim` 等基础镜像从 Docker Hub 拉取，无法通过构建参数加速。如需加速，请在 Docker Desktop 设置中配置 registry mirror，或编辑 `/etc/docker/daemon.json`：

```json
{
  "registry-mirrors": ["https://your-mirror.example.com"]
}
```
