import type { ConnectionStatus } from './connections'

export interface CalendarEvent {
  id: string
  account_id: string
  account_email: string
  provider: string
  title: string
  /** ISO date for all-day events, ISO date-time with offset otherwise. */
  start: string
  end: string
  all_day: boolean
  location: string | null
  html_link: string | null
}

export interface CalendarAccountResult {
  account_id: string
  account_email: string
  provider: string
  status: ConnectionStatus
  error: 'needs_reauth' | 'provider_unavailable' | null
}

export interface CalendarEventsResponse {
  events: CalendarEvent[]
  accounts: CalendarAccountResult[]
}
