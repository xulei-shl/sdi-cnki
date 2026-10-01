/**
 * 我的每日评分调度器
 *
 * 定时为每个 user 角色的用户执行 JEV 评分：
 * 1. 获取所有 role='user' 的用户
 * 2. 获取每个用户的主题领域和关键词
 * 3. 获取当日新增的文章（不过滤 filter_status）
 * 4. 并行调用 JEV 评分（并发数为 config.myDailyConcurrency）
 * 5. 结果写入 user_daily_scores 表
 *
 * 并发控制：用户之间串行（见 runDailyScoring），且全局同一时刻只允许一个评分
 * 任务在跑。重叠触发时按 FIFO 排队等待，前一个任务结束后名额自动转交给队首，
 * 因此定时任务与「重新评分」、以及多人同时点击都不会让 JEV 并发翻倍或重复计算
 * 同一批文章（见 acquireScoringSlot / releaseScoringSlot）。
 */

import cron from 'node-cron';
import { getDb } from './db.js';
import { config } from './config.js';
import { logger } from './logger.js';
import { scoreArticlesBatch, resolveJevConfig, type TopicInfo } from './jev.js';
import { getUserLocalDate, getUserTimezone, buildUtcRangeFromLocalDate } from './api/timezone.js';
import { getTopicDomainById } from './api/topic-domains.js';
import { getActiveKeywordsForDomain } from './api/topic-keywords.js';

const log = logger.child({ module: 'my-daily-scorer' });

/** 持有执行名额的任务 */
interface ActiveScoringJob {
  userId: number;
  date: string;
  startedAt: number;
}

/** 排队等待执行名额的任务 */
interface QueuedScoringJob {
  userId: number;
  date: string;
  enqueuedAt: number;
  resolve: () => void;
  reject: (error: Error) => void;
  timer: ReturnType<typeof setTimeout>;
}

/** 排队最长等待时间，超过就放弃（避免请求无限期挂着） */
const MAX_SCORING_WAIT_MS = 10 * 60 * 1000;

/** 队列长度上限，防止请求堆积 */
const MAX_SCORING_QUEUE_LENGTH = 10;

/** 当前持有执行名额的任务 */
let activeScoringJob: ActiveScoringJob | null = null;

/** 等待执行名额的任务（FIFO） */
const queuedScoringJobs: QueuedScoringJob[] = [];

/**
 * 排队失败时抛出：
 * - queue_full：队列已满
 * - wait_timeout：等待超过 MAX_SCORING_WAIT_MS
 */
export class ScoringQueueError extends Error {
  constructor(message: string, public readonly reason: 'queue_full' | 'wait_timeout') {
    super(message);
    this.name = 'ScoringQueueError';
  }
}

/** 同一 (userId, date) 是否已在执行或排队中 */
function isJobActiveOrQueued(userId: number, date: string): boolean {
  if (activeScoringJob?.userId === userId && activeScoringJob.date === date) return true;
  return queuedScoringJobs.some(job => job.userId === userId && job.date === date);
}

/**
 * 获取执行名额：空闲则立即获得；否则按 FIFO 排队，轮到时 resolve。
 * 名额在获得时（包括转交时）就已记入 activeScoringJob，因此不存在插队窗口。
 */
function acquireScoringSlot(userId: number, date: string): Promise<void> {
  if (!activeScoringJob) {
    activeScoringJob = { userId, date, startedAt: Date.now() };
    return Promise.resolve();
  }

  if (queuedScoringJobs.length >= MAX_SCORING_QUEUE_LENGTH) {
    return Promise.reject(
      new ScoringQueueError('当前排队的评分任务过多，请稍后再试', 'queue_full')
    );
  }

  return new Promise<void>((resolve, reject) => {
    const job: QueuedScoringJob = {
      userId,
      date,
      enqueuedAt: Date.now(),
      resolve,
      reject,
      timer: setTimeout(() => {
        const index = queuedScoringJobs.indexOf(job);
        if (index >= 0) queuedScoringJobs.splice(index, 1);
        reject(
          new ScoringQueueError(
            `等待时间超过 ${Math.round(MAX_SCORING_WAIT_MS / 60000)} 分钟，已取消排队，请稍后再试`,
            'wait_timeout'
          )
        );
      }, MAX_SCORING_WAIT_MS),
    };

    queuedScoringJobs.push(job);
    log.info(
      {
        userId,
        date,
        position: queuedScoringJobs.length,
        activeUserId: activeScoringJob?.userId,
      },
      '评分任务已排队，等待执行'
    );
  });
}

