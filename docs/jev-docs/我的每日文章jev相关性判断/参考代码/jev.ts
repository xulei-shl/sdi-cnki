/**
 * JEV (TypeSafe) 评分服务
 *
 * 调用 TypeSafe API 对文章进行相关性评分。
 * 使用 noul + score + choice 三种问题类型进行综合评分。
 * API 文档：https://docs.typesafe.ai
 */

import { config } from './config.js';
import { logger } from './logger.js';
import { getDb } from './db.js';
import { decryptAPIKey } from './utils/crypto.js';

const log = logger.child({ module: 'jev' });

export const JEV_DEFAULT_API_URL = 'https://api.typesafe.ai/v1/systemone';
export const JEV_DEFAULT_MODEL = 'jev-latest';

/**
 * 将配置里的 base_url 归一为 System One endpoint。
 * 已经是 .../systemone 的原样返回，否则补 /v1/systemone。
 */
export function normalizeJevApiUrl(baseUrl: string): string {
  const trimmed = baseUrl.trim();
  if (trimmed.endsWith('/systemone')) return trimmed;
  return `${trimmed.replace(/\/+$/, '')}/v1/systemone`;
}

export interface ResolvedJevConfig {
  apiUrl: string;
  apiKey: string;
  model: string;
}

/**
 * 解析当前可用的 JEV 配置
 * 优先级：llm_configs 数据库配置（已启用） > .env 环境变量 TYPESAFE_API_KEY
 */
export async function resolveJevConfig(): Promise<ResolvedJevConfig> {
  const db = getDb();

  // 优先从 llm_configs 查找启用的 JEV 配置 (config_type='jev' 或 provider='typesafe')
  // 读取失败（如数据库暂不可用 / 表缺失）不应阻断 env 兜底
  const dbConfig = await db
    .selectFrom('llm_configs')
    .where((eb) =>
      eb.or([
        eb('config_type', '=', 'jev'),
        eb('provider', '=', 'typesafe'),
      ])
    )
    .where('enabled', '=', 1)
    .selectAll()
    .orderBy('is_default', 'desc')
    .orderBy('priority', 'asc')
    .orderBy('created_at', 'asc')
    .limit(1)
    .executeTakeFirst()
    .catch((error) => {
      log.warn({ error }, '读取 llm_configs 中的 JEV 配置失败，回退环境变量');
      return undefined;
    });

  if (dbConfig && dbConfig.api_key_encrypted) {
    const apiKey = decryptAPIKey(dbConfig.api_key_encrypted, config.llmEncryptionKey);
    if (apiKey) {
      return {
        apiUrl: normalizeJevApiUrl(dbConfig.base_url),
        apiKey,
        model: dbConfig.model || JEV_DEFAULT_MODEL,
      };
    }
  }

  // 兜底回退到 .env 配置
  if (config.typesafeApiKey) {
    return {
      apiUrl: JEV_DEFAULT_API_URL,
      apiKey: config.typesafeApiKey,
      model: JEV_DEFAULT_MODEL,
    };
  }

  throw new Error('未配置 JEV API 密钥。请在「设置 -> LLM 配置」中添加 JEV 配置，或在环境变量中配置 TYPESAFE_API_KEY。');
}

/** 主题领域信息 */
export interface TopicInfo {
  name: string;
  description: string | null;
  keywords: string[];
}

/** 文章评分输入 */
export interface ArticleForScoring {
  id: number;
  title: string;
  summary: string | null;
}

/** JEV 评分结果 */
export interface JevScoreResult {
  articleId: number;
  relevanceScore: number;       // 综合评分 0-1
  matchedDomain: string | null; // 匹配的领域名称
  jevResponse: any;             // 原始响应
  failed?: boolean;             // JEV 调用失败时为 true（此时 relevanceScore 是占位 0，不代表真实相关性）
  latencyMs?: number;           // JEV 单次推理耗时毫秒
  breakdown?: {
    noulProb: number;           // is_relevant noul 概率
    scoreLevel: number;         // relevance_level score 等级 0-4
    scoreNormalized: number;    // 归一化得分 0-1
    levelLabel: string;         // 等级说明文案
    candidates?: Array<{ name: string; score: number }>; // 候选领域或选项概率
  };
}

