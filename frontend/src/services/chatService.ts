import type { ChatEvent, Interaction } from '../types/chat'
import { apiFetch, apiStream } from './apiClient'

export const chatService = {
  /** Interactions of the current conversation, oldest first. */
  listConversation: () => apiFetch<Interaction[]>('/chat/interactions'),
  sendMessage: (message: string, onEvent: (event: ChatEvent) => void) =>
    apiStream<ChatEvent>(
      '/chat/messages',
      { message, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone },
      onEvent,
    ),
  confirmAction: (interactionId: string, actionId: string) =>
    apiFetch<Interaction>(`/chat/interactions/${interactionId}/actions/${actionId}/confirm`, {
      method: 'POST',
    }),
  discardAction: (interactionId: string, actionId: string) =>
    apiFetch<Interaction>(`/chat/interactions/${interactionId}/actions/${actionId}/discard`, {
      method: 'POST',
    }),
  resetConversation: () => apiFetch<void>('/chat/conversation/reset', { method: 'POST' }),
}
