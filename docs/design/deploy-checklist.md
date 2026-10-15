# P1 上线检查单（草稿）
- 先跑数据库迁移，再执行 scripts/setup_db_roles.py 和 python -m app.initial_data，同步权限。
- 抽查接口返回的时间，确认都是带 Z 的 UTC，旧接口也不能还在输出 +08。
- 核对 PM 通知没有重复发（D33），把数据库会话时区设成 UTC 时也要核对。
- EAP 写入的那部分延后测，不算 P1 的阻塞。
- 开批接口改成严格载荷（D40）：上线前确认外部调用方都已改用 carrier_id。

## 2026-10-14 补充
- 时间统一改 UTC：`7cefea0`、`606c4eb`。上线后抽查旧接口（用户、租户、通知、谱系、Hold、Q-Time）的时间都带 Z；Q-Time 通知去重键保持不变，确认不会重复发送。
- D43：上料不拦 PM/待 Qual；开工拦截 `eqp_wait_qual` 必须生效，冒烟测试时验证一次。
- 安全：服务器上的 `.env` 权限设为 600；测试账号不随部署带上线。
- 前端构建时设置 `VITE_API_URL` 指向生产后端；没设会默认连 8000。

- [10/14] 部署后执行 `python -m app.initial_data`，否则 `mes-map-import` 菜单不会下发；只重启服务不够。

- [10/14] 迁移前确认目标库名和 `alembic current`，并在命令里显式覆盖 `MIGRATION_DATABASE_URL`、`DATABASE_URL`，不要只设 `POSTGRES_DB`。
