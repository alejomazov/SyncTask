import type { AuditLog, Page } from '../types/admin'
import type { User } from '../types/user'
import { apiFetch } from './apiClient'

export interface UserListParams {
  search?: string
  page?: number
  page_size?: number
}

export interface AuditLogParams {
  action?: string
  actor_email?: string
  date_from?: string
  date_to?: string
  page?: number
  page_size?: number
}

export interface CreateUserPayload {
  full_name: string
  email: string
  password: string
}

function toQuery(params: object): string {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') query.set(key, String(value))
  }
  const text = query.toString()
  return text ? `?${text}` : ''
}

export const adminService = {
  listUsers: (params: UserListParams = {}) =>
    apiFetch<Page<User>>(`/admin/users${toQuery(params)}`),
  createUser: (payload: CreateUserPayload) =>
    apiFetch<User>('/admin/users', { method: 'POST', body: JSON.stringify(payload) }),
  setUserActive: (userId: string, isActive: boolean) =>
    apiFetch<User>(`/admin/users/${userId}`, {
      method: 'PATCH',
      body: JSON.stringify({ is_active: isActive }),
    }),
  listAuditLogs: (params: AuditLogParams = {}) =>
    apiFetch<Page<AuditLog>>(`/admin/audit-logs${toQuery(params)}`),
}
