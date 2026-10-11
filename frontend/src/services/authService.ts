import type { User } from '../types/user'
import { apiFetch } from './apiClient'

export interface LoginPayload {
  email: string
  password: string
}

export interface RegisterPayload extends LoginPayload {
  full_name: string
}

export const authService = {
  me: () => apiFetch<User>('/auth/me'),
  login: (payload: LoginPayload) =>
    apiFetch<User>('/auth/login', { method: 'POST', body: JSON.stringify(payload) }),
  register: (payload: RegisterPayload) =>
    apiFetch<User>('/auth/register', { method: 'POST', body: JSON.stringify(payload) }),
  logout: () => apiFetch<void>('/auth/logout', { method: 'POST' }),
}
