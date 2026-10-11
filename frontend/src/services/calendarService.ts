import type { CalendarEventsResponse } from '../types/calendar'
import { apiFetch } from './apiClient'

export const calendarService = {
  listEvents: (from: Date, to: Date) => {
    const query = new URLSearchParams({ from: from.toISOString(), to: to.toISOString() })
    return apiFetch<CalendarEventsResponse>(`/calendar/events?${query}`)
  },
}
