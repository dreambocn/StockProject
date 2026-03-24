# 模型评估与实验页功能分支状态存档

## 分支信息

- 分支名：`codex/evaluation-experiment-page`
- 状态：**未完成**
- 合并状态：**未合并到 `main`**
- 当前定位：管理员只读实验结果中心首版，可用于样本导入、批量评估、页面演示与答辩截图

## 本阶段已完成

- 后端新增评估四表：
  - `analysis_evaluation_datasets`
  - `analysis_evaluation_cases`
  - `analysis_evaluation_runs`
  - `analysis_evaluation_case_results`
- 后端新增管理员只读接口：
  - `GET /api/admin/evaluations/catalog`
  - `GET /api/admin/evaluations/overview`
  - `GET /api/admin/evaluations/cases/{case_key}`
- 后端新增两个脚本：
  - `backend/scripts/import_analysis_evaluation_dataset.py`
  - `backend/scripts/run_analysis_evaluation.py`
- 默认评估样本集已补齐到 `30` 条：
  - `backend/data/evaluations/analysis_eval_dataset_v1.json`
- 前端新增管理员实验评估页：
  - 路由：`/admin/evaluations`
  - 展示：指标卡、ECharts 对比图、改善/退化样本、案例详情抽屉、CLI 空态
- 后台管理中枢已新增“实验评估中心”入口

## 当前未完成项

- 未补“更多历史 run 筛选排序与对比切换体验”
- 未补“导出截图模板 / 论文插图友好模式”
- 未补“公告主导样本补充集”与更细的评估标签体系
- 未补“批量评估运行状态页 / 页面内触发实验”
- 未处理前端构建中的大 chunk 警告优化

## 当前建议的下一阶段

1. 先基于这 `30` 条样本跑一轮 baseline / optimized，对照页面结果修订人工标注
2. 再补一组 `8-12` 条公告主导样本，增强 `announcement` 因子覆盖
3. 补“精选样本子集”与“截图导出模板”，服务答辩展示
4. 如评估结果稳定，再考虑是否合并主线

## 验证记录

- 后端测试：`uv run pytest -q` 通过
- 前端测试：`npm run test -- --run` 通过
- 前端构建：`npm run build` 通过

## 备注

- 本分支当前适合继续迭代，不建议直接视为最终交付版
- 推送远端的目的是保留阶段成果、便于后续继续开发与评审，不代表已经完成合并准备
