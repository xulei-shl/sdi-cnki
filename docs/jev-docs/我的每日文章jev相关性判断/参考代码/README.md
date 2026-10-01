# 参考代码清单（供外部项目复用「JEV 相关性判断」）

配套文档：[我的每日-JEV评分实现逻辑.md](../我的每日-JEV评分实现逻辑.md)

> 本目录是 `src/` 下源文件的**逐字快照**，仅供阅读与移植参考，**不是可编译代码**（`tsconfig.json` 的 `include` 不含 `docs/`，因此不会被类型检查或参与构建）。源文件变更后此处不会自动同步，**以 `src/` 为准**。核对方式：`git diff --no-index <快照> <源文件>`。

## 一、必读：相关性判断核心

| 快照文件 | 源路径 | 复用到别的项目要看什么 |
|---|---|---|
| `jev.ts` | `src/jev.ts` | **最核心**。`buildJevRequest`（拼 `state` + noul/score/choice 三种提问）、`calculateScore`（`round(noul × score/4 × 100)/100` + `breakdown` + `matched_domain`）、`callJevApi`（超时 / 指数退避抖动 / `Retry-After`）、`isJevResponseFailed`（失败占位判定，**已导出**）。纯逻辑，不依赖 DB / 调度，整段可搬。 |
| `jev-reranker.ts` | `src/vector/jev-reranker.ts` | 同一公式在「检索精排」场景的变体：批量候选打包进一次请求，每候选一对 `noul`+`score`，批级再问一个 `choice` 作显式弃权。可用来对照「多候选怎么组织提问」；注意它的 `choice` 语义与 my-daily 的「领域归因」不同。 |

## 二、主题解析与并发编排

| 快照文件 | 源路径 | 复用到别的项目要看什么 |
|---|---|---|
| `my-daily-scorer-scheduler.ts` | `src/my-daily-scorer-scheduler.ts` | `resolveArticleTopics`（源表 `domain_id` → 单领域优先、多领域回退；**强依赖本仓库 5 张源表 + `topic_domains`/`topic_keywords` 表结构，需按目标项目重写**）、`acquireScoringSlot`/`releaseScoringSlot`（全局 FIFO 互斥，**模块私有**）、`scoreForUser`（唯一对外入口）。 |
| `timezone.ts` | `src/api/timezone.ts` | `buildUtcRangeFromLocalDate`（用户本地自然日 → UTC 闭区间）、`getUserLocalDate` / `getUserTimezone`。跨时区按「日」聚合的场景几乎都要抄。 |

## 三、API 层（协议可直接照搬）

| 快照文件 | 源路径 | 复用到别的项目要看什么 |
|---|---|---|
| `my-daily.routes.ts` | `src/api/routes/my-daily.routes.ts` | SSE 流式评分协议（`start`/`item`/`done`/`info`/`error`）、非流式兼容分支、排队失败 429。 |
| `my-daily.ts` | `src/api/my-daily.ts` | 查询与排序口径（失败项沉底 → 其余按 `relevance_score` 降序）、可评分日期集合、日历状态 `green/yellow/orange/red/future` 判定。 |
| `external-my-daily.routes.ts` | `src/api/routes/external-my-daily.routes.ts` | 对外 API（`ensureScored` 先评分后返回、剔除 `failed` 占位条目、`minScore` / `limit` / `offset` / `fields` / `format`）。**注意分档阈值 `0.7` / `0.3` 在这里和前端各写了一份常量**，移植时别漏。 |
| `external-api-response.ts` | `src/api/external-api-response.ts` | 统一响应信封与错误码表。 |
| `external-auth.ts` | `src/api/external-auth.ts` | API Key（`x-api-key` / `?api_key=`）鉴权 + 角色白名单。 |

## 四、配置与表结构

| 快照文件 | 源路径 | 复用到别的项目要看什么 |
|---|---|---|
| `config.ts` | `src/config.ts` | `TYPESAFE_API_KEY`、`JEV_REQUEST_TIMEOUT_MS`、`JEV_MAX_RETRIES`、`MY_DAILY_ENABLED` / `MY_DAILY_SCHEDULE` / `MY_DAILY_CONCURRENCY`（约 116–130、254–268 行）；检索精排另有 `SEARCH_JEV_*` 四个。 |
| `044_add_user_role_and_daily_scores.sql` | `sql/044_...sql` | `user_daily_scores` 表结构（联合唯一键 `user_id+article_id+score_date`）与索引。 |

## 五、未收录

- `src/public/js/my-daily.js`（54 KB 前端）：只有分档阈值 0.7/0.3 与失败态样式对本主题有参考价值，该阈值已在 `external-my-daily.routes.ts` 中收录，故整份前端未拷贝。
- `src/filter.ts`：只与 `resolveArticleTopics` 共用「源 → 领域」这一**口径**，两者代码彼此独立，评分逻辑无需参考。