/**
 * 释放执行名额，并把名额直接转交给队首任务。
 * 名额在转交时立即写入 activeScoringJob，新请求无法插队，保证 FIFO 顺序。
 */
function releaseScoringSlot() {
  const next = queuedScoringJobs.shift();

  if (!next) {
    activeScoringJob = null;
    return;
  }

  clearTimeout(next.timer);
  activeScoringJob = { userId: next.userId, date: next.date, startedAt: Date.now() };
  log.info(
    {
      userId: next.userId,
      date: next.date,
      waitedMs: Date.now() - next.enqueuedAt,
      remaining: queuedScoringJobs.length,
    },
    '轮到此任务执行'
  );
  next.resolve();
}

/**
 * 获取用户的主题领域和关键词
 */
async function getUserTopics(userId: number): Promise<TopicInfo[]> {
  const db = getDb();

  // 获取用户激活的主题领域
  const domains = await db
    .selectFrom('topic_domains')
    .where('user_id', '=', userId)
    .where('is_active', '=', 1)
    .select(['id', 'name', 'description'])
    .execute();

  if (domains.length === 0) return [];

  // 获取每个领域的关键词
  const topics: TopicInfo[] = [];
  for (const domain of domains) {
    const keywords = await db
      .selectFrom('topic_keywords')
      .where('domain_id', '=', domain.id)
      .where('is_active', '=', 1)
      .select(['keyword'])
      .execute();

    topics.push({
      name: domain.name,
      description: domain.description,
      keywords: keywords.map(k => k.keyword),
    });
  }

  return topics;
}

/**
 * 判断用户是否配置了可用的主题领域（至少一个激活领域）
 *
 * 与 getUserTopics 的过滤口径一致（topic_domains 中 is_active = 1）。
 * 供外部 API 在执行评分前提前校验，避免没有主题时白白占用全局评分名额。
 */
export async function hasActiveTopics(userId: number): Promise<boolean> {
  const db = getDb();
  const hit = await db
    .selectFrom('topic_domains')
    .where('user_id', '=', userId)
    .where('is_active', '=', 1)
    .select('id')
    .limit(1)
    .executeTakeFirst();
  return !!hit;
}

/**
 * 获取指定自然日新增的文章
 *
 * 日期口径与「每日期刊 / 每日资讯」总结一致：
 * date 是用户时区下的本地日期，先换算成对应的 UTC 区间再查询。
 * 文章通常在凌晨抓取，若直接按 UTC 日期查询会把同一个自然日的文章拆到两天。
 *
 * 注意：这里不按 filter_status 过滤——需求要求 JEV 对当日所有新增文章
 * 评分打标过滤（低分条目灰显），因此已经过关键词预过滤的文章也要参与评分。
 */
export interface ScoringProgressStartEvent {
  type: 'start';
  total: number;
}

export interface ScoringProgressItemEvent {
  type: 'item';
  current: number;
  total: number;
  latencyMs?: number;
  breakdown?: {
    noulProb: number;
    scoreLevel: number;
    scoreNormalized: number;
    levelLabel: string;
    candidates?: Array<{ name: string; score: number }>;
  };
  article: {
    id: number;
    title: string;
    url: string | null;
    summary: string | null;
    source_origin: string | null;
    filter_status: string | null;
    published_at: Date | string | null;
    created_at: Date | string | null;
    title_zh: string | null;
    summary_zh: string | null;
    relevance_score: number;
    matched_domain: string | null;
    /** JEV 调用失败：relevance_score 为占位 0 分，不代表真实相关性 */
    failed: boolean;
  };
}

