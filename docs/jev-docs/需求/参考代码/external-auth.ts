/**
 * 外部 API 通用鉴权与用户双轨解析模块
 *
 * 供 /api/external/* 路由复用：
 * 1. 校验服务端环境变量 CLI_API_KEY 与 Header x-api-key（或 query api_key）
 * 2. 支持 username 与 userId 双轨兼容输入
 * 3. 统一返回标准化的 ExternalApiResponse 信封错误，避免各个接口重复实现
 */

import type { Response } from 'express';
import type { AuthRequest } from '../middleware/auth.js';
import { getDb } from '../db.js';
import {
  EXTERNAL_API_CODES,
  externalApiFailure,
  type ExternalApiResponse,
} from './external-api-response.js';

export interface ExternalAuthUser {
  id: number;
  username: string;
  role: 'admin' | 'user' | 'guest';
}

export type ExternalAuthResult =
  | { ok: true; user: ExternalAuthUser }
  | { ok: false; status: number; response: ExternalApiResponse<never> };

export interface VerifyExternalAuthOptions {
  /** 允许访问的角色列表（如 ['admin', 'user']） */
  allowedRoles?: ('admin' | 'user' | 'guest')[];
}

/**
 * 校验外部 API 请求的 API Key 并解析出用户实体
 */
export async function verifyExternalApiAuth(
  req: AuthRequest,
  options: VerifyExternalAuthOptions = {}
): Promise<ExternalAuthResult> {
  const cliApiKey = process.env.CLI_API_KEY;
  if (!cliApiKey) {
    return {
      ok: false,
      status: 500,
      response: externalApiFailure(
        EXTERNAL_API_CODES.CLI_API_KEY_NOT_CONFIGURED,
        '服务端未配置 CLI_API_KEY',
        { details: { requiredAction: 'configure_cli_api_key' } }
      ),
    };
  }

  const apiKeyHeader = req.headers['x-api-key'] as string | undefined;
  const apiKeyQuery = req.query.api_key as string | undefined;
  const providedApiKey = (apiKeyHeader || apiKeyQuery || '').trim();

  if (!providedApiKey) {
    return {
      ok: false,
      status: 401,
      response: externalApiFailure(
        EXTERNAL_API_CODES.MISSING_API_KEY,
        '缺少 API Key（请在请求头提供 x-api-key 或 query 参数 api_key）'
      ),
    };
  }

  if (providedApiKey !== cliApiKey) {
    return {
      ok: false,
      status: 401,
      response: externalApiFailure(
        EXTERNAL_API_CODES.INVALID_API_KEY,
        '无效的 API Key'
      ),
    };
  }

  // 提取用户标识：优先取 username，次取 userId / user_id
  const body = (req.body ?? {}) as Record<string, unknown>;
  const query = (req.query ?? {}) as Record<string, unknown>;

  const rawUsername = body.username ?? query.username;
  const username = typeof rawUsername === 'string' ? rawUsername.trim() : '';

  const rawUserId = body.userId ?? query.userId ?? query.user_id;

  if (!username && (rawUserId === undefined || rawUserId === null || rawUserId === '')) {
    return {
      ok: false,
      status: 400,
      response: externalApiFailure(
        EXTERNAL_API_CODES.MISSING_USER_IDENTIFIER,
        '请提供 username 或 userId'
      ),
    };
  }

  const db = getDb();

  try {
    let userRow: { id: number; username: string; role: 'admin' | 'user' | 'guest' } | undefined;

    if (username) {
      userRow = await db
        .selectFrom('users')
        .where('username', '=', username)
        .select(['id', 'username', 'role'])
        .executeTakeFirst() as typeof userRow;

      if (!userRow) {
        return {
          ok: false,
          status: 404,
          response: externalApiFailure(
            EXTERNAL_API_CODES.USER_NOT_FOUND,
            `用户 '${username}' 不存在`,
            { details: { username } }
          ),
        };
      }
    } else {
      const parsedId = typeof rawUserId === 'number'
        ? rawUserId
        : parseInt(String(rawUserId), 10);

      if (!Number.isInteger(parsedId) || parsedId <= 0) {
        return {
          ok: false,
          status: 400,
          response: externalApiFailure(
            EXTERNAL_API_CODES.INVALID_USER_ID,
            'userId 必须为有效正整数',
            { details: { userId: rawUserId } }
          ),
        };
      }

      userRow = await db
        .selectFrom('users')
        .where('id', '=', parsedId)
        .select(['id', 'username', 'role'])
        .executeTakeFirst() as typeof userRow;

      if (!userRow) {
        return {
          ok: false,
          status: 404,
          response: externalApiFailure(
            EXTERNAL_API_CODES.USER_NOT_FOUND,
            `用户 ID '${parsedId}' 不存在`,
            { details: { userId: parsedId } }
          ),
        };
      }
    }

    // 角色权限校验
    if (options.allowedRoles && options.allowedRoles.length > 0) {
      if (!options.allowedRoles.includes(userRow.role)) {
        return {
          ok: false,
          status: 403,
          response: externalApiFailure(
            EXTERNAL_API_CODES.FORBIDDEN_ROLE,
            `该用户角色 (${userRow.role}) 无权访问此接口（需 ${options.allowedRoles.join(' / ')} 角色）`,
            { details: { userId: userRow.id, username: userRow.username, role: userRow.role } }
          ),
        };
      }
    }

    const user: ExternalAuthUser = {
      id: userRow.id,
      username: userRow.username,
      role: userRow.role,
    };

    req.userId = user.id;
    req.user = user;

    return { ok: true, user };
  } catch (error) {
    const reason = error instanceof Error ? error.message : 'Database error';
    return {
      ok: false,
      status: 500,
      response: externalApiFailure(
        EXTERNAL_API_CODES.INTERNAL_ERROR,
        '查询用户信息时发生数据库异常',
        { retryable: true, details: { reason } }
      ),
    };
  }
}
