/**
 * 「我的每日」外部 API 路由
 *
 * 供外部项目 / agent 查询指定用户的 JEV 每日评分：
 * - 统一 API Key 鉴权（Header x-api-key 或 query api_key 对齐服务端 CLI_API_KEY）
 * - 支持 username（用户名）与 userId 双轨兼容输入，无需传 password
 * - 默认返回 limit: 5 条最相关文献（双轨分离：默认轻量感知轨，体积严格 < 1KB）
 * - 默认 fields: "core"，自动剔除长摘要与内部状态字段，自动剔除 failed: true 占位条目
 * - 支持 exportUrl / format=json_file 全量 JSON 导出（留存轨）
 * - 支持指定日期（默认用户时区下的当天）与 minScore 过滤
 * - 已评分则直接返回结果，未评分则触发评分后再返回
 *
 * 所有响应都使用 src/api/external-api-response.ts 中的统一信封，
 * 详见 docs/我的每日外部API调用说明.md。
 */

import express from 'express';
import type { Response } from 'express';
import type { AuthRequest } from '../../middleware/auth.js';
import { logger } from '../../logger.js';
import { getDb } from '../../db.js';
import { resolveJevConfig } from '../../jev.js';
import { getDailyArticles } from '../my-daily.js';
import { getUserLocalDate } from '../timezone.js';
import { scoreForUser, hasActiveTopics, ScoringQueueError } from '../../my-daily-scorer-scheduler.js';
import { verifyExternalApiAuth, type ExternalAuthUser } from '../external-auth.js';
import {
  EXTERNAL_API_CODES,
  externalApiFailure,
  externalApiSuccess,
  type ExternalApiCode,
  type ExternalApiResponse,
} from '../external-api-response.js';

const log = logger.child({ module: 'api-routes/external-my-daily' });

const router = express.Router();

const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

/** 默认返回条数与上限 */
const DEFAULT_LIMIT = 5;
const MAX_LIMIT = 100;

/** 相关度分档阈值 */
const HIGH_SCORE_THRESHOLD = 0.7;
const MEDIUM_SCORE_THRESHOLD = 0.3;

const TOPIC_REQUIRED_ACTION = 'configure_topic_domain';
const JEV_REQUIRED_ACTION = 'configure_jev_api_key';

/** 评分执行情况，供 agent 判断是读缓存还是本次触发了评分 */
interface ExecutionInfo {
  triggered: boolean;
  reason: 'already_scored' | 'executed' | 'no_articles' | 'in_progress';
  scored: number | null;
  failed: number | null;
}

/** 核心轻量文章结构（字段稠密度治理：排除长摘要） */
export interface MyDailyArticleCore {
  id: number;
  title: string;
  title_zh: string | null;
  relevance_score: number;
  relevance_level: 'high' | 'medium' | 'low';
  matched_domain: string | null;
  source_origin: string | null;
  published_at: string | Date | null;
  url: string | null;
}

/** 完整文章结构（用于 fields=full 或全量文件导出） */
export interface MyDailyArticleFull extends MyDailyArticleCore {
  summary: string | null;
  summary_zh: string | null;
  filter_status: string | null;
  created_at: string | Date | null;
}

interface MyDailyData {
  userId: number;
  username: string;
  date: string;
  minScore: number | null;
  total: number;
  limit: number;
  offset: number;
  returned: number;
  exportUrl: string;
  articles: (MyDailyArticleCore | MyDailyArticleFull)[];
}

function sendJson(res: Response, status: number, body: ExternalApiResponse<unknown>): void {
  res.status(status).json(body);
}

function parseOptionalInteger(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return Math.trunc(value);
  }
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = parseInt(value, 10);
    return Number.isNaN(parsed) ? undefined : parsed;
  }
  return undefined;
}

function parseMinScore(value: unknown): number | undefined | null {
  if (value === undefined || value === null || value === '') return undefined;

  const parsed = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(parsed) || parsed < 0 || parsed > 1) return null;

  return parsed;
}

function isValidCalendarDate(value: string): boolean {
  const [year, month, day] = value.split('-').map(Number);
  if (month < 1 || month > 12 || day < 1 || day > 31) return false;

  const date = new Date(Date.UTC(year, month - 1, day));
  return (
    date.getUTCFullYear() === year &&
    date.getUTCMonth() === month - 1 &&
    date.getUTCDate() === day
  );
}

function parseDate(value: unknown): string | undefined | null {
  if (value === undefined || value === null) return undefined;
  if (typeof value !== 'string') return null;

  const trimmed = value.trim();
  if (trimmed === '') return undefined;

  return DATE_PATTERN.test(trimmed) && isValidCalendarDate(trimmed) ? trimmed : null;
}