export interface ScoringProgressDoneEvent {
  type: 'done';
  total: number;
  scored: number;
  failed: number;
}

export type ScoringProgressEvent =
  | ScoringProgressStartEvent
  | ScoringProgressItemEvent
  | ScoringProgressDoneEvent;

export type ScoringProgressCallback = (event: ScoringProgressEvent) => Promise<void> | void;

/** 当日文章（含来源外键，用于解析来源绑定的主题领域） */
interface TodayArticle {
  id: number;
  title: string;
  url: string | null;
  summary: string | null;
  source_origin: string | null;
  filter_status: string | null;
  published_at: Date | string | null;
  created_at: Date | string | null;
  title_zh: string | null;
  summary_zh: string | null;
  rss_source_id: number | null;
  journal_id: number | null;
  keyword_id: number | null;
  email_source_id: number | null;
  web_source_id: number | null;
}

/**
 * 获取指定自然日新增的文章（包含前台渲染所需全部元数据）
 *
 * 日期口径与「每日期刊 / 每日资讯」总结一致：
 * date 是用户时区下的本地日期，先换算成对应的 UTC 区间再查询。
 * 文章通常在凌晨抓取，若直接按 UTC 日期查询会把同一个自然日的文章拆到两天。
 *
 * 注意：这里不按 filter_status 过滤——需求要求 JEV 对当日所有新增文章
 * 评分打标过滤（低分条目灰显），因此已经过关键词预过滤的文章也要参与评分。
 */
async function getTodayArticles(date: string, userId: number): Promise<TodayArticle[]> {
  const db = getDb();

  const timezone = await getUserTimezone(userId);
  const [startUtc, endUtc] = buildUtcRangeFromLocalDate(date, timezone);

  const articles = await db
    .selectFrom('articles as a')
    .leftJoin('article_translations as t', 't.article_id', 'a.id')
    .where('a.created_at', '>=', startUtc)
    .where('a.created_at', '<=', endUtc)
    .select([
      'a.id',
      'a.title',
      'a.url',
      'a.summary',
      'a.source_origin',
      'a.filter_status',
      'a.published_at',
      'a.created_at',
      'a.rss_source_id',
      'a.journal_id',
      'a.keyword_id',
      'a.email_source_id',
      'a.web_source_id',
      't.title_zh',
      't.summary_zh',
    ])
    .execute();

  return articles;
}

/**
 * 解析每篇文章应使用的主题（复用 LLM 过滤的「源 → 单领域」逻辑）
 *
 * 文章 source_origin 指向的源表上都绑定了 domain_id。能解析出领域时，只把该
 * 领域及其激活关键词交给 JEV：判断更聚焦、prompt 更小，领域归属也直接确定。
 * 解析不出（源未绑定领域 / 领域已删除 / 不属于该用户）时回退到用户的全部
 * 激活领域，与改造前的行为一致，避免文章拿不到分。
 *
 * 注意：绑定领域不做 is_active 过滤——它是源上显式做出的归档选择；关键词则
 * 沿用 filter 模块的口径，只取激活关键词。
 */
