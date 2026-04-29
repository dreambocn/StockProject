# P0 计划书 1：Analysis 后端骨架与标准化事件模型

## 目标
- 把 `news_events` 升级为标准化事件母表。
- 新增 `analysis_event_links`、`analysis_reports` 两张分析结果表。
- 提供稳定的 `GET /api/analysis/stocks/{ts_code}/summary` 聚合接口。

## 公共契约
- 响应字段固定为：`ts_code`、`instrument`、`latest_snapshot`、`status`、`generated_at`、`topic`、`published_from`、`published_to`、`event_count`、`events`、`report`。
- `events[]` 最小字段固定为：`event_id`、`scope`、`title`、`published_at`、`source`、`macro_topic`、`event_type`、`event_tags`、`sentiment_label`、`sentiment_score`、`anchor_trade_date`、`window_return_pct`、`window_volatility`、`abnormal_volume_ratio`、`correlation_score`、`confidence`、`link_status`。
- `report` 最小字段固定为：`status`、`summary`、`risk_points`、`factor_breakdown`、`generated_at`。

## 写入范围
- `backend/app/models/news_event.py`
- `backend/app/models/analysis_event_link.py`
- `backend/app/models/analysis_report.py`
- `backend/app/models/__init__.py`
- `backend/app/db/init_db.py`
- `backend/app/schemas/analysis.py`
- `backend/app/services/analysis_repository.py`
- `backend/app/services/analysis_service.py`
- `backend/app/api/routes/analysis.py`
- `backend/app/main.py`
- `backend/tests/test_analysis_routes.py`
- `backend/tests/test_analysis_service.py`
- `backend/tests/test_db_schema.py`

## 分阶段交付
### 阶段 1
- 扩展 `news_events` 字段：`event_type`、`sentiment_label`、`sentiment_score`、`event_tags`、`analysis_status`。
- 新增 `analysis_event_links` 与 `analysis_reports` 模型。
- 在 `init_db.py` 中补齐自动建表与历史库列补齐逻辑。
- 新增 `schemas/analysis.py`、`analysis_repository.py`、`analysis_service.py`、`routes/analysis.py`。
- 路由先返回 DB-first 聚合与空结果回退。

### 阶段 2
- 在不改变公共 schema 的前提下，把计划书 2 的分析服务接回 `analysis_service.py`。
- 保证前端只依赖 `/summary` 契约，不感知内部实现。

## 验收
- `GET /api/analysis/stocks/600519.SH/summary` 对存在股票返回 `200`。
- 无事件时 `events=[]`。
- 无报告时 `report=null`，且 `status` 为 `pending` 或 `partial`。
- `test_db_schema.py` 能证明新表与新列已存在。
