import http from '@/lib/http'
import type { SystemPrompt } from '@/types'

export function getSystemPrompts() {
  return http.get<SystemPrompt[]>('/system-prompts')
}

export function createSystemPrompt(data: Partial<SystemPrompt>) {
  return http.post<SystemPrompt>('/system-prompts', data)
}

export function updateSystemPrompt(id: number, data: Partial<SystemPrompt>) {
  return http.put<SystemPrompt>(`/system-prompts/${id}`, data)
}

export function deleteSystemPrompt(id: number) {
  return http.delete(`/system-prompts/${id}`)
}