/**
 * 构建 JEV 请求体
 */
function buildJevRequest(
  article: ArticleForScoring,
  topics: TopicInfo[],
  model: string = JEV_DEFAULT_MODEL
) {
  // 构建 state：文章标题 + 摘要
  const articleText = article.summary
    ? `标题：${article.title}\n摘要：${article.summary}`
    : `标题：${article.title}`;

  // 构建主题描述供 JEV 参考
  const topicsDescription = topics.map(t => {
    const kw = t.keywords.length > 0 ? `（关键词：${t.keywords.join('、')}）` : '';
    return `${t.name}${kw}${t.description ? '：' + t.description : ''}`;
  }).join('\n');

  const state = {
    article: articleText,
    user_topics: topicsDescription,
  };

  const questions: Record<string, any> = {
    // noul：二值判断，是否相关
    is_relevant: {
      type: 'noul',
      instructions: '根据 `user_topics` 中描述的主题领域和关键词，判断 `article` 中的文章是否与用户关注的主题相关。',
      criteria: {
        true: '文章内容直接涉及或紧密关联用户关注的主题领域或关键词',
        false: '文章内容与用户关注的主题领域无关，仅表面词汇相似但实质不同',
      },
    },
    // score：细粒度相关程度
    relevance_level: {
      type: 'score',
      instructions: '根据 `user_topics`，评估 `article` 与用户关注主题的相关程度。',
      criteria: [
        '完全不相关，与用户主题无任何关联',
        '边缘相关，仅涉及相邻领域或间接关联',
        '中度相关，涉及用户主题的部分方面',
        '高度相关，直接讨论用户关注的核心主题',
        '完全匹配，深入讨论用户核心主题且包含关键词',
      ],
    },
  };

  // 如果有多个领域，用 choice 判断最匹配哪个
  if (topics.length > 1) {
    const domainCriteria: Record<string, string | null> = {};
    for (const t of topics) {
      domainCriteria[t.name] = t.description || null;
    }
    questions.best_domain = {
      type: 'choice',
      instructions: '`article` 最匹配 `user_topics` 中的哪个主题领域？',
      criteria: domainCriteria,
    };
  }

  return {
    state,
    model,
    questions,
  };
}

/**
 * 判断数据库中持久化的 jev_response 是否代表一次失败的 JEV 调用。
 *
 * scoreArticle 在调用失败时写入 `{ error: message }`，成功时写入完整响应
 * （含 answers / usage）。因此只要解析出 error 字段即视为调用失败——占位 0 分
 * 不代表真实相关性，展示层需要单独标识。
 */
export function isJevResponseFailed(jevResponse: unknown): boolean {
  if (jevResponse == null) return false;

  let parsed: unknown = jevResponse;
  if (typeof jevResponse === 'string') {
    try {
      parsed = JSON.parse(jevResponse);
    } catch {
      return false;
    }
  }

  return (
    typeof parsed === 'object' &&
    parsed !== null &&
    typeof (parsed as { error?: unknown }).error === 'string'
  );
}

/** 重试退避的基准延迟 / 单次退避上限 */
const JEV_RETRY_BASE_DELAY_MS = 1000;
const JEV_RETRY_MAX_DELAY_MS = 30000;

/** 除 5xx 外额外可重试的状态码：429 限流 / 529 过载 / 408 超时 */
const JEV_RETRYABLE_STATUSES = new Set([408, 429, 529]);

