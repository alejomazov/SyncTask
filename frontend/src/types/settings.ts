export type ExecutionMode = 'confirm' | 'automatic'

export type AiProviderId = 'anthropic' | 'gemini'

export interface AiModelOption {
  id: string
  name: string
  provider: AiProviderId
}

export interface AiProviderStatus {
  id: AiProviderId
  name: string
  key_configured: boolean
  key_last4: string | null
}

export interface Settings {
  execution_mode: ExecutionMode
  ai_model: string
  ai_provider: AiProviderId
  /** True when the provider of the selected model has a key stored. */
  assistant_ready: boolean
  providers: AiProviderStatus[]
  available_models: AiModelOption[]
}