function toCoreArticle(article: {
  id: number;
  title: string;
  title_zh: string | null;
  relevance_score: number | null;
  matched_domain: string | null;
  source_origin: string | null;
  published_at: string | Date | null;
  url: string | null;
}): MyDailyArticleCore {
  const score = article.relevance_score ?? 0;
  return {
    id: article.id,
    title: article.title,
    title_zh: article.title_zh ?? null,
    relevance_score: score,
    relevance_level:
      score >= HIGH_SCORE_THRESHOLD
        ? 'high'
        : score >= MEDIUM_SCORE_THRESHOLD
          ? 'medium'
          : 'low',
    matched_domain: article.matched_domain ?? null,
    source_origin: article.source_origin ?? null,
    published_at: article.published_at ?? null,
    url: article.url ?? null,
  };
}

function toFullArticle(article: {
  id: number;
  title: string;
  title_zh: string | null;
  summary: string | null;
  summary_zh: string | null;
  url: string | null;
  source_origin: string | null;
  filter_status: string | null;
  published_at: string | Date | null;
  created_at: string | Date | null;
  relevance_score: number | null;
  matched_domain: string | null;
}): MyDailyArticleFull {
  return {
    ...toCoreArticle(article),
    summary: article.summary ?? null,
    summary_zh: article.summary_zh ?? null,
    filter_status: article.filter_status ?? null,
    created_at: article.created_at ?? null,
  };
}

/**
 * 确保目标日期的评分已完成（如果未评分且有文章则触发排队）
 */
async function ensureScored(
  user: ExternalAuthUser,
  targetDate: string
): Promise<
  | { ok: true; code: ExternalApiCode; message: string; execution: ExecutionInfo }
  | { ok: false; status: number; response: ExternalApiResponse<never> }
> {
  const db = getDb();
  const existing = await db
    .selectFrom('user_daily_scores')
    .where('user_id', '=', user.id)
    .where('score_date', '=', targetDate)
    .select('id')
    .limit(1)
    .executeTakeFirst();

  if (existing) {
    return {
      ok: true,
      code: EXTERNAL_API_CODES.RESULT_CACHED,
      message: `该日期（${targetDate}）已有评分结果，直接返回缓存`,
      execution: { triggered: false, reason: 'already_scored', scored: null, failed: null },
    };
  }

  if (!(await hasActiveTopics(user.id))) {
    return {
      ok: false,
      status: 400,
      response: externalApiFailure(
        EXTERNAL_API_CODES.NO_TOPIC_CONFIGURED,
        '该账号尚未配置主题领域，无法执行评分。请先在「主题」页面配置主题领域与关键词',
        {
          details: {
            userId: user.id,
            username: user.username,
            date: targetDate,
            requiredAction: TOPIC_REQUIRED_ACTION,
          },
        }
      ),
    };
  }

  try {
    await resolveJevConfig();
  } catch {
    return {
      ok: false,
      status: 503,
      response: externalApiFailure(
        EXTERNAL_API_CODES.JEV_NOT_CONFIGURED,
        '服务端未配置 JEV API 密钥，无法执行评分。请在「设置 -> LLM 配置」中添加 JEV 配置',
        {
          details: {
            userId: user.id,
            username: user.username,
            date: targetDate,
            requiredAction: JEV_REQUIRED_ACTION,
          },
        }
      ),
    };
  }

  try {
    const result = await scoreForUser(user.id, user.username, targetDate);
    const reason = (result as any).reason as string | undefined;

    if (result.skipped && reason === 'no_topics') {
      return {
        ok: false,
        status: 400,
        response: externalApiFailure(
          EXTERNAL_API_CODES.NO_TOPIC_CONFIGURED,
          '该账号尚未配置主题领域，无法执行评分。请先在「主题」页面配置主题领域与关键词',
          {
            details: {
              userId: user.id,
              username: user.username,
              date: targetDate,
              requiredAction: TOPIC_REQUIRED_ACTION,
            },
          }
        ),
      };
    }

    if (reason === 'no_articles') {
      return {
        ok: true,
        code: EXTERNAL_API_CODES.NO_ARTICLES_FOR_DATE,
        message: `该日期（${targetDate}）没有新增文章，无需评分`,
        execution: { triggered: true, reason: 'no_articles', scored: 0, failed: 0 },
      };
    }

    if (reason === 'duplicate') {
      return {
        ok: false,
        status: 409,
        response: externalApiFailure(
          EXTERNAL_API_CODES.SCORING_IN_PROGRESS,
          '该日期的评分正在进行中，请稍后重试',
          { retryable: true, details: { userId: user.id, username: user.username, date: targetDate } }
        ),
      };
    }

    return {
      ok: true,
      code: EXTERNAL_API_CODES.RESULT_SCORED,
      message: `已完成该日期（${targetDate}）的评分`,
      execution: {
        triggered: true,
        reason: 'executed',
        scored: (result as any).scored ?? 0,
        failed: (result as any).failed ?? 0,
      },
    };
  } catch (error) {
    if (error instanceof ScoringQueueError) {
      const queueCode =
        error.reason === 'queue_full'
          ? EXTERNAL_API_CODES.SCORING_QUEUE_FULL
          : EXTERNAL_API_CODES.SCORING_QUEUE_TIMEOUT;
      return {
        ok: false,
        status: 429,
        response: externalApiFailure(queueCode, error.message, {
          retryable: true,
          details: { userId: user.id, username: user.username, date: targetDate, reason: error.reason },
        }),
      };
    }
    throw error;
  }
}

