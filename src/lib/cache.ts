/**
 * P0-2: Lightweight in-memory cache for API list responses.
 *
 * Usage (normal — cache hit on tab-switch):
 *   const getFoo = withCache(
 *     (params) => http.get('/foo', { params }),
 *     (params) => `foo:list:${JSON.stringify(params)}`
 *   )
 *   await getFoo(params)           // returns cached data when available
 *
 * Usage (after mutation — always fresh):
 *   import { fresh } from '@/lib/cache'
 *   const getFooFresh = fresh(getFoo, (p) => `foo:list:${JSON.stringify(p)}`)
 *   await getFooFresh(params)      // busts cache, fetches from server
 */

const store = new Map<string, { data: unknown; timestamp: number }>()
const DEFAULT_TTL = 30_000 // 30 seconds

function getCached<T>(key: string): T | null {
  const entry = store.get(key)
  if (!entry) return null
  if (Date.now() - entry.timestamp > DEFAULT_TTL) {
    store.delete(key)
    return null
  }
  return entry.data as T
}

function setCache<T>(key: string, data: T): void {
  store.set(key, { data, timestamp: Date.now() })
}

/**
 * Wraps an async function with an in-memory cache.
 * Returns the cached function with a `.fresh()` attached for bypassing cache.
 */
export function withCache<T extends (...args: any[]) => Promise<any>>(
  fn: T,
  cacheKey: (...args: Parameters<T>) => string,
): T & { fresh: (...args: Parameters<T>) => Promise<ReturnType<T>> } {
  const result = (async (...args: Parameters<T>): Promise<ReturnType<T>> => {
    const key = cacheKey(...args)
    const hit = getCached<ReturnType<T>>(key)
    if (hit) return hit
    const resolved = await fn(...args)
    setCache(key, resolved)
    return resolved
  }) as T & { fresh: (...args: Parameters<T>) => Promise<ReturnType<T>> }

  result.fresh = async (...args: Parameters<T>): Promise<ReturnType<T>> => {
    const key = cacheKey(...args)
    const prefix = key.split(/[:]/)[0]
    if (prefix) clearCache(prefix + ':')
    const resolved = await fn(...args)
    setCache(key, resolved)
    return resolved
  }

  return result
}

/**
 * Clears all cached entries, or entries whose key starts with `prefix`.
 */
export function clearCache(prefix?: string): void {
  if (!prefix) {
    store.clear()
    return
  }
  for (const key of store.keys()) {
    if (key.startsWith(prefix)) store.delete(key)
  }
}