async function resolveArticleTopics(
  articles: TodayArticle[],
  userId: number,
  fallbackTopics: TopicInfo[]
): Promise<{ topicsByArticle: Map<number, TopicInfo[]>; boundCount: number; fallbackCount: number }> {
  const db = getDb();

  // 1. 按来源类型批量反查源表上的 domain_id
  const rssIds = new Set<number>();
  const journalIds = new Set<number>();
  const keywordIds = new Set<number>();
  const emailIds = new Set<number>();
  const webIds = new Set<number>();

  for (const a of articles) {
    if (a.source_origin === 'rss' && a.rss_source_id) rssIds.add(a.rss_source_id);
    else if (a.source_origin === 'journal' && a.journal_id) journalIds.add(a.journal_id);
    else if (a.source_origin === 'keyword' && a.keyword_id) keywordIds.add(a.keyword_id);
    else if (a.source_origin === 'email' && a.email_source_id) emailIds.add(a.email_source_id);
    else if (a.source_origin === 'web' && a.web_source_id) webIds.add(a.web_source_id);
  }

  const [rssRows, journalRows, keywordRows, emailRows, webRows] = await Promise.all([
    rssIds.size
      ? db.selectFrom('rss_sources').select(['id', 'domain_id']).where('id', 'in', [...rssIds]).execute()
      : Promise.resolve([]),
    journalIds.size
      ? db.selectFrom('journals').select(['id', 'domain_id']).where('id', 'in', [...journalIds]).execute()
      : Promise.resolve([]),
    keywordIds.size
      ? db.selectFrom('keyword_subscriptions').select(['id', 'domain_id']).where('id', 'in', [...keywordIds]).execute()
      : Promise.resolve([]),
    emailIds.size
      ? db.selectFrom('email_sources').select(['id', 'domain_id']).where('id', 'in', [...emailIds]).execute()
      : Promise.resolve([]),
    webIds.size
      ? db.selectFrom('web_sources').select(['id', 'domain_id']).where('id', 'in', [...webIds]).execute()
      : Promise.resolve([]),
  ]);

  const toMap = (rows: Array<{ id: number; domain_id: number }>) => {
    const m = new Map<number, number>();
    for (const r of rows) {
      if (r.domain_id != null) m.set(r.id, r.domain_id);
    }
    return m;
  };
  const rssDomain = toMap(rssRows);
  const journalDomain = toMap(journalRows);
  const keywordDomain = toMap(keywordRows);
  const emailDomain = toMap(emailRows);
  const webDomain = toMap(webRows);

  const domainIdByArticle = new Map<number, number>();
  for (const a of articles) {
    let domainId: number | undefined;
    if (a.source_origin === 'rss' && a.rss_source_id) domainId = rssDomain.get(a.rss_source_id);
    else if (a.source_origin === 'journal' && a.journal_id) domainId = journalDomain.get(a.journal_id);
    else if (a.source_origin === 'keyword' && a.keyword_id) domainId = keywordDomain.get(a.keyword_id);
    else if (a.source_origin === 'email' && a.email_source_id) domainId = emailDomain.get(a.email_source_id);
    else if (a.source_origin === 'web' && a.web_source_id) domainId = webDomain.get(a.web_source_id);

    if (domainId !== undefined) domainIdByArticle.set(a.id, domainId);
  }

  // 2. 加载涉及的领域（做所有权校验，不过滤 is_active）及其激活关键词
  const domainTopicCache = new Map<number, TopicInfo | null>();
  for (const domainId of new Set(domainIdByArticle.values())) {
    const domain = await getTopicDomainById(domainId, userId);
    if (!domain) {
      domainTopicCache.set(domainId, null);
      continue;
    }
    const keywords = await getActiveKeywordsForDomain(domain.id);
    domainTopicCache.set(domainId, {
      name: domain.name,
      description: domain.description,
      keywords: keywords.map(k => k.keyword),
    });
  }

  // 3. 逐篇确定主题：能解析出绑定领域就用它，否则回退全部激活领域
  const topicsByArticle = new Map<number, TopicInfo[]>();
  let boundCount = 0;
  let fallbackCount = 0;

  for (const a of articles) {
    const domainId = domainIdByArticle.get(a.id);
    const bound = domainId !== undefined ? domainTopicCache.get(domainId) : undefined;

    if (bound) {
      topicsByArticle.set(a.id, [bound]);
      boundCount++;
    } else {
      topicsByArticle.set(a.id, fallbackTopics);
      fallbackCount++;
    }
  }

  return { topicsByArticle, boundCount, fallbackCount };
}

