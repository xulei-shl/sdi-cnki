# 开发任务跟踪

## M9: 数据导出打包、Webhook 通知与磁盘监控 ✅

- [x] M9-01: 创建 `export_task` 模型 + Alembic 迁移
- [x] M9-02: 实现 `export_service.py` (ZIP 打包 + Excel 生成 + metadata.json)
- [x] M9-03: 实现 `export_worker.py` (异步打包 + SSE 推送 + 状态更新)
- [x] M9-04: 实现 `exports.py` 路由 (启动/状态/下载)
- [x] M9-05: 实现 `wecom_notifier.py` (Webhook 推送) + 各 Worker 集成
- [x] M9-06: 实现磁盘空间监控 (lifespan 后台任务)
- [x] M9-07: 前端导出 API + UI (导出全部 + SSE 监听 + 下载 ZIP)
- [x] M9-08: 测试 (导出 + Webhook)
- [x] M9-09: 端到端验证 (TS 0 errors, 测试全通过)

## M10: Docker 部署编排与运维文档 🔄

- [ ] M10-01: 创建 `backend/Dockerfile`（多阶段构建）— **待办：手动测试完成后**
- [ ] M10-02: 创建 `backend/docker-entrypoint.sh` — **待办**
- [ ] M10-03: 创建 `docker-compose.yml` — **待办**
- [ ] M10-04: 创建 `docker/nginx/default.conf` — **待办**
- [ ] M10-05: 更新 `.dockerignore` — **待办**
- [x] M10-06: `docs/deploy/部署运维手册.md` ✅

## 低优先级 V1.1

- [ ] Rate Limiting (5次/分钟防爆破) — `routers/auth.py`
- [ ] LLM 多选拖拽排序组件 — `views/meta-task/index.vue`
