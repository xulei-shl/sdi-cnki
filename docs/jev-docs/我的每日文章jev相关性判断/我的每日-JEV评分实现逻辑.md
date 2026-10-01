# 我的每日 — JEV 评分实现逻辑

> 对应初始需求：[我的每日-初始需求.md](./我的每日-初始需求.md)
>
> 主要代码：`src/jev.ts`（JEV 调用与评分）、`src/my-daily-scorer-scheduler.ts`（调度与并发控制）、`src/api/my-daily.ts`（查询）、`src/api/routes/my-daily.routes.ts`（路由）、`src/api/routes/external-my-daily.routes.ts`（对外 API）、`src/public/js/my-daily.js`（前端展示）、`src/public/js/components/calendar-picker.js`（日历圆点）。
>
> 仓库内另有一处**同口径**的相关性判断实现（语义检索精排，`finalScore = noul × (score / 4)`）：`src/vector/jev-reranker.ts`，见第 9 节。

## 1. 问题类型：noul / choice / score 三种按需组合

JEV 支持 `noul`、`choice`、`score` 三种问题模式。本模块对每篇文章的**一次** JEV 调用中按情况组合使用三种模式（`src/jev.ts` `buildJevRequest`）；按来源绑定领域时只问 `noul` + `score`，回退到多领域时才追加 `choice`：

| 问题 key | 类型 | 作用 | 触发条件 |
|---|---|---|---|
| `is_relevant` | `noul` | 二值判断：文章是否与所给主题相关 | 始终使用 |
| `relevance_level` | `score` | 细粒度相关程度（0–4 五档） | 始终使用 |
| `best_domain` | `choice` | 从多个主题领域中选出最匹配的一个 | 仅当该篇回退到多领域评分（用户配置了 ≥2 个激活主题领域）时 |

三种模式的分工：`noul` 提供粗粒度的「相关 / 不相关」概率门控，`score` 提供细粒度的相关程度，`choice` 提供领域归因打标。三者各自独立提问，由前端综合算法汇总为一个分数。

## 2. 请求构建

### 2.1 state（输入维度）

```js
{
  article: "标题：<title>\n摘要：<summary>",   // 无摘要时只有标题
  user_topics: "<领域名>（关键词：a、b）：<描述>\n..."
}
```

- `article`：文章原文标题 + 摘要（中文翻译 `title_zh` / `summary_zh` 不参与评分，仅用于前端展示）。**不截断**，摘要全文进 prompt。
- `user_topics`：**该篇文章的来源绑定领域**（优先），解析不出时才回退到用户全部**激活**主题领域（`topic_domains.is_active = 1`）及其激活关键词（`topic_keywords.is_active = 1`）。详见 2.3。
- `user_topics` 每行的拼装规则（`buildJevRequest`）：`领域名` +（有激活关键词时 `（关键词：a、b）`）+（有描述时 `：描述`）。关键词与描述都为空时行内没有冒号。领域间用换行连接。

### 2.2 questions（打分指标与标准）

**`noul` — `is_relevant`（是否相关）**

| 取值 | 判断标准 |
|---|---|
| `true` | 文章内容直接涉及或紧密关联用户关注的主题领域或关键词 |
| `false` | 文章内容与用户关注的主题领域无关，仅表面词汇相似但实质不同 |

**`score` — `relevance_level`（相关程度，0–4 五档）**

| 分值 | 标准 |
|---|---|
| 0 | 完全不相关，与用户主题无任何关联 |
| 1 | 边缘相关，仅涉及相邻领域或间接关联 |
| 2 | 中度相关，涉及用户主题的部分方面 |
| 3 | 高度相关，直接讨论用户关注的核心主题 |
| 4 | 完全匹配，深入讨论用户核心主题且包含关键词 |

**`choice` — `best_domain`（最匹配领域，多领域回退时）**

- 选项为每个领域名，选项描述为该领域的 `description`（无描述则为 `null`）。
- 提问：`article` 最匹配 `user_topics` 中的哪个主题领域？

### 2.3 主题来源：优先按文章来源绑定领域

