import http from '@/lib/http'
import type { MetaTask, PaginatedResponse } from '@/types'

export interface MetaTaskQuery {
  keyword?: string
  date_from?: string
  date_to?: string
  page?: number
  page_size?: number
}

export function getMetaTasks(params: MetaTaskQuery = {}) {
  return http.get<PaginatedResponse<MetaTask>>('/meta-tasks', { params })
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
