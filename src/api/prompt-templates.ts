import http from '@/lib/http'
import { withCache, clearCache } from '@/lib/cache'
import type { PromptTemplate, PaginatedResponse } from '@/types'

export const getPromptTemplates = withCache(
  (params = {}) => http.get<PaginatedResponse<PromptTemplate>>('/prompt-templates', { params }),
  (params = {}) => `prompt-templates:list:${JSON.stringify(params)}`
)

export function invalidatePromptTemplatesCache() {
  clearCache('prompt-templates:')
}

export function createPromptTemplate(data: Partial<PromptTemplate>) {
  return http.post<PromptTemplate>('/prompt-templates', data)
}

export function updatePromptTemplate(id: number, data: Partial<PromptTemplate>) {
  return http.put<PromptTemplate>(`/prompt-templates/${id}`, data)
}

export function deletePromptTemplate(id: number) {
  return http.delete(`/prompt-templates/${id}`)
}