复用 LLM 过滤模块的「源 → 单领域」**口径**（`src/filter.ts` `llmFilter` 用的是同一套绑定关系），但 `resolveArticleTopics` **不调用** `llmFilter`，而是自己按来源类型批量反查源表，两处代码彼此独立：

- 文章的 `source_origin` 指向的源表（`rss_sources` / `journals` / `keyword_subscriptions` / `email_sources` / `web_sources`）都绑定了 `domain_id`（见 `sql/037`、`sql/041`）。
- 评每篇文章时，`resolveArticleTopics`（`src/my-daily-scorer-scheduler.ts`）先按 `source_origin` 把文章分到对应源表、批量 `WHERE id IN (...)` 反查 `domain_id`，再用 `getTopicDomainById(domainId, userId)` 做**所有权校验**（必须属于当前用户）。校验通过则**只把这一个领域及其激活关键词**发给 JEV；判断更聚焦、prompt 更小，领域归属也直接确定（不再需要 `choice`）。
- **回退**：源未绑定领域 / 领域已删除 / 领域不属于该用户时，回退到用户全部激活领域（改造前的行为），保证文章仍能拿到分数；回退篇数在 `开始 JEV 评分` 日志中以 `fallbackCount` 单独报告（>0 时另打一条 warn）。
- 绑定领域**不做 `is_active` 过滤**——它是源上显式做出的归档选择；关键词沿用 filter 模块口径，只取激活关键词（`getActiveKeywordsForDomain`）。

## 3. 综合评分算法（`calculateScore`）

```
relevanceScore = round(noul概率 × (score值 / 4) × 100) / 100
```

- `noul` 概率 ∈ [0, 1] 作为门控；`score` 归一化到 [0, 1] 作为程度。
- 两者相乘：被判为「不相关」的文章，即使 score 打高分也会被压到接近 0。
- 结果保留两位小数，范围 0–1；前端展示为百分比（`★ 85%`）。
- `matched_domain`：单领域提问（含来源绑定领域）时直接取该领域名；多领域回退时取 `choice` 答案——若 `answers.best_domain.choice` 缺失则为 `null`（**不会**退回某个领域）。
- 字段缺失兜底：`is_relevant.noul` / `relevance_level.score` 不是 number 时按 `0` 处理。这类情况 `failed = false`，即**会被当成真实的 0 分低相关**，与「JEV 调用失败」是两回事——复用时若要区分，需要额外判断 `answers` 是否存在。

### 3.1 `breakdown` 明细（随 SSE `item` 事件下发，前端 HUD 直接消费）

| 字段 | 含义 |
|---|---|
| `noulProb` | `is_relevant.noul`，四舍五入两位 |
| `scoreLevel` | `relevance_level.score` 原值 0–4 |
| `scoreNormalized` | `scoreLevel / 4`，两位小数 |
| `levelLabel` | 按 `round(scoreValue)` 夹到 [0,4] 取 `RELEVANCE_LEVEL_LABELS`（完全不相关 / 边缘相关 / 中度相关 / 高度相关 / 完全匹配） |
| `candidates` | 领域概率分布。有 `answers.best_domain.distribution` 时直接取；否则**合成**：命中领域填 `relevanceScore`，其余领域均分 `(1 - relevanceScore) / (topics.length - 1)` |

### 3.2 失败占位

JEV 调用失败（`scoreArticle` catch 分支）时返回 `relevanceScore = 0`、`matchedDomain = null`、`jevResponse = { error: message }`、`failed: true`、`latencyMs` 仍为真实耗时——占位 0 分不代表真实相关性，展示层需单独标识（见第 7 节）。

原始响应完整 JSON 存入 `user_daily_scores.jev_response`，便于事后审计与调参；前端读取它还原 `noulProb` / `scoreNormalized`（`jev_response` 本身也会随 `/api/my-daily` 查询一并返回）。

## 4. 数据存储

`user_daily_scores` 表（`sql/044_add_user_role_and_daily_scores.sql`）：

