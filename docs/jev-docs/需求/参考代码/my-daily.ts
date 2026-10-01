/**
 * 我的每日 API
 *
 * 获取当日 JEV 评分结果，按评分排序返回。
 *
 * 日期语义与「每日期刊 / 每日资讯」总结保持一致：
 * score_date 是用户时区下的本地自然日（YYYY-MM-DD），
 * 文章通常在凌晨抓取，因此查询时必须换算成对应的 UTC 区间。
 */

import { getDb } from '../db.js';
import { logger } from '../logger.js';
import { isJevResponseFailed } from '../jev.js';
import { getUserLocalDate, getUserTimezone, buildUtcRangeFromLocalDate } from './timezone.js';

const log = logger.child({ module: 'my-daily-api' });

/** 可评分日期回溯窗口（自然日） */
const SCORABLE_DAYS_WINDOW = 30;

/**
 * 获取用户当日的评分文章列表
 */
export async function getDailyArticles(userId: number, date?: string) {
  const db = getDb();

  // 默认用户时区下的当天
  const scoreDate = date || (await getUserLocalDate(userId));

  // 联表查询：评分 + 文章 + 翻译
  const rows = await db
    .selectFrom('user_daily_scores as s')
    .innerJoin('articles as a', 'a.id', 's.article_id')
    .leftJoin('article_translations as t', 't.article_id', 'a.id')
    .where('s.user_id', '=', userId)
    .where('s.score_date', '=', scoreDate)
    .select([
      'a.id',
      'a.title',
      'a.url',
      'a.summary',
      'a.source_origin',
      'a.filter_status',
      'a.published_at',
      'a.created_at',
      's.relevance_score',
      's.matched_domain',
      's.jev_response',
      't.title_zh',
      't.summary_zh',
    ])
    .orderBy('s.relevance_score', 'desc')
    .execute();

  // 标记 JEV 调用失败的条目：其 relevance_score 是占位 0 分，不代表真实相关性，
  // 因此统一沉底，交给前端单独标识而不是混进相关性排序。
  const articles = rows.map((row) => ({
    ...row,
    failed: isJevResponseFailed(row.jev_response),
  }));
  articles.sort((a, b) => {
    if (a.failed !== b.failed) return a.failed ? 1 : -1;
    return (b.relevance_score ?? 0) - (a.relevance_score ?? 0);
  });

  return {
    date: scoreDate,
    total: articles.length,
    articles,
  };
}

/**
 * 按自然日平移日期字符串（YYYY-MM-DD）
 */
function shiftLocalDate(dateStr: string, deltaDays: number): string {
  const [year, month, day] = dateStr.split('-').map(Number);
  return new Date(Date.UTC(year, month - 1, day + deltaDays)).toISOString().split('T')[0];
}

/**
 * 获取最近若干自然日中「有可评分文章」的日期
 *
 * 与计分口径保持一致：每个自然日都按用户时区换算成 UTC 区间，
 * 只要该自然日存在任何新增文章（不限于已通过预过滤的），就认为可评分。
 */
async function getScorableDates(timezone: string, todayLocal: string): Promise<string[]> {
  const db = getDb();
  const dates: string[] = [];

  for (let offset = 0; offset < SCORABLE_DAYS_WINDOW; offset++) {
    const date = shiftLocalDate(todayLocal, -offset);
    const [startUtc, endUtc] = buildUtcRangeFromLocalDate(date, timezone);

    const hit = await db
      .selectFrom('articles')
      .where('created_at', '>=', startUtc)
      .where('created_at', '<=', endUtc)
      .select('id')
      .limit(1)
      .executeTakeFirst();

    if (hit) dates.push(date);
  }

  return dates;
}

/**
 * 获取可用的评分日期列表
 *
 * 合并两类日期（去重后按时间倒序，最多 30 个）：
 * 1. 已经产生评分结果的日期
 * 2. 有可评分文章的日期（最近 30 个自然日内，当日有新增文章）
 *
 * 第 2 类保证用户在尚未评分时，仍然能选择该日期进行评分。
 */
export async function getAvailableDates(userId: number) {
  const db = getDb();
  const limit = 30;

  const [timezone, todayLocal] = await Promise.all([
    getUserTimezone(userId),
    getUserLocalDate(userId),
  ]);

  const scoredDates = await db
    .selectFrom('user_daily_scores')
    .where('user_id', '=', userId)
    .select('score_date')
    .distinct()
    .orderBy('score_date', 'desc')
    .limit(limit)
    .execute();

  const scorableDates = await getScorableDates(timezone, todayLocal);

  const dates = new Set<string>();
  for (const d of scoredDates) dates.add(d.score_date);
  for (const d of scorableDates) dates.add(d);

  log.info({ userId, timezone, today: todayLocal, count: dates.size }, '获取可评分日期列表');

  return {
    dates: Array.from(dates).sort().reverse().slice(0, limit),
    scoredDates: scoredDates.map((d) => d.score_date),
    today: todayLocal,
  };
}

