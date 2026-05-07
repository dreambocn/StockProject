# Docker 单机部署指南

本文档说明如何在一台服务器上使用 Docker Compose 启动 StockProject。当前方案只容器化应用服务，PostgreSQL 和 Redis 使用服务器已有实例。

## 1. 部署结构

- `frontend-nginx`：对外入口，默认暴露 `8080`，托管前端静态资源并反代 `/api/`。
- `backend-api`：FastAPI API 服务，只在 Compose 内部暴露 `8000`。
- `backend-migrate`：一次性迁移任务，执行 `uv run alembic upgrade head`。
- `watchlist-worker`：关注列表后台 Worker。
- `analysis-worker`：分析任务后台 Worker。
- PostgreSQL / Redis：服务器已有实例，不由 Compose 创建。

## 2. 准备环境变量

在仓库根目录复制生产样例：

```powershell
Set-Location 'E:\Development\Project\StockProject'
Copy-Item '.\.env.production.example' '.\.env.production'
```

至少需要替换以下配置：

- `POSTGRES_JDBC_URL`：外部 PostgreSQL 地址，例如 `jdbc:postgresql://host.docker.internal:5432/stockproject`。
- `POSTGRES_USER` / `POSTGRES_PASSWORD`：数据库账号和强密码。
- `REDIS_JDBC_URL` / `REDIS_PASSWORD`：外部 Redis 地址和密码。
- `JWT_SECRET_KEY`：至少 32 位随机字符串。
- `CORS_ALLOW_ORIGINS`：服务器访问地址，例如 `http://服务器IP:8080`。
- `LLM_API_KEY`、`SMTP_PASSWORD`、`TUSHARE_TOKEN`：按功能启用情况填写。

如果密码或密钥中包含 `$`，请在 `.env.production` 中用单引号包住完整值，例如 `SMTP_PASSWORD='abc$def'`。Docker Compose 会对 env 文件做变量插值，不处理会导致 `$xxx` 被当成环境变量名并被替换为空。

如果容器内无法访问 `host.docker.internal`，请把数据库和 Redis 地址替换为宿主机内网 IP 或 Docker 网关 IP。

## 3. 启动服务

先检查 Compose 配置：

```powershell
Set-Location 'E:\Development\Project\StockProject'
docker compose --env-file .\.env.production config
```

构建并启动：

```powershell
docker compose --env-file .\.env.production up -d --build
```

启动后访问：

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8080/api/health/liveness'
Invoke-RestMethod -Uri 'http://127.0.0.1:8080/api/health/readiness'
```

浏览器访问：

```text
http://服务器IP:8080
```

## 4. 查看日志

```powershell
docker compose logs --tail 100 backend-migrate
docker compose logs --tail 100 backend-api
docker compose logs --tail 100 watchlist-worker
docker compose logs --tail 100 analysis-worker
docker compose logs --tail 100 frontend-nginx
```

持续跟踪 API 日志：

```powershell
docker compose logs -f backend-api
```

## 5. 升级发布

拉取或更新代码后重新构建：

```powershell
Set-Location 'E:\Development\Project\StockProject'
docker compose --env-file .\.env.production up -d --build
```

`backend-migrate` 会在 API 和 Worker 启动前执行迁移。生产环境固定使用 `DB_SCHEMA_BOOTSTRAP_MODE=validate_only`，服务启动时只校验迁移版本，不隐式改表。

## 6. 停止服务

```powershell
docker compose down
```

该命令只停止应用容器，不会停止服务器已有的 PostgreSQL 和 Redis。

## 7. 常见问题

- `backend-migrate` 失败：优先检查 `POSTGRES_JDBC_URL`、账号密码、数据库是否已创建，以及容器是否能访问数据库地址。
- `/api/health/readiness` 返回 `fail`：检查返回体里的 `postgres` 和 `redis` 探针错误类型。
- `/api/health/readiness` 返回 `degraded`：通常是 SMTP 未配置，不影响核心 API 可用性。
- 前端能打开但接口失败：确认浏览器访问地址与 `CORS_ALLOW_ORIGINS` 完全一致，并检查 `frontend-nginx` 日志。
- Worker 反复重启：查看对应 Worker 日志，通常与数据库迁移、Redis 鉴权或 LLM 配置有关。
