# 生产部署

## 架构

`deploy/docker-compose.prod.yml`（compose 项目名 `fsft`）：

| 服务 | 说明 |
| --- | --- |
| `db` | PostgreSQL 17，数据卷 `fsft_pgdata`，不对外暴露端口 |
| `migrate` | 一次性任务：`alembic upgrade head`（postgres 超级用户 / 表 owner）→ `setup_db_roles.py`（创建 / 更新 `app_user`：非 owner、NOBYPASSRLS，行级安全生效）→ `app.initial_data`（菜单同步、默认租户、超级用户）→ 可选 MES 演示数据 |
| `backend` | FastAPI（2 个 worker），以 `app_user` 连接数据库；`QTIME_SWEEP_SECONDS=60` 开启 Q-Time 后台扫描（咨询锁保证多 worker 只执行一次）；上传文件卷 `fsft_uploads` |
| `frontend` | nginx：托管前端静态文件，`/api/` 反向代理到 backend，对外端口 80 |

全部服务 `restart: unless-stopped`（migrate 除外），服务器重启后自动恢复。前端以同源方式访问 `/api`（构建时 `VITE_API_URL=""`）。

## 首次部署 / 更新

在开发机（仓库根目录，已配置到服务器的 SSH 密钥）执行：

```bash
deploy/deploy.sh root@<服务器IP> /opt/fsft
```

脚本会：
1. 用 `git archive HEAD` 打包**已提交**的代码上传到 `/opt/fsft/src`（未提交的修改不会部署）；
2. 首次部署时在服务器生成 `/opt/fsft/.env`（随机 `SECRET_KEY`、postgres / app_user 密码、admin 密码；权限 600，**不进仓库**），并导入 MES 演示数据（含演示通知订阅）；
3. `docker compose build` 后 `up -d`：先跑 migrate，成功后启动 backend、frontend。

之后再次执行同一命令即完成更新：只重建镜像并执行迁移，不会覆盖 `.env`、不会重置数据。

查看 admin 密码（仅服务器）：`grep FIRST_SUPERUSER_PASSWORD /opt/fsft/.env`。注意该变量只在**首次创建**超级用户时生效，之后修改密码请在系统内操作。

## 常用运维命令（服务器）

```bash
cd /opt/fsft
C="docker compose -f src/deploy/docker-compose.prod.yml --env-file .env --project-directory src/deploy"
$C ps                      # 状态
$C logs -f backend         # 后端日志
$C logs migrate            # 迁移日志
$C restart backend
# 重置演示数据（会清除旧演示数据后重新生成）
$C run --rm -e SEED_DEMO=1 migrate
# 备份数据库
$C exec -T db pg_dump -U postgres -Fc app > backup_$(date +%F).dump
```

## 国内网络

- Docker Hub 拉取不稳定时，可先从镜像仓库拉取再打标签，例如：
  `docker pull swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/library/postgres:17 && docker tag ... postgres:17`
  （`python:3.14-slim`、`node:22-alpine`、`nginx:1.27-alpine` 同理）。
- Python 依赖使用 `PIP_INDEX_URL`（默认阿里云）安装 uv，依赖按 `uv.lock` 冻结安装；npm 使用 `NPM_REGISTRY`（默认 npmmirror）。

## 防火墙与 HTTPS

- 服务器若启用 ufw / firewalld 需放行 80（以及将来的 443）；云服务器还需在**安全组**放行 TCP 80。
- 绑定域名后建议在 nginx 前加 HTTPS（如 Caddy / certbot），并把 `.env` 的 `FRONTEND_HOST` 改为 `https://域名` 后重新部署。

## 回滚

`git checkout <旧提交>` 后执行 `deploy/deploy.sh`（数据库迁移只向前，回滚前请先备份并确认迁移兼容）。
