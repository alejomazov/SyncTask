export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface AuditLog {
  id: string
  actor_id: string | null
  actor_email: string | null
  action: string
  target_type: string | null
  target_id: string | null
  detail: Record<string, unknown>
  ip_address: string | null
  created_at: string
}
