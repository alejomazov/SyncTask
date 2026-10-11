import type { ExecutionMode, Settings } from '../types/settings'
import { apiFetch } from './apiClient'

export const settingsService = {
  get: () => apiFetch<Settings>('/settings'),
  setExecutionMode: (mode: ExecutionMode) =>
    apiFetch<Settings>('/settings', {
      method: 'PATCH',
      body: JSON.stringify({ execution_mode: mode }),
    }),
  saveAiKey: (apiKey: string) =>
    apiFetch<Settings>('/settings/ai-key', {
      method: 'PUT',
      body: JSON.stringify({ api_key: apiKey }),
    }),
  removeAiKey: () => apiFetch<Settings>('/settings/ai-key', { method: 'DELETE' }),
}