/**
 * 每日状态项
 */
export interface DailyStatusItem {
  status: 'green' | 'yellow' | 'orange' | 'red' | 'future';
  hasArticles: boolean;
  isScored: boolean;
  /** JEV 调用失败的条目数（占位 0 分，不代表真实相关性） */
  failedCount: number;
  articleCount: number;
}

/**
 * 获取指定月份每一天的文章与 JEV 排序状态
 *
 * 状态判定规则：
 * - future: 未来日期（不可选，不渲染状态圆点）
 * - green:  已执行 JEV 排序且至少一篇拿到真实分数
 * - orange: 已调用 JEV 但全部失败，分数不可用（待重试）
 * - yellow: 当天有文章，但尚未执行 JEV 排序
 * - red:    当天没有文章
 */
export async function getMonthDailyStatus(userId: number, yearMonth?: string) {
  const db = getDb();
  const [timezone, todayLocal] = await Promise.all([
    getUserTimezone(userId),
    getUserLocalDate(userId),
  ]);

  // 若未提供合法的 YYYY-MM，默认使用用户时区下的当月
  let targetMonth = yearMonth;
  if (!targetMonth || !/^\d{4}-\d{2}$/.test(targetMonth)) {
    targetMonth = todayLocal.slice(0, 7);
  }

  const [yearStr, monthStr] = targetMonth.split('-');
  const year = parseInt(yearStr, 10);
  const month = parseInt(monthStr, 10);

  // 计算当月总天数
  const daysInMonth = new Date(year, month, 0).getDate();
  const lastDayStr = String(daysInMonth).padStart(2, '0');

  // 构建当月的起始与结束 UTC 范围
  const [startUtc] = buildUtcRangeFromLocalDate(`${targetMonth}-01`, timezone);
  const [, endUtc] = buildUtcRangeFromLocalDate(`${targetMonth}-${lastDayStr}`, timezone);

  // 1. 查询当月已评分记录，并按日期聚合成功 / 失败篇数；
  //    失败判定依据 jev_response 中是否记录了调用错误（见 isJevResponseFailed）
  const scoredRows = await db
    .selectFrom('user_daily_scores')
    .where('user_id', '=', userId)
    .where('score_date', '>=', `${targetMonth}-01`)
    .where('score_date', '<=', `${targetMonth}-${lastDayStr}`)
    .select(['score_date', 'jev_response'])
    .execute();

  const scoredStats = new Map<string, { total: number; failed: number }>();
  for (const row of scoredRows) {
    const stat = scoredStats.get(row.score_date) || { total: 0, failed: 0 };
    stat.total++;
    if (isJevResponseFailed(row.jev_response)) stat.failed++;
    scoredStats.set(row.score_date, stat);
  }

  // 2. 查询当月范围内的文章创建时间
  const articleRows = await db
    .selectFrom('articles')
    .where('created_at', '>=', startUtc)
    .where('created_at', '<=', endUtc)
    .select('created_at')
    .execute();

  // 按用户时区格式化日期 (YYYY-MM-DD)
  const formatter = new Intl.DateTimeFormat('en-CA', {
    timeZone: timezone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  });

  const articleDatesCount = new Map<string, number>();
  for (const row of articleRows) {
    if (!row.created_at) continue;
    const localDate = formatter.format(new Date(row.created_at));
    // 仅统计属于当前月份内的文章
    if (localDate.startsWith(targetMonth)) {
      articleDatesCount.set(localDate, (articleDatesCount.get(localDate) || 0) + 1);
    }
  }

  // 3. 构建整月每日状态字典
  const days: Record<string, DailyStatusItem> = {};
  for (let d = 1; d <= daysInMonth; d++) {
    const dayStr = String(d).padStart(2, '0');
    const dateKey = `${targetMonth}-${dayStr}`;

    if (dateKey > todayLocal) {
      days[dateKey] = {
        status: 'future',
        hasArticles: false,
        isScored: false,
        failedCount: 0,
        articleCount: 0,
      };
      continue;
    }

    const stat = scoredStats.get(dateKey);
    const isScored = !!stat;
    const failedCount = stat?.failed ?? 0;
    const successCount = stat ? stat.total - stat.failed : 0;
    const articleCount = articleDatesCount.get(dateKey) || 0;
    const hasArticles = articleCount > 0;

    // 有评分记录但一篇都没拿到真实分数：当天 JEV 调用全部失败，标成待重试
    let status: 'green' | 'yellow' | 'orange' | 'red';
    if (!isScored) {
      status = hasArticles ? 'yellow' : 'red';
    } else if (successCount === 0) {
      status = 'orange';
    } else {
      status = 'green';
    }

    days[dateKey] = {
      status,
      hasArticles,
      isScored,
      failedCount,
      articleCount,
    };
  }

  return {
    month: targetMonth,
    today: todayLocal,
    days,
  };
}

