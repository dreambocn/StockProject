# StockProject 环境矩阵

## 环境默认值

| 环境 | `APP_ENV` | `DB_SCHEMA_BOOTSTRAP_MODE` | `INIT_ADMIN_ENABLED` | 说明 |
| --- | --- | --- | --- | --- |
| 本地开发 | `development` | `auto_apply` | `false` | 允许自动建库/建 schema/执行迁移，适合快速起本地环境 |
| 测试 / CI | `test` | `validate_only` | `false` | 先显式执行 `alembic upgrade head`，启动时只做版本校验 |
| 预发 | `staging` | `validate_only` | `false` | 禁止服务启动隐式改表，部署前必须先跑迁移 |
| 生产 | `production` | `validate_only` | `false` | 强制迁移前置，禁止初始化管理员副作用 |

## 最低必填配置

- `APP_ENV`
- `DB_SCHEMA_BOOTSTRAP_MODE`
- `POSTGRES_JDBC_URL`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `REDIS_JDBC_URL`
- `JWT_SECRET_KEY`

## 迁移治理规则

### 开发环境

- 允许 `DB_SCHEMA_BOOTSTRAP_MODE=auto_apply`
- API / Analysis Worker / Watchlist Worker 启动时统一执行 `ensure_database_schema()`
- 若本地切为 `validate_only`，启动前必须先手工执行：

```powershell
Set-Location 'E:\Development\Project\StockProject\backend'
uv run alembic upgrade head
```

### CI / 预发 / 生产

- 固定使用 `DB_SCHEMA_BOOTSTRAP_MODE=validate_only`
- 部署顺序必须为：
  1. `uv sync --group dev`
  2. `uv run alembic upgrade head`
  3. 启动 API / Worker
- 服务启动只校验迁移版本，不执行 DDL

## 管理员初始化

- `INIT_ADMIN_ENABLED` 仅建议在本地显式开启
- 即使配置了 `INIT_ADMIN_*`，如果 `INIT_ADMIN_ENABLED=false` 也不会创建管理员
- 预发/生产默认关闭，避免误建弱口令账号
