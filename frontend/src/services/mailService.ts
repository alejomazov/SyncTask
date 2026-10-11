import type { MailMessageDetail, MailMessagesResponse } from '../types/mail'
import { apiFetch } from './apiClient'

export const mailService = {
  listMessages: (limit: number, unreadOnly = false) =>
    apiFetch<MailMessagesResponse>(`/mail/messages?limit=${limit}&unread=${unreadOnly}`),
  getMessage: (accountId: string, messageId: string) =>
    apiFetch<MailMessageDetail>(`/mail/messages/${accountId}/${messageId}`),
}