| 字段 | 说明 |
|---|---|
| `user_id` + `article_id` + `score_date` | 联合唯一键；重复评分时 upsert 覆盖 |
| `relevance_score` | 综合评分（REAL，0–1） |
| `matched_domain` | 匹配的主题领域名称（可空） |
| `jev_response` | JEV 原始响应 JSON（TEXT）。成功时为完整响应（含 `answers` / `usage`）；失败时为 `{ error: message }`，是判定该条是否调用失败的持久化依据（`isJevResponseFailed`） |

日期口径：`score_date` 是**用户时区下的本地自然日**（YYYY-MM-DD）。查询文章时先换算成对应 UTC 区间（`buildUtcRangeFromLocalDate`）再按 `created_at` 过滤：`created_at >= 当日 00:00:00.000 本地` **且** `created_at <= 当日 23:59:59.999 本地`（两端都是闭区间，见 `getTodayArticles`），避免凌晨抓取的文章被拆到两天。

覆盖范围：**不过滤 `filter_status`**——需求要求 JEV 对当日所有新增文章评分打标（低分灰显），已过关键词预过滤的文章也参与评分。

## 5. 调度与并发控制（`my-daily-scorer-scheduler.ts`）

### 5.1 定时任务

- cron 表达式默认 `30 7 * * *`（每日 07:30），可通过 `MY_DAILY_SCHEDULE` 配置。
- 遍历所有 `role='user'` 的用户，**串行**逐个评分；日期按各用户时区的当天计算（`getUserLocalDate`）。
- 未配置 JEV 密钥时跳过整个任务（不报错）。
- `MY_DAILY_ENABLED=false` **只关闭 cron 注册**（`src/index.ts`），手动「重新评分」与外部 API 触发的手动评分不受该开关影响。

### 5.2 全局互斥与排队（`acquireScoringSlot` / `releaseScoringSlot`）

> 注意：`acquireScoringSlot` / `releaseScoringSlot` / `runScoringForUser` 都是**模块私有**函数，没有导出。跨项目复用时能拿到的只有 `scoreForUser(userId, username, date, onProgress?)`、`hasActiveTopics(userId)`、`ScoringQueueError` 三个导出。

- 全局同一时刻只允许**一个**评分任务执行（不分用户），定时任务与多个用户手动点击「重新评分」共用同一把锁。
- 重叠触发按 **FIFO** 排队：名额释放时 `releaseScoringSlot` 直接把名额转交给队首（转交瞬间就写入 `activeScoringJob`），新请求无法插队。
- 同一 `(userId, date)` 已在执行或排队时，重复触发直接返回 `skipped: reason='duplicate'`。
- 排队上限 10 个（超出抛 `ScoringQueueError('queue_full')`），最长等待 10 分钟（超时抛 `ScoringQueueError('wait_timeout')`），避免请求无限挂起。
- 定时任务逐用户串行时也会走同一把锁：某用户排队失败（`ScoringQueueError`）只记 warn 并跳过该用户，不中断整轮任务。

### 5.3 文章级并发

- 单个用户内按 `MY_DAILY_CONCURRENCY`（默认 5）分批并行调用 JEV。
- 每批内 `Promise.all` 等全部完成后进入下一批；每篇完成即触发回调（写库 + SSE 推送）。

### 5.4 重试与失败处理（`callJevApi`）

- 带超时（`JEV_REQUEST_TIMEOUT_MS`，默认 30s，AbortController 实现）。
- 最多重试 `JEV_MAX_RETRIES`（默认 2）次，即最多 `retries + 1` 次尝试。
- 可重试条件：5xx、408 / 429 / 529、网络异常、超时、响应体解析失败；4xx（除上述三个）不重试直接抛出。按指数退避 + 抖动（1s 起步，倍数 2，单次上限 30s），优先遵循响应头 `Retry-After`（同样受 30s 上限约束）。
- 单篇最终失败不阻塞批次：写占位 0 分（`failed: true`），完成后在 `done` 事件中单独报告 `failed` 数。
- **配置解析失败 ≠ 单篇失败**：`scoreArticlesBatch` 在批次开始时统一 `resolveJevConfig()`，未配置密钥会直接抛异常（整批不执行），不会被降级成单篇 0 分。
- `done.scored = inserted - failedCount`：写库失败的条目既不计入 `scored` 也不计入 `failed`。

