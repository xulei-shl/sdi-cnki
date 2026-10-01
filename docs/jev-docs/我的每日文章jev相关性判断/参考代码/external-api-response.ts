/**
 * 外部 API（供 agent / 外部项目调用）统一响应信封
 *
 * 所有响应（成功与失败）都使用同一层结构，便于 agent 稳定解析：
 * - ok：先据此区分成功 / 失败；
 * - code：机器可读的稳定状态码，可枚举、不随文案变化；
 * - message：人类可读说明，失败时尽量给出下一步动作；
 * - retryable：失败是否可能通过重试恢复；
 * - data：成功时的结构化结果，失败时为 null；
 * - details：诊断上下文（用户 / 日期 / 执行结果 / 需执行的动作），无则为 null。
 */

export const EXTERNAL_API_CODES = {
  // ── 「我的每日」成功 ──────────────────────────────────────────────
  RESULT_CACHED: 'RESULT_CACHED',
  RESULT_SCORED: 'RESULT_SCORED',
  NO_ARTICLES_FOR_DATE: 'NO_ARTICLES_FOR_DATE',

  // ── 「我的每日」当前状态无法完成（非输入错误）─────────────────────
  SCORING_IN_PROGRESS: 'SCORING_IN_PROGRESS',
  NO_TOPIC_CONFIGURED: 'NO_TOPIC_CONFIGURED',
  JEV_NOT_CONFIGURED: 'JEV_NOT_CONFIGURED',

  // ── 「我的每日」输入与状态错误 ──────────────────────────────────────
  FORBIDDEN_ROLE: 'FORBIDDEN_ROLE',
  INVALID_DATE_FORMAT: 'INVALID_DATE_FORMAT',
  INVALID_MIN_SCORE: 'INVALID_MIN_SCORE',
  SCORING_QUEUE_FULL: 'SCORING_QUEUE_FULL',
  SCORING_QUEUE_TIMEOUT: 'SCORING_QUEUE_TIMEOUT',

  // ── 统一检索成功 ──────────────────────────────────────────────────
  SEARCH_COMPLETED: 'SEARCH_COMPLETED',
  SEARCH_NO_RESULTS: 'SEARCH_NO_RESULTS',

  // ── 统一检索输入错误 ──────────────────────────────────────────────
  INVALID_MODE: 'INVALID_MODE',
  MISSING_QUERY: 'MISSING_QUERY',
  MISSING_ARTICLE_ID: 'MISSING_ARTICLE_ID',
  INVALID_LIMIT: 'INVALID_LIMIT',
  INVALID_OFFSET: 'INVALID_OFFSET',

  // ── CLI / 外部 API 鉴权（username / user_id + api_key / x-api-key）──
  CLI_API_KEY_NOT_CONFIGURED: 'CLI_API_KEY_NOT_CONFIGURED',
  MISSING_USER_IDENTIFIER: 'MISSING_USER_IDENTIFIER',
  MISSING_USER_ID: 'MISSING_USER_ID',
  INVALID_USER_ID: 'INVALID_USER_ID',
  MISSING_API_KEY: 'MISSING_API_KEY',
  INVALID_API_KEY: 'INVALID_API_KEY',
  USER_NOT_FOUND: 'USER_NOT_FOUND',

  // ── 通用 ──────────────────────────────────────────────────────────
  INVALID_JSON_BODY: 'INVALID_JSON_BODY',
  INTERNAL_ERROR: 'INTERNAL_ERROR',
} as const;

export type ExternalApiCode = (typeof EXTERNAL_API_CODES)[keyof typeof EXTERNAL_API_CODES];

export interface ExternalApiResponse<T = unknown> {
  ok: boolean;
  code: ExternalApiCode;
  message: string;
  retryable: boolean;
  data: T | null;
  details: Record<string, unknown> | null;
}

/** 构造成功响应信封 */
export function externalApiSuccess<T>(
  code: ExternalApiCode,
  message: string,
  data: T,
  details: Record<string, unknown> | null = null
): ExternalApiResponse<T> {
  return { ok: true, code, message, retryable: false, data, details };
}

/** 构造失败响应信封 */
export function externalApiFailure(
  code: ExternalApiCode,
  message: string,
  options: { retryable?: boolean; details?: Record<string, unknown> | null } = {}
): ExternalApiResponse<never> {
  return {
    ok: false,
    code,
    message,
    retryable: options.retryable ?? false,
    data: null,
    details: options.details ?? null,
  };
}
