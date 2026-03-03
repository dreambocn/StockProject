# StockProject 全栈项目

`StockProject` 是一个前后端分离的股票分析项目：

- `frontend/`：`Vue 3` + `Vite` + `TypeScript` + `Element Plus` + `VueUse Motion`
- `backend/`：`FastAPI`（使用 `uv` 管理）

## 已完成功能

### 后端能力

- 完成 Auth V1 全流程：注册、登录、刷新 Token、修改密码、登出、当前用户信息。
- 登录支持用户名或邮箱（`account` 字段）。
- 接入 JWT 鉴权与密码哈希安全模块。
- 接入 Redis 刷新令牌存储。
- 支持登录失败自适应图形验证码：
  - 达到失败阈值后强制验证码
  - 提供验证码获取接口 `GET /api/auth/captcha`
  - 登录接口支持 `captcha_id` 与 `captcha_code`
- 启动时支持自动检查/创建数据库、表与 schema（可配置）。
- 完成请求级日志能力（含 `X-Request-ID`）。

### 前端能力

- 完成认证页面与流程：登录、注册、个人中心、修改密码。
- 接入路由守卫（`guestOnly` / `requiresAuth`）与登录后重定向。
- 完成 Pinia 认证状态管理（含 token 持久化与会话恢复）。
- 完成密码确认与密码强度提示体验。
- 登录页支持验证码挑战展示与刷新。
- 完成 i18n 多语言基础：`zh-CN` 与 `en-US`，默认中文。
- 顶部语言切换支持本地持久化（`localStorage` 的 `app.locale`）。
- 认证相关错误信息已接入本地化映射（包含 422 校验错误首条提示）。
- 头部品牌区与语言切换器已升级为精致产品风：
  - 品牌文案：`AI STOCK LAB` / `by DreamBo`
  - 语言切换器采用胶囊分段样式
  - 已添加滑块式 active 背景动效

## 项目结构

### 前端关键文件

- `frontend/src/router/index.ts`：路由定义
- `frontend/src/router/guards.ts`：路由守卫
- `frontend/src/stores/auth.ts`：认证状态与 token 持久化
- `frontend/src/i18n/index.ts`：多语言初始化与切换
- `frontend/src/App.vue`：全局布局、头部品牌与语言切换

### 后端关键文件

- `backend/main.py`：开发入口（兼容 `fastapi dev main.py`）
- `backend/app/main.py`：FastAPI 应用装配
- `backend/app/api/routes/auth.py`：认证相关路由
- `backend/app/services/auth_service.py`：认证业务逻辑
- `backend/app/services/captcha_service.py`：验证码服务
- `backend/app/core/security.py`：JWT 与密码安全
- `backend/app/core/settings.py`：环境配置解析

## 快速启动

### Windows 一键启动

在项目根目录执行：

```bash
start-dev.bat
```

该脚本会自动拉起后端与前端开发服务。

### 单独启动后端

后端配置文件：`backend/.env`（模板：`backend/.env.example`）。

```bash
cd backend
uv run fastapi dev main.py
```

默认地址：`http://127.0.0.1:8000`

常用登录安全参数（`backend/.env`）：

- `LOGIN_CAPTCHA_THRESHOLD`（默认 `2`）
- `LOGIN_FAIL_WINDOW_SECONDS`（默认 `900`）
- `CAPTCHA_TTL_SECONDS`（默认 `300`）
- `CAPTCHA_LENGTH`（默认 `4`）

### 单独启动前端

先根据 `frontend/.env.example` 创建 `frontend/.env`，然后执行：

```bash
cd frontend
npm run dev
```

默认地址：`http://127.0.0.1:5173`

## Auth API 列表

- `POST /api/auth/register`
- `POST /api/auth/login`（`account` 支持用户名或邮箱）
- `GET /api/auth/captcha`
- `POST /api/auth/refresh`
- `POST /api/auth/change-password`
- `POST /api/auth/logout`
- `GET /api/auth/me`

## 测试与构建

后端测试：

```bash
cd backend
uv run pytest -q
```

前端测试：

```bash
cd frontend
npm run test -- --run
```

前端构建：

```bash
cd frontend
npm run build
```
