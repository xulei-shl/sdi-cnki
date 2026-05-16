import http from '@/lib/http'
import type { PromptTemplate, PaginatedResponse } from '@/types'

export function getPromptTemplates(params = {}) {
  return http.get<PaginatedResponse<PromptTemplate>>('/prompt-templates', { params })
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
