export type ConnectionStatus = 'active' | 'needs_reauth'

export interface ConnectedAccount {
  id: string
  provider: string
  account_email: string
  status: ConnectionStatus
  /** False when the account was connected without the permission to read mail. */
  mail_enabled: boolean
  created_at: string
}

export interface AdminConnection extends ConnectedAccount {
  user_id: string
  user_email: string
  user_full_name: string
  token_expires_at: string
  updated_at: string
}
