import http from '@/lib/http'
import { withCache, clearCache } from '@/lib/cache'
import type { TaskInstance, PaginatedResponse } from '@/types'

export interface TaskInstanceQuery {
  keyword?: string
  template_keyword?: string
  status_filter?: string
  date_from?: string
  date_to?: string
  page?: number
  page_size?: number
}

export const getTaskInstances = withCache(
  (params: TaskInstanceQuery = {}) => http.get<PaginatedResponse<TaskInstance>>('/task-instances', { params }),
  (params: TaskInstanceQuery = {}) => `task-instances:list:${JSON.stringify(params)}`
)

export function getTaskInstance(id: number) {
  return http.get<TaskInstance>(`/task-instances/${id}`)
}

export function invalidateTaskInstancesCache() {
  clearCache('task-instances:')
}

export function deleteTaskInstance(id: number) {
  return http.delete(`/task-instances/${id}`)
}

export function runTaskInstance(id: number) {
  return http.post(`/task-instances/${id}/run`)
}

export function updateTaskInstanceParams(id: number, searchParams: Record<string, any>) {
  return http.patch(`/task-instances/${id}/params`, { search_params: searchParams })
}

export function completeTaskInstance(id: number) {
  return http.post(`/task-instances/${id}/complete`)
}

export function importExcelResults(instanceId: number, file: File) {
  const formData = new FormData()
  formData.append('file', file)
  return http.post<{ total: number; valid: number; duplicate: number }>(`/task-instances/${instanceId}/import-excel`, formData)
}
