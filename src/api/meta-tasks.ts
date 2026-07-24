import http from '@/lib/http'
import { withCache, clearCache } from '@/lib/cache'
import type { MetaTask, DedupCandidate, PaginatedResponse } from '@/types'

export interface MetaTaskQuery {
  keyword?: string
  date_from?: string
  date_to?: string
  page?: number
  page_size?: number
}

export const getMetaTasks = withCache(
  (params: MetaTaskQuery = {}) => http.get<PaginatedResponse<MetaTask>>('/meta-tasks', { params }),
  (params: MetaTaskQuery = {}) => `meta-tasks:list:${JSON.stringify(params)}`
)

export function invalidateMetaTasksCache() {
  clearCache('meta-tasks:')
}

export function getMetaTask(id: number) {
  return http.get<MetaTask>(`/meta-tasks/${id}`)
}

export function createMetaTask(data: Partial<MetaTask>) {
  return http.post<MetaTask>('/meta-tasks', data)
}

export function updateMetaTask(id: number, data: Partial<MetaTask>) {
  return http.put<MetaTask>(`/meta-tasks/${id}`, data)
}

export function deleteMetaTask(id: number) {
  return http.delete(`/meta-tasks/${id}`)
}

export function executeMetaTask(id: number, autoRun: boolean = true) {
  return http.post(`/meta-tasks/${id}/execute`, { auto_run: autoRun })
}

export function getDedupCandidates() {
  return http.get<DedupCandidate[]>('/meta-tasks/dedup-candidates')
}

export function cloneMetaTask(id: number) {
  return http.post<{ id: number; name: string }>(`/meta-tasks/${id}/clone`)
}
