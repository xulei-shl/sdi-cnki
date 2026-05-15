import http from '@/lib/http'
import type { User } from '@/types'

export function getUsers() {
  return http.get<User[]>('/users')
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