function isRetryableStatus(status: number): boolean {
  return status >= 500 || JEV_RETRYABLE_STATUSES.has(status);
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** 解析 Retry-After 响应头（秒数或 HTTP 日期），返回毫秒 */
function parseRetryAfterMs(header: string | null): number | undefined {
  if (!header) return undefined;

  const seconds = Number(header);
  if (Number.isFinite(seconds) && seconds >= 0) return seconds * 1000;

  const dateMs = Date.parse(header);
  if (!Number.isNaN(dateMs)) return Math.max(0, dateMs - Date.now());

  return undefined;
}

/** 指数退避 + 抖动；上游给了 Retry-After 就听它的（仍受单次上限约束） */
function retryDelayMs(attempt: number, retryAfterMs?: number): number {
  if (retryAfterMs !== undefined) return Math.min(retryAfterMs, JEV_RETRY_MAX_DELAY_MS);

  const backoff = Math.min(JEV_RETRY_BASE_DELAY_MS * 2 ** (attempt - 1), JEV_RETRY_MAX_DELAY_MS);
  const jitter = Math.random() * backoff * 0.25;
  return Math.round(backoff + jitter);
}

/**
 * 调用 JEV API
 *
 * 带超时与重试：TypeSafe 在 429 限流 / 529 过载 / 5xx 时要求指数退避后重试
 * （见官方 API reference「Handling rate limits」），否则并发一高就会把限流
 * 记成 0 分。超时通过 AbortController 实现，与 vector/embedding-client 一致。
 */
export async function callJevApi(requestBody: any, jevConfig: ResolvedJevConfig): Promise<any> {
  const maxAttempts = Math.max(1, (config.jevMaxRetries || 0) + 1);
  let lastError: Error = new Error('JEV 请求失败');

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), config.jevRequestTimeoutMs);

    let retryable = true;
    let retryAfterMs: number | undefined;

    try {
      const response = await fetch(jevConfig.apiUrl, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${jevConfig.apiKey}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody),
        signal: controller.signal,
      });

      if (response.ok) {
        return await response.json();
      }

      const errorText = await response.text().catch(() => '');
      lastError = new Error(`JEV API 错误 (${response.status}): ${errorText}`);
      retryable = isRetryableStatus(response.status);
      retryAfterMs = parseRetryAfterMs(response.headers.get('retry-after'));
    } catch (error) {
      // 网络异常 / 超时 / 响应体解析失败都可以重试
      lastError = error instanceof Error ? error : new Error(String(error));
      const isTimeout = lastError.name === 'AbortError';
      lastError = new Error(
        isTimeout ? `JEV 请求超时（${config.jevRequestTimeoutMs}ms）` : lastError.message
      );
    } finally {
      clearTimeout(timer);
    }

    if (!retryable || attempt === maxAttempts) {
      throw lastError;
    }

    const delay = retryDelayMs(attempt, retryAfterMs);
    log.warn(
      { attempt, maxAttempts, delay, error: lastError.message },
      'JEV 请求失败，退避后重试'
    );
    await sleep(delay);
  }

  throw lastError;
}

/**
 * 计算综合评分
 *
 * 算法：noul 概率 × score 归一化值
 * - noul 提供粗粒度的相关/不相关判断
 * - score 提供细粒度的相关程度
 * - 两者相乘后，不相关的文章分数会被压到很低
 *
 * 领域归属：单领域提问（含按文章来源绑定领域的情形）归属是确定的，直接取该
 * 领域；只有多领域回退提问时才由 choice 答案决定。
 */
const RELEVANCE_LEVEL_LABELS = [
  '完全不相关',
  '边缘相关',
  '中度相关',
  '高度相关',
  '完全匹配',
];

