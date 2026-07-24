import http from '@/lib/http'
import { withCache, clearCache } from '@/lib/cache'
import type { User, PaginatedResponse } from '@/types'

export const getUsers = withCache(
  (params = {}) => http.get<PaginatedResponse<User>>('/users', { params }),
  (params = {}) => `users:list:${JSON.stringify(params)}`
)

export function invalidateUsersCache() {
  clearCache('users:')
}

export function createUser(data: Partial<User> & { password: string }) {
  return http.post<User>('/users', data)
}

export function updateUser(id: number, data: Partial<User> & { password?: string }) {
  return http.put<User>(`/users/${id}`, data)
}

export function deleteUser(id: number) {
  return http.delete(`/users/${id}`)
}
