import { config } from '../config.js';
import { getUserSetting } from './settings.js';

/**
 * 读取用户时区设置，默认回退到全局配置
 */
export async function getUserTimezone(userId: number): Promise<string> {
  if (!userId) {
    return config.defaultTimezone;
  }
  const setting = await getUserSetting(userId, 'timezone');
  return setting || config.defaultTimezone;
}

/**
 * 获取用户时区下的当前日期（YYYY-MM-DD 格式）
 * @param userId - 用户 ID
 * @returns 用户时区下的当前日期字符串
 */
export async function getUserLocalDate(userId: number): Promise<string> {
  const timezone = await getUserTimezone(userId);
  return getLocalDateInTimezone(timezone);
}

/**
 * 获取指定时区下的当前日期（YYYY-MM-DD 格式）
 * @param timezone - 时区字符串
 * @returns 该时区下的当前日期字符串
 */
function getLocalDateInTimezone(timezone: string): string {
  const formatter = new Intl.DateTimeFormat('en-CA', {
    timeZone: timezone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  });

  const parts = formatter.formatToParts(new Date());
  const year = parts.find(p => p.type === 'year')?.value ?? '';
  const month = parts.find(p => p.type === 'month')?.value ?? '';
  const day = parts.find(p => p.type === 'day')?.value ?? '';

  return `${year}-${month}-${day}`;
}

/**
 * 根据本地自然日计算 UTC 查询区间
 */
export function buildUtcRangeFromLocalDate(
  dateStr: string,
  timezone?: string
): [string, string] {
  const resolvedTimezone = timezone || config.defaultTimezone;
  const [year, month, day] = parseDateParts(dateStr);

  const startRef = new Date(Date.UTC(year, month - 1, day, 0, 0, 0, 0));
  const endRef = new Date(Date.UTC(year, month - 1, day, 23, 59, 59, 999));

  const startUtc = new Date(startRef.getTime() - getTimezoneOffsetMs(startRef, resolvedTimezone));
  const endUtc = new Date(endRef.getTime() - getTimezoneOffsetMs(endRef, resolvedTimezone));

  return [startUtc.toISOString(), endUtc.toISOString()];
}

function parseDateParts(dateStr: string): [number, number, number] {
  const parts = dateStr?.split('-').map((v) => Number(v)) ?? [];
  if (parts.length === 3 && parts.every((n) => Number.isFinite(n))) {
    return parts as [number, number, number];
  }

  const fallback = new Date(dateStr);
  if (Number.isNaN(fallback.getTime())) {
    throw new Error(`Invalid date string: ${dateStr}`);
  }

  return [
    fallback.getUTCFullYear(),
    fallback.getUTCMonth() + 1,
    fallback.getUTCDate(),
  ];
}

function getTimezoneOffsetMs(date: Date, timezone: string): number {
  const formatter = new Intl.DateTimeFormat('en-US', {
    timeZone: timezone,
    hour12: false,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });

  const parts = formatter.formatToParts(date);
  const filled: Record<string, string> = {};

  for (const part of parts) {
    if (part.type !== 'literal') {
      filled[part.type] = part.value;
    }
  }

  const zonedTime = Date.UTC(
    Number(filled.year),
    Number(filled.month) - 1,
    Number(filled.day),
    Number(filled.hour),
    Number(filled.minute),
    Number(filled.second)
  );

  return zonedTime - date.getTime();
}
