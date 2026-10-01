/**
 * JEV 精排：对向量召回的候选做相关性打分，供排序使用。
 *
 * 设计见 docs/jev-docs/需求/语义检索-JEV精排设计方案.md：
 * - 一个批次的多条候选放进**同一次请求**（共享 state），每候选问 `noul` + `score`，
 *   批级再问 1 个 `choice` 作为显式弃权。
 * - 综合分 `finalScore = noul × (score / 最高档位)`，与 my-daily 同口径。
 * - 逐字校验答案；批次级降级：单批失败仅该批候选回退，全部失败返回 `null`，
 *   由调用方回退到现有 rerank/向量分排序。
 */

import { logger } from '../logger.js';
import { config as appConfig } from '../config.js';
import { decryptAPIKey } from '../utils/crypto.js';
import { getActiveConfigByType } from '../api/llm-configs.js';
import {
  callJevApi,
  resolveJevConfig,
  normalizeJevApiUrl,
  JEV_DEFAULT_MODEL,
  type ResolvedJevConfig,
} from '../jev.js';

const log = logger.child({ module: 'vector-jev-rerank' });

/** `score` 问题的档位描述（0–4 五档，与 my-daily `relevance_level` 一致） */
export const RELEVANCE_LEVELS = [
  '完全不相关，与查询主题无任何关联',
  '边缘相关，仅涉及相邻领域或间接关联',
  '中度相关，涉及查询主题的部分方面',
  '高度相关，直接讨论查询的核心主题',
  '完全匹配，深入讨论查询核心主题且包含关键词',
];

const MAX_LEVEL = RELEVANCE_LEVELS.length - 1;

/** 每条候选送 JEV 的文本上限（固定截断，控制成本与注入面） */
const MAX_ITEM_CHARS = 800;

export interface JevRerankItem {
  articleId: number;
  /** 候选文本（标题 + 摘要/正文），内部会固定截断 */
  text: string;
}

export interface JevRerankScore {
  /** 综合分 0-1 = noul × (score / 4) */
  value: number;
  /** score 原值 0-4 */
  relevanceLevel: number;
}