## 6. API 层（`/api/my-daily`）

所有路由都经过 `requireAuth` + `requireUser`（要求 `role` 为 `user` 或 `admin`），且一律按 `req.userId` 过滤，**无法查看他人评分**。

| 路由 | 方法 | 说明 |
|---|---|---|
| `/api/my-daily?date=` | GET | 查询指定日期的评分文章（联表 articles + translations）；每条附带 `failed` 标志与原始 `jev_response`，失败项沉底，其余按 `relevance_score` 降序；`date` 缺省为用户时区当天 |
| `/api/my-daily/dates` | GET | 返回 `{ dates, scoredDates, today }`：`dates` = 已有评分结果的日期 ∪ 最近 30 个自然日内有新增文章的日期（去重、倒序、上限 30）；`scoredDates` 仅已有评分记录的日期；`today` 为用户时区当天 |
| `/api/my-daily/calendar-status?month=` | GET | 指定月份每日状态（`green`/`yellow`/`orange`/`red`/`future`）、`hasArticles` / `isScored` / `articleCount` / `failedCount`；`month` 非法或缺省时用用户时区当月 |
| `/api/my-daily/refresh` | POST | 手动触发当前用户评分；`Accept: text/event-stream` 时走 SSE 流式，否则走传统 JSON。可选 body `date`（缺省用户时区当天） |

**`/api/my-daily/refresh` 非流式返回分支**：`no_topics` → 400 引导配置主题；`no_articles` / `duplicate` → 200 带 message 的 `success: true`；`ScoringQueueError` → **429** 且 body 带 `reason`（`queue_full` / `wait_timeout`）；其余异常 → 500。

**SSE 流式评分**（前端「Jev 评分」按钮）推送三类事件：

| 事件 | 时机 | 载荷 |
|---|---|---|
| `start` | 评分开始 | `{ type, total }` |
| `item` | 每篇出分 | `{ type, current, total, latencyMs?, breakdown?, article: { id, title, url, summary, source_origin, filter_status, published_at, created_at, title_zh, summary_zh, relevance_score, matched_domain, failed } }`（`latencyMs` / `breakdown` 见 3.1；`failed: true` 表示该篇 JEV 调用失败，分数为占位 0） |
| `done` | 全部完成 | `{ type, total, scored, failed }` |

另有 `info`（`no_articles` / `duplicate`）与 `error`（未配置主题、排队失败含 `statusCode: 429`、JEV 异常）事件。前端收到 `item` 即插入卡片并按分数动态重排（FLIP 动画），直到全部完成。

### 6.1 对外 API（`/api/external/my-daily`）

`src/api/routes/external-my-daily.routes.ts` 是给外部项目 / agent 用的统一信封接口，鉴权走 `verifyExternalApiAuth`（Header `x-api-key` 或 query `api_key`，对齐服务端 `CLI_API_KEY`，允许 `admin` / `user`），响应统一由 `src/api/external-api-response.ts` 包装（`success` / `code` / `message` / `data` / `meta`），详见 `docs/我的每日外部API调用说明.md`。

| 路由 | 方法 | 说明 |
|---|---|---|
| `/api/external/my-daily` | POST | 查询（必要时先触发评分后返回）；参数可放 body 或 query |
| `/api/external/my-daily/export` | GET | 全量 JSON 附件导出（`Content-Disposition: attachment`） |

关键行为：

