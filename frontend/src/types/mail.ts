import type { ConnectionStatus } from './connections'

export interface MailMessage {
  id: string
  account_id: string
  account_email: string
  provider: string
  sender_name: string
  sender_email: string
  subject: string
  snippet: string
  /** ISO date-time. */
  received_at: string
  unread: boolean
  html_link: string
}

export interface MailMessageDetail extends MailMessage {
  recipients: string
  body: string
  /** True when the text was cut because the message is very long. */
  body_truncated: boolean
}

export interface MailAccountResult {
  account_id: string
  account_email: string
  provider: string
  status: ConnectionStatus
  error: 'missing_permission' | 'needs_reauth' | 'provider_unavailable' | null
}

export interface MailMessagesResponse {
  messages: MailMessage[]
  accounts: MailAccountResult[]
}