function calculateScore(
  answers: any,
  topics: TopicInfo[]
): { score: number; matchedDomain: string | null; breakdown: JevScoreResult['breakdown'] } {
  const noulProb = typeof answers.is_relevant?.noul === 'number' ? answers.is_relevant.noul : 0;
  const scoreValue = typeof answers.relevance_level?.score === 'number' ? answers.relevance_level.score : 0;
  const maxLevel = 4; // score criteria 有 5 个等级 (0-4)
  const normalizedScore = scoreValue / maxLevel;

  // 综合评分：noul 概率 × 归一化 score
  const relevanceScore = Math.round(noulProb * normalizedScore * 100) / 100;

  const matchedDomain =
    topics.length === 1 ? topics[0].name : answers.best_domain?.choice ?? null;

  const levelIdx = Math.min(Math.max(Math.round(scoreValue), 0), 4);
  const levelLabel = RELEVANCE_LEVEL_LABELS[levelIdx] || '未知';

  // 候选选项分布
  const candidates: Array<{ name: string; score: number }> = [];
  if (answers.best_domain?.distribution && typeof answers.best_domain.distribution === 'object') {
    for (const [name, prob] of Object.entries(answers.best_domain.distribution)) {
      candidates.push({ name, score: typeof prob === 'number' ? Math.round(prob * 100) / 100 : 0 });
    }
  } else if (topics.length > 0) {
    for (const t of topics) {
      candidates.push({
        name: t.name,
        score: t.name === matchedDomain ? relevanceScore : Math.round(((1 - relevanceScore) / Math.max(1, topics.length - 1)) * 100) / 100,
      });
    }
  }

  return {
    score: relevanceScore,
    matchedDomain,
    breakdown: {
      noulProb: Math.round(noulProb * 100) / 100,
      scoreLevel: scoreValue,
      scoreNormalized: Math.round(normalizedScore * 100) / 100,
      levelLabel,
      candidates,
    },
  };
}

/**
 * 对单篇文章进行 JEV 评分
 */
export async function scoreArticle(
  article: ArticleForScoring,
  topics: TopicInfo[],
  jevConfig?: ResolvedJevConfig
): Promise<JevScoreResult> {
  const startTime = Date.now();
  try {
    const activeConfig = jevConfig || (await resolveJevConfig());
    const requestBody = buildJevRequest(article, topics, activeConfig.model);
    const result = await callJevApi(requestBody, activeConfig);
    const latencyMs = Date.now() - startTime;
    const { score, matchedDomain, breakdown } = calculateScore(result.answers, topics);

    return {
      articleId: article.id,
      relevanceScore: score,
      matchedDomain,
      jevResponse: result,
      failed: false,
      latencyMs,
      breakdown,
    };
  } catch (error) {
    const latencyMs = Date.now() - startTime;
    log.error({ articleId: article.id, error }, 'JEV 评分失败');
    return {
      articleId: article.id,
      relevanceScore: 0,
      matchedDomain: null,
      jevResponse: { error: error instanceof Error ? error.message : 'unknown' },
      failed: true,
      latencyMs,
    };
  }
}

export type OnArticleScoredCallback = (
  result: JevScoreResult,
  index: number,
  total: number
) => Promise<void> | void;

/**
 * 批量并行评分（按并发数分批处理）
 *
 * 每篇文章使用的主题由 `getTopics` 决定：通常是该文章来源绑定的单个领域，
 * 解析不出绑定领域时回退到用户的全部激活领域，因此同一批文章可以带着不同
 * 的主题交给 JEV。
 */
export async function scoreArticlesBatch(
  articles: ArticleForScoring[],
  getTopics: (article: ArticleForScoring) => TopicInfo[],
  concurrency = 5,
  onArticleScored?: OnArticleScoredCallback
): Promise<JevScoreResult[]> {
  // 解析一次 JEV 配置供本批次共用
  const jevConfig = await resolveJevConfig();

  log.info(
    { count: articles.length, concurrency, model: jevConfig.model, url: jevConfig.apiUrl },
    '开始批量 JEV 评分'
  );

  // 按并发数分批处理
  const results: JevScoreResult[] = [];
  let completedCount = 0;

  for (let i = 0; i < articles.length; i += concurrency) {
    const batch = articles.slice(i, i + concurrency);
    const batchResults = await Promise.all(
      batch.map(async (article) => {
        const res = await scoreArticle(article, getTopics(article), jevConfig);
        completedCount++;
        if (onArticleScored) {
          try {
            await onArticleScored(res, completedCount, articles.length);
          } catch (callbackErr) {
            log.error({ articleId: article.id, error: callbackErr }, '评分进度回调执行出错');
          }
        }
        return res;
      })
    );
    results.push(...batchResults);
  }

  const failedCount = results.filter(r => r.failed).length;
  log.info(
    {
      total: results.length,
      scored: results.length - failedCount,
      failed: failedCount,
    },
    'JEV 评分完成'
  );

  return results;
}