- **先确保已评分**（`ensureScored`）：该日期已有任意一条 `user_daily_scores` 记录 → 直接返回缓存（`meta.execution = { triggered: false, reason: 'already_scored' }`）；否则依次校验「有激活主题领域」（否则 400 `NO_TOPIC_CONFIGURED`）、「已配置 JEV 密钥」（否则 503 `JEV_NOT_CONFIGURED`），再 `scoreForUser` 同步跑一遍。成功评分返回 `reason: 'executed'`、无文章返回 `reason: 'no_articles'`；**注意**「评分进行中」不是 `execution.reason`，而是直接返回 409 `SCORING_IN_PROGRESS` 错误信封——类型里声明的 `'in_progress'` 目前没有任何代码路径会产生。
- **严格剔除失败占位条目**：结果过滤 `article.failed === true`，再按 `minScore` 过滤。
- 分页与裁剪：`limit` 默认 5、上限 100；`offset` 默认 0；`fields` 默认 `core`（无摘要等长文本、体积小），`full` 附带摘要与内部字段；`format=json_file` 直接输出全量 JSON 附件。
- 每条附带 `relevance_level: 'high' | 'medium' | 'low'`，阈值与前端一致（`HIGH_SCORE_THRESHOLD = 0.7`、`MEDIUM_SCORE_THRESHOLD = 0.3`，见该文件常量）。
- 错误码：日期格式非法 400、主题未配置 400、JEV 未配置 503、评分进行中 409、排队满 / 排队超时 429（`retryable: true`）、其余 500。

## 7. 前端展示分档（`my-daily.js`）

| 档位 | 阈值 | 展示 |
|---|---|---|
| 高度相关 | score ≥ 0.7 | 正常高亮徽章 |
| 中度相关 | 0.3 ≤ score < 0.7 | 正常徽章 |
| 低相关 | score < 0.3 | 徽章为 low 样式，整卡 `is-low-score` **灰显** |

工具栏统计三类数量（高 / 中 / 低），三项之和必须等于**成功出分**的文章数（失败项不计入，不一致时控制台报错）。摘要展示优先中文翻译（`summary_zh`），超过 400 字折叠。

### 7.1 JEV 调用失败态的展示

失败判定统一由 `isJevResponseFailed(jev_response)` 给出（`jev_response` 为 JSON 字符串或已解析对象均可；解析后 `error` 字段是**字符串**才算调用失败），前端不再把占位 0 分当作真实低分：

- **文章卡片**：显示红色「⚠ 评分失败」徽标（不再显示 `★ 0%`），整卡加 `is-score-failed` 红边弱化；失败项在列表中统一**沉底**，且**不计入**高/中/低相关分档统计。
- **决策中枢 HUD**：失败项标记为「调用失败」，不为其编造延迟、不计入延迟遥测与散点、不参与分档分布；状态标签显示「全部失败 (N篇)」/「部分失败 (N篇)」，全部失败时延迟指标显示 `--`。
- **日历组件**（`src/public/js/components/calendar-picker.js`）：图例新增橙色「评分失败」；某天已调用 JEV 但一篇都没拿到真实分数时显示**橙色圆点**（`orange`），tooltip「JEV 评分失败（N篇），可重新评分」；部分失败仍为绿点。

失败标志随 `/api/my-daily` 查询与 SSE `item` 事件下发；日历另有 `/api/my-daily/calendar-status` 返回的 `failedCount`。

> **复用时的已知取舍——延迟数据在归档视图里是合成的**：`latencyMs` 只存在于 SSE 实时事件中，**没有落库**。刷新页面走 `GET /api/my-daily` 后，HUD 用 `55 + (article.id % 45)` 伪造延迟（`loadArchivedScores`）。因此 HUD 的延迟遥测（avg / p50 / p95 / 散点）只在评分刚跑完的那次会话内有意义。要在别的项目里展示真实延迟，需要自己把 `latencyMs` 一起持久化。

## 8. 配置项（`src/config.ts`）

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `TYPESAFE_API_KEY` | — | JEV 兜底密钥（优先用 llm_configs 数据库配置） |
| `JEV_REQUEST_TIMEOUT_MS` | `30000` | 单次请求超时 |
| `JEV_MAX_RETRIES` | `2` | 最大重试次数 |
| `MY_DAILY_ENABLED` | `true` | 是否启用定时评分（`false` 只关闭 cron 注册，不影响手动触发） |
| `MY_DAILY_SCHEDULE` | `30 7 * * *` | 定时 cron 表达式 |
| `MY_DAILY_CONCURRENCY` | `5` | 单用户内文章并行评分并发数 |