/**
 * 组装全量有效评分文献（过滤 failed: true 及 minScore）
 */
async function loadScoredArticles(
  userId: number,
  date: string,
  minScore: number | undefined
) {
  const daily = await getDailyArticles(userId, date);

  // 严格剔除 failed: true 的占位垃圾条目
  const validArticles = daily.articles.filter((article) => !article.failed);

  const matchedArticles =
    minScore === undefined
      ? validArticles
      : validArticles.filter((article) => (article.relevance_score ?? 0) >= minScore);

  return matchedArticles;
}

/**
 * 生成全量导出直链
 */
function buildExportUrl(username: string, date: string, minScore?: number): string {
  const params = new URLSearchParams();
  params.set('username', username);
  params.set('date', date);
  if (minScore !== undefined) {
    params.set('minScore', String(minScore));
  }
  return `/api/external/my-daily/export?${params.toString()}`;
}

/**
 * POST /api/external/my-daily
 *
 * 鉴权：
 * - Header: x-api-key: <CLI_API_KEY>（或 query.api_key）
 *
 * Body 参数：
 * - username: string   可选，用户名（与 userId 二选一）
 * - userId: number     可选，用户 ID（与 username 二选一）
 * - date: string       可选，YYYY-MM-DD，默认用户时区下的当天
 * - minScore: number   可选，0~1，过滤最低综合相关度
 * - limit: number      可选，返回条数，默认 5，最大 100
 * - offset: number     可选，偏移量，默认 0
 * - fields: string     可选，"core" | "full"，默认 "core"
 * - format: string     可选，"json" | "json_file"，默认 "json"
 */
