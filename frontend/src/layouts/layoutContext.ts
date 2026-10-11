import { useOutletContext } from 'react-router-dom'

import type { MailMessagesResponse } from '../types/mail'

/** Largest number of unread messages counted; beyond it the count shows a plus sign. */
export const UNREAD_LIMIT = 25

export interface LayoutContext {
  /** Unread inbox messages; null while loading or when they could not be read. */
  unread: MailMessagesResponse | null
}

export function useLayoutContext() {
  return useOutletContext<LayoutContext>()
}

export function unreadLabel(count: number): string {
  return count >= UNREAD_LIMIT ? `${UNREAD_LIMIT}+` : String(count)
}
