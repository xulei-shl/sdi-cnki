import http from '@/lib/http'
import type { AuthResponse } from '@/types'

export function login(username: string, password: string) {
  return http.post<AuthResponse>('/auth/login', { username, password })
}

export function refreshToken(refreshToken: string) {
  return http.post('/auth/refresh', { refresh_token: refreshToken })
}

export function getMe() {
  return http.get('/auth/me')
}

export function logout() {
  return http.post('/auth/logout')
}
