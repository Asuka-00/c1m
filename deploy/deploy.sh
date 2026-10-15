#!/usr/bin/env bash
# 一键部署 / 更新：把当前 git HEAD 打包上传到服务器并重建容器。
#   用法：deploy/deploy.sh [root@host] [/opt/fsft]
#   首次部署：服务器上自动生成 deploy/.env（随机密钥与密码，仅存于服务器），并导入演示数据。
#   之后：只更新代码、重建镜像、执行迁移（不会覆盖 .env，也不会重置演示数据）。
set -euo pipefail

HOST="${1:-${DEPLOY_HOST:-root@115.190.121.153}}"
DIR="${2:-${DEPLOY_DIR:-/opt/fsft}}"
cd "$(git rev-parse --show-toplevel)"
REV="$(git rev-parse --short HEAD)"
[ -z "$(git status --porcelain)" ] || echo "注意：工作区有未提交修改，只部署已提交的 HEAD ($REV)"

echo ">> 上传代码 $REV -> $HOST:$DIR"
ssh "$HOST" "mkdir -p '$DIR/src' && find '$DIR/src' -mindepth 1 -maxdepth 1 -exec rm -rf {} +"
git archive --format=tar HEAD | ssh "$HOST" "tar -x -C '$DIR/src' && echo '$REV' > '$DIR/src/REVISION'"

ssh "$HOST" DIR="$DIR" bash -s <<'REMOTE'
set -euo pipefail
cd "$DIR"
ENV="$DIR/.env"
FIRST=0
if [ ! -f "$ENV" ]; then
  FIRST=1
  IP="$(curl -s --max-time 5 ifconfig.me || hostname -I | awk '{print $1}')"
  umask 077
  cat > "$ENV" <<CONF
PROJECT_NAME=FSFT MES
FRONTEND_HOST=http://$IP
HTTP_PORT=80
SECRET_KEY=$(openssl rand -hex 32)
POSTGRES_DB=app
POSTGRES_PASSWORD=$(openssl rand -hex 24)
APP_DB_PASSWORD=$(openssl rand -hex 24)
FIRST_SUPERUSER=admin@example.com
FIRST_SUPERUSER_USERNAME=admin
FIRST_SUPERUSER_PASSWORD=$(openssl rand -base64 18 | tr -d '/+=' | cut -c1-20)
QTIME_SWEEP_SECONDS=60
SEED_DEMO=0
PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
NPM_REGISTRY=https://registry.npmmirror.com
CONF
  echo ">> 已生成 $ENV（首次部署）"
fi
C="docker compose -f src/deploy/docker-compose.prod.yml --env-file $ENV --project-directory src/deploy"
echo ">> 构建镜像"
$C build
echo ">> 启动（迁移 → 后端 → 前端）"
if [ "$FIRST" = 1 ]; then SEED_DEMO=1 $C up -d; else $C up -d; fi
$C ps
REMOTE
echo ">> 完成：$REV"
