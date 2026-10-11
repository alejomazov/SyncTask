import type { ConnectedAccount } from '../types/connections'
import { apiFetch } from './apiClient'

export const connectionsService = {
  list: () => apiFetch<ConnectedAccount[]>('/connections'),
  disconnect: (accountId: string) =>
    apiFetch<void>(`/connections/${accountId}`, { method: 'DELETE' }),
  googleAuthorizationUrl: async () =>
    (await apiFetch<{ authorization_url: string }>('/integrations/google/authorize'))
      .authorization_url,
}
