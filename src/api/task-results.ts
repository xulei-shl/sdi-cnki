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
  download_status?: string
  keyword?: string
  page?: number
  page_size?: number
  sort_by?: string
  sort_order?: 'asc' | 'desc'
}

export function getTaskResults(instanceId: number, params: Omit<TaskResultQuery, 'instance_id'>) {
  return http.get<PaginatedResponse<TaskResult>>(`/task-instances/${instanceId}/results`, { params })
}

export function markPass(id: number, isPassed: boolean = true) {
  return http.put(`/task-results/${id}/pass`, { is_passed: isPassed })
}

export function markReject(id: number) {
  return http.put(`/task-results/${id}/reject`)
}

export function batchUpdateResults(instanceId: number, data: { result_ids: number[]; action: 'pass' | 'reject' }) {
  return http.post(`/task-instances/${instanceId}/results/batch-update`, data)
}

export function retryAnalysis(instanceId: number) {
  return http.post(`/task-instances/${instanceId}/retry-analysis`)
}

export function startDownload(instanceId: number) {
  return http.post(`/task-instances/${instanceId}/download`)
}

export function getDownloadProgress(instanceId: number) {
  return http.get(`/task-instances/${instanceId}/download-progress`)
}

export function startExport(instanceId: number) {
  return http.post<{ export_id: number; status: string; message: string }>(`/task-instances/${instanceId}/export`)
}

export async function downloadExportFile(exportId: number) {
  const response = await http.get(`/exports/${exportId}/download`, { responseType: 'blob' })
  const disposition = response.headers['content-disposition'] || ''
  const match = disposition.match(/filename="?(.+?)"?$/)
  const filename = match?.[1] || `export_${exportId}.zip`
  const url = window.URL.createObjectURL(response.data)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.URL.revokeObjectURL(url)
}

export function getExportStatus(exportId: number) {
  return http.get<{
    id: number
    task_instance_id: number
    status: string
    file_path: string | null
    file_size: number | null
    error_message: string | null
    expires_at: string | null
    created_at: string
    completed_at: string | null
  }>(`/exports/${exportId}/status`)
}
