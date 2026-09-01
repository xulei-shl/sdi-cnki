import http from '@/lib/http'
import { withCache, clearCache } from '@/lib/cache'
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

export const getTaskResults = withCache(
  (instanceId: number, params: Omit<TaskResultQuery, 'instance_id'>) =>
    http.get<PaginatedResponse<TaskResult>>(`/task-instances/${instanceId}/results`, { params }),
  (instanceId: number, params: Omit<TaskResultQuery, 'instance_id'>) =>
    `task-results:list:${instanceId}:${JSON.stringify(params)}`
)

export function invalidateTaskResultsCache(instanceId?: number) {
  if (instanceId) clearCache(`task-results:list:${instanceId}`)
  else clearCache('task-results:')
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

export function retryDownload(instanceId: number, resultId: number) {
  return http.post<{ download_status: string; pdf_path: string | null; file_size: number | null }>(
    `/task-instances/${instanceId}/results/${resultId}/retry-download`
  )
}

export function getDownloadProgress(instanceId: number) {
  return http.get(`/task-instances/${instanceId}/download-progress`)
}

export function startExport(instanceId: number, includePdfs: boolean = true) {
  return http.post<{ export_id: number; status: string; message: string }>(
    `/task-instances/${instanceId}/export`,
    { include_pdfs: includePdfs },
  )
}

export async function downloadExportFile(
  exportId: number,
  onProgress?: (loaded: number, total: number) => void,
): Promise<void> {
  const token = localStorage.getItem('access_token') || ''
  const res = await fetch(`/api/v1/exports/${exportId}/download`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `下载失败 (${res.status})`)
  }
  const contentDisposition = res.headers.get('Content-Disposition') || ''
  const match = contentDisposition.match(/filename="?(.+?)"?$/)
  const filename = match?.[1] || `export_${exportId}.zip`
  const total = Number(res.headers.get('Content-Length')) || 0
  const reader = res.body?.getReader()
  if (!reader) throw new Error('浏览器不支持流式下载')
  const chunks: BlobPart[] = []
  let loaded = 0
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    chunks.push(value)
    loaded += value.length
    onProgress?.(loaded, total)
  }
  const blob = new Blob(chunks, { type: 'application/zip' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
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
