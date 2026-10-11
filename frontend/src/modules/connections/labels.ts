import type { ConnectionStatus } from '../../types/connections'

export const PROVIDER_LABELS: Record<string, string> = {
  google: 'Google',
}

export const STATUS_LABELS: Record<ConnectionStatus, string> = {
  active: 'Conectada',
  needs_reauth: 'Requiere reconexión',
}

export function providerLabel(provider: string): string {
  return PROVIDER_LABELS[provider] ?? provider
}
