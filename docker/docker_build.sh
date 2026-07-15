#!/usr/bin/env bash
# =============================================================================
# 构建 Octop Docker 镜像
#
# 用法:
#   bash docker/docker_build.sh [镜像标签] [额外 docker build 参数...]
#
# 示例:
#   bash docker/docker_build.sh
#   bash docker/docker_build.sh myreg/octop:v1
#   bash docker/docker_build.sh octop:dev --no-cache
#
# 国内加速（可选，需 BuildKit，本脚本默认已开启）:
#   PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple \
#   PIP_TRUSTED_HOST=mirrors.aliyun.com \
#   NPM_REGISTRY=https://registry.npmmirror.com \
#   APT_MIRROR=mirrors.aliyun.com \
#   bash docker/docker_build.sh
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

IMAGE_TAG="${1:-octop:latest}"
shift 2>/dev/null || true

# BuildKit 启用 Dockerfile 缓存挂载，加速 npm / pip / apt 下载
export DOCKER_BUILDKIT=1

BUILD_ARGS=()
if [ -n "${PIP_INDEX_URL:-}" ]; then
    BUILD_ARGS+=(--build-arg "PIP_INDEX_URL=${PIP_INDEX_URL}")
fi
if [ -n "${PIP_TRUSTED_HOST:-}" ]; then
    BUILD_ARGS+=(--build-arg "PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}")
fi
if [ -n "${NPM_REGISTRY:-}" ]; then
    BUILD_ARGS+=(--build-arg "NPM_REGISTRY=${NPM_REGISTRY}")
fi
if [ -n "${NODE_MAX_OLD_SPACE_SIZE:-}" ]; then
    BUILD_ARGS+=(--build-arg "NODE_MAX_OLD_SPACE_SIZE=${NODE_MAX_OLD_SPACE_SIZE}")
fi
if [ -n "${APT_MIRROR:-}" ]; then
    BUILD_ARGS+=(--build-arg "APT_MIRROR=${APT_MIRROR}")
fi

echo "╔══════════════════════════════════════════════════╗"
echo "║  正在构建 Octop Docker 镜像                      ║"
echo "║  标签: ${IMAGE_TAG}"
echo "╚══════════════════════════════════════════════════╝"
echo ""

docker build \
    -t "$IMAGE_TAG" \
    -f "${REPO_ROOT}/Dockerfile" \
    "${BUILD_ARGS[@]}" \
    "$@" \
    "$REPO_ROOT"

echo ""
echo "✅ 构建完成: ${IMAGE_TAG}"
echo ""
echo "启动示例:"
echo "  docker run -d -p 8088:8088 -v octop-data:/data/.octop -e HOME=/data ${IMAGE_TAG}"
echo ""
echo "或使用 Compose:"
echo "  docker compose -f docker/docker-compose.yml up -d"
