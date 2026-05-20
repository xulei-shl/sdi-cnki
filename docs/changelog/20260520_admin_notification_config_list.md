# 开发变更记录

- **日期**: 2026-05-20
- **对应设计文档**: `docs/design/admin_notification_config_list_20260520.md`

## 1. 变更摘要

为 Admin 角色新增「通知配置」管理页面，以列表形式展示所有用户的 Webhook 配置状态（只读）。

## 2. 文件清单

### 新增
- `app/routers/admin_notification_configs.py` — admin-only 列表查询接口 `GET /admin/user-notification-configs`
- `src/api/admin-notification-configs.ts` — 前端 API 调用
- `src/pages/system/notification-configs/index.tsx` — 列表页面组件

### 修改
- `app/main.py` — 注册新 router（前缀 `/api/v1/admin`）
- `src/router.tsx` — 添加路由 `/system/notification-configs`
- `src/components/layout/sidebar.tsx` — 在 admin「设置」区域添加「通知配置」导航项

## 3. 接口说明

```
GET /api/v1/admin/user-notification-configs
Authorization: Bearer <admin_token>
```

返回所有用户的 `user_id`, `username`, `email`, `role`, `is_active`, `webhook_url`, `enabled`, `updated_at`。未配置通知的用户也返回（`webhook_url: null`, `enabled: false`）。

## 4. 测试结果

- [x] TypeScript 类型检查通过（`npx tsc --noEmit`）
- [x] Python 语法检查通过
- [ ] 集成测试（需后端运行后验证）
