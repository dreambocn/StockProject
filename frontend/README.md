# StockProject 前端

这是 `StockProject` 的 Vue 3 + Vite + TypeScript 前端应用，提供股票列表、热点新闻、个股详情、AI 分析工作台、关注列表、个人中心和后台管理界面。项目使用 Element Plus、Pinia、Vue Router、Vue I18n 与 VueUse Motion。

## 常用命令

安装依赖：

```powershell
Set-Location 'E:\Development\Project\StockProject\frontend'
npm install
```

启动开发服务：

```powershell
Set-Location 'E:\Development\Project\StockProject\frontend'
npm run dev
```

运行全部测试：

```powershell
Set-Location 'E:\Development\Project\StockProject\frontend'
npm run test -- --run
```

运行单个测试文件或指定用例：

```powershell
Set-Location 'E:\Development\Project\StockProject\frontend'
npm run test -- --run src/stores/auth.test.ts
npm run test -- --run src/stores/auth.test.ts -t "stores token and user after login"
```

生产构建：

```powershell
Set-Location 'E:\Development\Project\StockProject\frontend'
npm run build
```

## 主要目录

- `src/api/`：后端 API 包装和请求错误处理。
- `src/router/`：页面路由和登录态守卫。
- `src/stores/`：Pinia 状态管理，包含鉴权、主题、政策等状态。
- `src/views/`：核心页面，包括首页、热点新闻、个股详情、分析工作台、关注列表和后台管理。
- `src/i18n/`：中英文文案资源。
- `src/style.css`：全局主题 token、布局基础样式和 Element Plus 主题覆盖。

## 主题与交互

前端支持白天和黑夜主题，默认优先保证白天主题的截图可读性。新增页面或组件时应优先使用语义化主题变量，避免直接写死正文、标题、按钮、卡片和空态颜色。

分析工作台、热点新闻、策略中心和后台页面都包含异步加载、错误提示和空态展示。改动这些页面后，建议同时检查白天和黑夜主题下的正文对比度、卡片摘要和主阅读路径。

## API 依赖

开发环境默认请求本地后端：

```powershell
Set-Location 'E:\Development\Project\StockProject\backend'
uv run fastapi dev main.py
```

常用后端入口：

- `GET /api/stocks`：股票列表。
- `GET /api/news/hot`：热点新闻。
- `GET /api/news/impact-map`：热点影响面板。
- `GET /api/policy/documents`：政策文档列表。
- `POST /api/analysis/stocks/{ts_code}/sessions`：创建分析会话。
- `GET /api/admin/jobs`：后台任务列表。

## 构建说明

`vite.config.ts` 已将 Element Plus、Vue Router、Pinia、Vue I18n 和 VueUse Motion 拆分为稳定 vendor chunk，并提高了合理的包体告警阈值。Vitest 使用 `jsdom` 环境，并内联转换 Element Plus 相关依赖，避免测试时直接加载 CSS 子路径失败。

## 排障入口

- 应用入口：`src/main.ts` 与 `src/App.vue`
- API 请求：`src/api/http.ts`
- 鉴权状态：`src/stores/auth.ts`
- 路由守卫：`src/router/index.ts`
- 主题状态：`src/stores/theme.ts`
- 热点新闻页：`src/views/HotNewsView.vue`
- 分析工作台：`src/views/AnalysisWorkbenchView.vue`