export interface JevRerankOutcome {
  scores: Map<number, JevRerankScore>;
  /** 批级 choice 弃权答案；无有效答案时为 null */
  hasMatch: boolean | null;
  usage: { input_tokens: number; output_tokens: number };
  scoreMs: number;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

/**
 * 解析检索用的 JEV 配置：优先当前用户的 llm_configs（config_type='jev'），
 * 回退到全局解析（provider='typesafe' / .env `TYPESAFE_API_KEY`）。
 * 两者皆无（或配置读取失败）时返回 null，表示"未配置 JEV"。
 */
async function resolveSearchJevConfig(userId: number): Promise<ResolvedJevConfig | null> {
  try {
    const dbConfig = await getActiveConfigByType(userId, 'jev');
    if (dbConfig && dbConfig.api_key_encrypted) {
      const apiKey = decryptAPIKey(dbConfig.api_key_encrypted, appConfig.llmEncryptionKey);
      if (apiKey) {
        return {
          apiUrl: normalizeJevApiUrl(dbConfig.base_url),
          apiKey,
          model: dbConfig.model || JEV_DEFAULT_MODEL,
        };
      }
    }
  } catch (error) {
    log.debug({ error, userId }, '读取用户 JEV 配置失败，回退全局配置');
  }

  try {
    return await resolveJevConfig();
  } catch {
    return null;
  }
}

/**
 * 构建单个批次的 JEV 请求体。
 * `state` 放事实（查询 + 候选），`criteria` 放判断标准，问题 id 由下标派生。
 */
export function buildJevRerankRequest(
  query: string,
  items: JevRerankItem[],
  model: string = JEV_DEFAULT_MODEL
) {
  const state = {
    request: query,
    results: items.map((item, index) => ({
      index,
      content: item.text.slice(0, MAX_ITEM_CHARS),
    })),
  };

  const questions: Record<string, any> = {};

  items.forEach((_, i) => {
    questions[`r${i}`] = {
      type: 'noul',
      instructions: `根据 \`request\` 中用户的检索意图，判断 \`results[${i}]\` 中的候选是否与其主题相关。`,
      criteria: {
        true: '候选讨论用户所问的同一主题，即使只是简要提及或作为多个话题之一',
        false: '候选只与请求共享词面（同词异义、同名不同主体）或完全无关',
      },
    };
    questions[`s${i}`] = {
      type: 'score',
      instructions: `评估 \`results[${i}]\` 与 \`request\` 检索意图的相关程度。`,
      criteria: RELEVANCE_LEVELS,
    };
  });

  questions.has_match = {
    type: 'choice',
    instructions: '`results` 中是否至少有一条候选真正涉及 `request` 的主题？',
    criteria: {
      yes: '至少有一条候选真正讨论用户查询的主题',
      no: '所有候选都只共享词面或与查询主题无关',
    },
  };

  return { state, model, questions };
}

/**
 * 解析单个批次返回的 answers，做严格校验：
 * 缺失 / 非法 / 越界一律不产分（调用方对该候选回退向量分）。
 */
export function parseJevRerankAnswers(
  answers: any,
  items: JevRerankItem[]
): { scores: Array<{ articleId: number; value: number; relevanceLevel: number }>; hasMatch: boolean | null } {
  const scores: Array<{ articleId: number; value: number; relevanceLevel: number }> = [];

  for (let i = 0; i < items.length; i++) {
    const noulAnswer = answers?.[`r${i}`];
    const scoreAnswer = answers?.[`s${i}`];

    const noul =
      noulAnswer?.type === 'noul' && Number.isFinite(noulAnswer.noul) ? Number(noulAnswer.noul) : null;
    const level =
      scoreAnswer?.type === 'score' && Number.isFinite(scoreAnswer.score)
        ? Number(scoreAnswer.score)
        : null;

    if (noul === null || level === null) continue;

    const clampedNoul = clamp(noul, 0, 1);
    const clampedLevel = clamp(level, 0, MAX_LEVEL);
    scores.push({
      articleId: items[i].articleId,
      value: Math.round(clampedNoul * (clampedLevel / MAX_LEVEL) * 100) / 100,
      relevanceLevel: clampedLevel,
    });
  }

  let hasMatch: boolean | null = null;
  const choiceAnswer = answers?.has_match;
  if (choiceAnswer?.type === 'choice') {
    if (choiceAnswer.choice === 'yes') hasMatch = true;
    else if (choiceAnswer.choice === 'no') hasMatch = false;
  }

  return { scores, hasMatch };
}

/**
 * 对候选做 JEV 精排打分。
 *
 * @returns 成功时返回打分结果；未启用 / 未配置 / 全部批次失败时返回 `null`。
 */
export async function jevRerank(
  query: string,
  items: JevRerankItem[],
  userId: number
): Promise<JevRerankOutcome | null> {
  if (!appConfig.searchJevEnabled || items.length === 0) return null;

  const jevConfig = await resolveSearchJevConfig(userId);
  if (!jevConfig) {
    log.debug({ userId }, '未配置 JEV，检索精排跳过 JEV');
    return null;
  }

  const startedAt = Date.now();
  const batchSize = Math.max(1, appConfig.searchJevBatch);
  const scores = new Map<number, JevRerankScore>();
  const usage = { input_tokens: 0, output_tokens: 0 };
  let hasMatch: boolean | null = null;
  let anySuccess = false;
  let lastError: unknown = null;

  const batches: JevRerankItem[][] = [];
  for (let i = 0; i < items.length; i += batchSize) {
    batches.push(items.slice(i, i + batchSize));
  }

  await Promise.all(
    batches.map(async (batch) => {
      try {
        const body = buildJevRerankRequest(query, batch, jevConfig.model);
        const result = await callJevApi(body, jevConfig);
        anySuccess = true;

        const parsed = parseJevRerankAnswers(result?.answers, batch);
        for (const score of parsed.scores) {
          scores.set(score.articleId, { value: score.value, relevanceLevel: score.relevanceLevel });
        }
        if (hasMatch === null) hasMatch = parsed.hasMatch;

        if (result?.usage) {
          usage.input_tokens += Number(result.usage.input_tokens) || 0;
          usage.output_tokens += Number(result.usage.output_tokens) || 0;
        }
      } catch (error) {
        lastError = error;
        log.warn(
          { error, userId, batchSize: batch.length },
          'JEV 精排批次失败，该批候选回退向量分'
        );
      }
    })
  );

  const scoreMs = Date.now() - startedAt;

  if (!anySuccess || scores.size === 0) {
    log.warn(
      { error: lastError, userId, candidates: items.length, scoreMs },
      'JEV 精排全部失败，回退现有评分排序'
    );
    return null;
  }

  log.info(
    { userId, candidates: items.length, scored: scores.size, hasMatch, scoreMs },
    'JEV 精排完成'
  );

  return { scores, hasMatch, usage, scoreMs };
}