/**
 * 为单个用户执行评分
 *
 * 同一时刻只允许一个评分任务在执行，其余按 FIFO 排队；
 * 前一个任务结束后名额自动转交给队首，因此调用方只需 await。
 * 同一 (用户, 日期) 已在执行或排队时不会重复入队。
 */
export async function scoreForUser(
  userId: number,
  username: string,
  date: string,
  onProgress?: ScoringProgressCallback
) {
  if (isJobActiveOrQueued(userId, date)) {
    log.info({ userId, date }, '该日期的评分已在执行或排队中，跳过重复触发');
    return { userId, scored: 0, skipped: true, reason: 'duplicate' as const };
  }

  await acquireScoringSlot(userId, date);

  try {
    return await runScoringForUser(userId, username, date, onProgress);
  } finally {
    releaseScoringSlot();
  }
}

/** 单个用户的评分主体（调用方须已持有评分锁） */
async function runScoringForUser(
  userId: number,
  username: string,
  date: string,
  onProgress?: ScoringProgressCallback
) {
  try {
    await resolveJevConfig();
  } catch (err) {
    throw new Error('未配置 JEV API 密钥。请在「设置 -> LLM 配置」中添加 JEV 配置，或在环境变量中配置 TYPESAFE_API_KEY。');
  }

  log.info({ userId, username, date }, '开始为用户执行评分');

  // 获取用户主题
  const topics = await getUserTopics(userId);
  if (topics.length === 0) {
    log.info({ userId, username }, '用户没有设置主题领域，跳过');
    return { userId, scored: 0, skipped: true, reason: 'no_topics' };
  }

  // 获取当日文章
  const articles = await getTodayArticles(date, userId);
  if (articles.length === 0) {
    log.info({ userId, username, date }, '当日没有新增文章');
    return { userId, scored: 0, skipped: false, reason: 'no_articles', total: 0 };
  }

  // 解析每篇文章的来源绑定领域；解析不出的回退到全部激活领域
  const { topicsByArticle, boundCount, fallbackCount } = await resolveArticleTopics(articles, userId, topics);

  log.info(
    { userId, username, articleCount: articles.length, boundCount, fallbackCount },
    '开始 JEV 评分'
  );
  if (fallbackCount > 0) {
    log.warn(
      { userId, date, fallbackCount },
      '部分文章未能解析来源绑定领域，已回退到全部激活领域评分'
    );
  }

  // 触发开始事件
  if (onProgress) {
    try {
      await onProgress({ type: 'start', total: articles.length });
    } catch (e) {
      log.error({ error: e }, '推送评分开始事件失败');
    }
  }

  const db = getDb();
  const articleMap = new Map(articles.map(a => [a.id, a]));
  let inserted = 0;
  let failedCount = 0;

  // 逐篇出分回调：每评完一篇立即写入数据库并实时推向前端
  const handleSingleScore = async (result: any, currentIndex: number, totalCount: number) => {
    if (result.failed) {
      failedCount++;
    }

    try {
      await db
        .insertInto('user_daily_scores')
        .values({
          user_id: userId,
          article_id: result.articleId,
          score_date: date,
          relevance_score: result.relevanceScore,
          matched_domain: result.matchedDomain,
          jev_response: JSON.stringify(result.jevResponse),
        })
        .onConflict(oc =>
          oc.columns(['user_id', 'article_id', 'score_date']).doUpdateSet({
            relevance_score: result.relevanceScore,
            matched_domain: result.matchedDomain,
            jev_response: JSON.stringify(result.jevResponse),
          })
        )
        .execute();
      inserted++;
    } catch (error) {
      log.error({ userId, articleId: result.articleId, error }, '写入评分失败');
    }

    const meta = articleMap.get(result.articleId);
    if (onProgress && meta) {
      try {
        await onProgress({
          type: 'item',
          current: currentIndex,
          total: totalCount,
          latencyMs: result.latencyMs,
          breakdown: result.breakdown,
          article: {
            id: result.articleId,
            title: meta.title,
            url: meta.url,
            summary: meta.summary,
            source_origin: meta.source_origin,
            filter_status: meta.filter_status,
            published_at: meta.published_at,
            created_at: meta.created_at,
            title_zh: meta.title_zh,
            summary_zh: meta.summary_zh,
            relevance_score: result.relevanceScore,
            matched_domain: result.matchedDomain,
            failed: !!result.failed,
          },
        });
      } catch (err) {
        log.error({ articleId: result.articleId, error: err }, '推送单篇评分进度失败');
      }
    }
  };

  // 批量并发评分（内部在每篇完成时立即调用 handleSingleScore）
  const results = await scoreArticlesBatch(
    articles,
    (article) => topicsByArticle.get(article.id) ?? topics,
    config.myDailyConcurrency,
    handleSingleScore
  );

  if (failedCount > 0) {
    log.warn(
      { userId, date, failed: failedCount, total: results.length },
      '部分文章的 JEV 评分失败，已写入占位 0 分'
    );
  }

  const successCount = inserted - failedCount;
  log.info({ userId, username, total: articles.length, inserted, failed: failedCount }, '用户评分完成');

  if (onProgress) {
    try {
      await onProgress({
        type: 'done',
        total: articles.length,
        scored: successCount,
        failed: failedCount,
      });
    } catch (e) {
      log.error({ error: e }, '推送评分完成事件失败');
    }
  }

  // scored 只统计真正拿到 JEV 结果的篇数，失败的那部分单独用 failed 报告
  return { userId, scored: successCount, failed: failedCount, skipped: false };
}

