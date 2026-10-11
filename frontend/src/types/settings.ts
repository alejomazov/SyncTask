export type ExecutionMode = 'confirm' | 'automatic'

export interface Settings {
  execution_mode: ExecutionMode
  ai_key_configured: boolean
  ai_key_last4: string | null
  ai_model: string
}
