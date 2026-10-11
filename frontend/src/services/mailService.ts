import type { MailMessageDetail, MailMessagesResponse } from '../types/mail'
import { apiFetch } from './apiClient'

export const mailService = {
  listMessages: (limit: number) => apiFetch<MailMessagesResponse>(`/mail/messages?limit=${limit}`),
  getMessage: (accountId: string, messageId: string) =>
    apiFetch<MailMessageDetail>(`/mail/messages/${accountId}/${messageId}`),
}