/**
 * 执行所有用户的评分
 */
async function runDailyScoring() {
  const startTime = Date.now();

  log.info('开始每日 JEV 评分任务');

  // 检查 JEV 配置
  try {
    await resolveJevConfig();
  } catch (err) {
    log.warn('未配置 JEV API 密钥，跳过每日评分');
    return;
  }

  // 获取所有 user 角色的用户
  const db = getDb();
  const users = await db
    .selectFrom('users')
    .where('role', '=', 'user')
    .select(['id', 'username'])
    .execute();

  if (users.length === 0) {
    log.info('没有 user 角色的用户，跳过评分');
    return;
  }

  log.info({ userCount: users.length }, '找到需要评分的用户');

  // 逐个用户评分（避免并发过高），日期按各用户时区的当天计算
  const results = [];
  for (const user of users) {
    try {
      const userDate = await getUserLocalDate(user.id);
      const result = await scoreForUser(user.id, user.username, userDate);
      results.push(result);
    } catch (error) {
      // 排队失败（队列已满 / 等待超时）不视为错误，跳过该用户即可
      if (error instanceof ScoringQueueError) {
        log.warn(
          { userId: user.id, username: user.username, reason: error.reason },
          '评分排队失败，跳过该用户'
        );
        results.push({ userId: user.id, scored: 0, skipped: true, reason: error.reason });
        continue;
      }
      log.error({ userId: user.id, username: user.username, error }, '用户评分出错');
      results.push({ userId: user.id, scored: 0, skipped: false, error: true });
    }
  }

  const elapsed = Date.now() - startTime;
  const totalScored = results.reduce((sum, r) => sum + r.scored, 0);
  log.info(
    { users: users.length, totalScored, elapsed: `${elapsed}ms` },
    '每日 JEV 评分任务完成'
  );
}

/**
 * 初始化每日评分调度器
 */
export function initMyDailyScorerScheduler() {
  let task: cron.ScheduledTask | null = null;

  return {
    start() {
      const schedule = config.myDailySchedule;
      task = cron.schedule(schedule, async () => {
        try {
          await runDailyScoring();
        } catch (error) {
          log.error({ error }, '每日评分调度出错');
        }
      });
      log.info({ schedule }, '每日评分调度器已启动');
    },

    async stop() {
      if (task) {
        task.stop();
        task = null;
      }
    },

    // 支持手动触发
    runNow: runDailyScoring,
  };
}