JEV 配置解析优先级（`resolveJevConfig`）：`llm_configs` 表中 `config_type='jev'`（或 `provider='typesafe'`）且 `enabled = 1` 的配置（按 `is_default desc, priority asc, created_at asc` 取第一条，且 `api_key_encrypted` 能解出密钥）> `.env` 的 `TYPESAFE_API_KEY`。数据库读取失败（如表缺失）会降级到环境变量而不是抛错；两者皆无时抛错并引导用户到「设置 → LLM 配置」添加。走数据库配置时 `base_url` 会被 `normalizeJevApiUrl` 归一为 System One endpoint（不以 `/systemone` 结尾则补 `/v1/systemone`），`model` 缺省 `jev-latest`；走环境变量兜底时固定用 `https://api.typesafe.ai/v1/systemone` + `jev-latest`。

## 9. 同口径的另一处实现：语义检索 JEV 精排

`src/vector/jev-reranker.ts`（被 `src/vector/search-service.ts` 使用）是同一套相关性判断公式在**检索精排**场景的复用，与本文档第 1–3 节可以直接对照：

- 综合分口径完全相同：`finalScore = noul × (score / 最高档位)`，0–4 五档描述 `RELEVANCE_LEVELS` 与本模块 `relevance_level` 一致。
- 差异在提问结构：把**一批候选**（`SEARCH_JEV_BATCH`，默认 20）放进同一次请求的 `results[i]` 共享 state，每候选问一对 `r{i}`（noul）+ `s{i}`（score），再在批级额外问 1 个 `choice` 作为「本批是否至少有一条真正涉及该主题」的**显式弃权**信号——与本模块「多领域时用 `best_domain` 做领域归因」的 `choice` 用途不同。
- 答案解析更保守：`noul` / `score` 任一缺失或非有限数就整条丢弃（`parseJevRerankAnswers` 中 `continue`），不像 `calculateScore` 那样兜底成 0 分。
- 独立的开关与配额：`SEARCH_JEV_ENABLED`（默认开）、`SEARCH_JEV_BATCH`（默认 20）、`SEARCH_JEV_MAX_CANDERS`（默认 50，源码中就是这个拼写）、`SEARCH_JEV_WEIGHT`（与向量相似度的融合权重）。密钥解析是**两级**：先按 userId 取用户的 `jev` 配置（`getActiveConfigByType`），读失败再回退本模块的全局 `resolveJevConfig()`，都没有则**静默跳过 JEV 精排**（返回 `null`，不抛错、不影响原排序）。

## 10. 复用到其他项目时的最小依赖集

相关性判断逻辑本身不依赖本仓库的 DB / 调度，只依赖 HTTP 调用，可以整段搬走：

| 需要的能力 | 本仓库位置 | 是否自包含 |
|---|---|---|
| 提问拼装（noul / score / choice + `state` 格式） | `src/jev.ts` `buildJevRequest` | 是，纯函数（未导出，需自行拷贝或改为导出） |
| 评分公式 + `breakdown` + `matched_domain` | `src/jev.ts` `calculateScore` | 是，纯函数（未导出） |
| 超时 / 重试 / `Retry-After` / 退避抖动 | `src/jev.ts` `callJevApi` | 依赖 `config.jevRequestTimeoutMs` / `config.jevMaxRetries` 两个常量 |
| 失败占位语义 + 判定 | `JevScoreResult.failed` + `isJevResponseFailed`（**已导出**） | 是 |
| 分档阈值 0.7 / 0.3 | 前端 `my-daily.js` 与 `external-my-daily.routes.ts` **各写一份常量** | 重复定义，搬运时注意别漏 |
| 单领域优先 + 多领域回退 | `resolveArticleTopics` | 强依赖本仓库的 5 张源表 + `topic_domains` / `topic_keywords` 表结构，需要按目标项目的数据模型重写 |

需要一并带走的三个已知取舍：① 领域归属靠源表绑定（`domain_id`），不是靠模型判断；② 失败与「真实 0 分」在 DB 里长得一样，必须靠 `jev_response.error` 区分；③ 推理耗时未持久化。
