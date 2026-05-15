import http from '@/lib/http'
import type { TaskResult, PaginatedResponse } from '@/types'

export interface TaskResultQuery {
  instance_id: number
  review_status?: string
  analysis_status?: string
  journal?: string
  year?: number
  min_score?: number
  include_duplicate?: boolean
  keyword?: string
  page?: number
  page_size?: number
  sort_by?: string
  sort_order?: 'asc' | 'desc'
}

export function getTaskResults(params: TaskResultQuery) {
  return http.get<PaginatedResponse<TaskResult>>('/task-results', { params })
}

export function markPass(id: number) {
  return http.put(`/task-results/${id}/pass`)
}

export function markReject(id: number) {
  return http.put(`/task-results/${id}/reject`)
}

export function batchUpdateResults(instanceId: number, data: { ids: number[]; action: 'pass' | 'reject' }) {
  return http.post(`/task-instances/${instanceId}/results/batch-update`, data)
}

export function startDownload(instanceId: number) {
  return http.post(`/task-instances/${instanceId}/download`)
}

export function getDownloadProgress(instanceId: number) {
  return http.get(`/task-instances/${instanceId}/download-progress`)
}
