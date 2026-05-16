import http from '@/lib/http'
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

export function getTaskInstances(params: TaskInstanceQuery = {}) {
  return http.get<PaginatedResponse<TaskInstance>>('/task-instances', { params })
}

export function getTaskInstance(id: number) {
  return http.get<TaskInstance>(`/task-instances/${id}`)
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