router.post('/external/my-daily', async (req: AuthRequest, res) => {
  try {
    const auth = await verifyExternalApiAuth(req, { allowedRoles: ['admin', 'user'] });
    if (!auth.ok) {
      return sendJson(res, auth.status, auth.response);
    }
    const user = auth.user;

    const body = (req.body ?? {}) as Record<string, unknown>;
    const query = (req.query ?? {}) as Record<string, unknown>;

    const dateVal = body.date ?? query.date;
    const date = parseDate(dateVal);
    if (date === null) {
      return sendJson(
        res,
        400,
        externalApiFailure(EXTERNAL_API_CODES.INVALID_DATE_FORMAT, 'date 格式应为 YYYY-MM-DD', {
          details: { userId: user.id, username: user.username },
        })
      );
    }

    const minScoreVal = body.minScore ?? query.minScore;
    const minScore = parseMinScore(minScoreVal);
    if (minScore === null) {
      return sendJson(
        res,
        400,
        externalApiFailure(EXTERNAL_API_CODES.INVALID_MIN_SCORE, 'minScore 应为 0~1 之间的数值', {
          details: { userId: user.id, username: user.username },
        })
      );
    }

    const parsedLimit = parseOptionalInteger(body.limit ?? query.limit);
    if (parsedLimit !== undefined && parsedLimit <= 0) {
      return sendJson(
        res,
        400,
        externalApiFailure(EXTERNAL_API_CODES.INVALID_LIMIT, 'limit 必须为正整数', {
          details: { userId: user.id, username: user.username },
        })
      );
    }
    const limit = Math.min(parsedLimit ?? DEFAULT_LIMIT, MAX_LIMIT);

    const parsedOffset = parseOptionalInteger(body.offset ?? query.offset);
    if (parsedOffset !== undefined && parsedOffset < 0) {
      return sendJson(
        res,
        400,
        externalApiFailure(EXTERNAL_API_CODES.INVALID_OFFSET, 'offset 必须大于等于 0', {
          details: { userId: user.id, username: user.username },
        })
      );
    }
    const offset = parsedOffset ?? 0;

    const fields = String(body.fields ?? query.fields ?? 'core').toLowerCase() === 'full' ? 'full' : 'core';
    const format = String(body.format ?? query.format ?? 'json').toLowerCase() === 'json_file' ? 'json_file' : 'json';

    const targetDate = date ?? (await getUserLocalDate(user.id));

    // 确保打分完毕
    const scoreState = await ensureScored(user, targetDate);
    if (!scoreState.ok) {
      return sendJson(res, scoreState.status, scoreState.response);
    }

    const matchedArticles = await loadScoredArticles(user.id, targetDate, minScore);
    const total = matchedArticles.length;

    // 若请求 format=json_file，直接以附件形式输出全量 JSON（留存轨）
    if (format === 'json_file') {
      const fullArticles = matchedArticles.map(toFullArticle);
      const fileData = {
        userId: user.id,
        username: user.username,
        date: targetDate,
        minScore: minScore ?? null,
        total,
        returned: fullArticles.length,
        articles: fullArticles,
      };

      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.setHeader(
        'Content-Disposition',
        `attachment; filename="my-daily-${user.username}-${targetDate}.json"`
      );
      return res.status(200).send(JSON.stringify(fileData, null, 2));
    }

    // 默认感知轨切片
    const paged = matchedArticles.slice(offset, offset + limit);
    const articles = fields === 'full' ? paged.map(toFullArticle) : paged.map(toCoreArticle);
    const exportUrl = buildExportUrl(user.username, targetDate, minScore);

    const data: MyDailyData = {
      userId: user.id,
      username: user.username,
      date: targetDate,
      minScore: minScore ?? null,
      total,
      limit,
      offset,
      returned: articles.length,
      exportUrl,
      articles,
    };

    sendJson(
      res,
      200,
      externalApiSuccess(scoreState.code, scoreState.message, data, {
        userId: user.id,
        username: user.username,
        date: targetDate,
        execution: scoreState.execution,
      })
    );
  } catch (error) {
    const reason = error instanceof Error ? error.message : '未知错误';
    log.error({ error }, 'External my-daily request failed');
    sendJson(
      res,
      500,
      externalApiFailure(EXTERNAL_API_CODES.INTERNAL_ERROR, '服务端处理请求时发生异常', {
        retryable: true,
        details: { reason },
      })
    );
  }
});

/**
 * GET /api/external/my-daily/export
 *
 * 全量 JSON 导出直链端点（留存轨）：
 * 直接将目标日期的全量文献（含长摘要）以静态附件文件流格式返回。
 */
router.get('/external/my-daily/export', async (req: AuthRequest, res) => {
  try {
    const auth = await verifyExternalApiAuth(req, { allowedRoles: ['admin', 'user'] });
    if (!auth.ok) {
      return sendJson(res, auth.status, auth.response);
    }
    const user = auth.user;

    const query = req.query as Record<string, unknown>;
    const date = parseDate(query.date);
    if (date === null) {
      return sendJson(
        res,
        400,
        externalApiFailure(EXTERNAL_API_CODES.INVALID_DATE_FORMAT, 'date 格式应为 YYYY-MM-DD')
      );
    }

    const minScore = parseMinScore(query.minScore);
    if (minScore === null) {
      return sendJson(
        res,
        400,
        externalApiFailure(EXTERNAL_API_CODES.INVALID_MIN_SCORE, 'minScore 应为 0~1 之间的数值')
      );
    }

    const targetDate = date ?? (await getUserLocalDate(user.id));
    const scoreState = await ensureScored(user, targetDate);
    if (!scoreState.ok) {
      return sendJson(res, scoreState.status, scoreState.response);
    }

    const matchedArticles = await loadScoredArticles(user.id, targetDate, minScore);
    const fullArticles = matchedArticles.map(toFullArticle);

    const fileData = {
      userId: user.id,
      username: user.username,
      date: targetDate,
      minScore: minScore ?? null,
      total: fullArticles.length,
      returned: fullArticles.length,
      articles: fullArticles,
    };

    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.setHeader(
      'Content-Disposition',
      `attachment; filename="my-daily-${user.username}-${targetDate}.json"`
    );
    res.status(200).send(JSON.stringify(fileData, null, 2));
  } catch (error) {
    const reason = error instanceof Error ? error.message : '未知错误';
    log.error({ error }, 'External my-daily export failed');
    sendJson(
      res,
      500,
      externalApiFailure(EXTERNAL_API_CODES.INTERNAL_ERROR, '导出全量数据时发生异常', {
        retryable: true,
        details: { reason },
      })
    );
  }
});

export default router;
