export type ActionStatus = 'pending' | 'executed' | 'rejected' | 'discarded' | 'failed'

export interface AssistantAction {
  id: string
  tool: string
  input: Record<string, unknown>
  summary: string
  status: ActionStatus
  result: string | null
}

export interface Interaction {
  id: string
  instruction: string
  response: string
  actions: AssistantAction[]
  status: 'completed' | 'error'
  created_at: string
}

export type ChatErrorCode =
  | 'invalid_key'
  | 'key_without_access'
  | 'rate_limited'
  | 'provider_rejected'
  | 'provider_unavailable'

export type ChatEvent =
  | { type: 'text'; delta: string }
  | { type: 'status'; tool: string }
  | { type: 'action'; interaction_id: string; action: AssistantAction }
  | { type: 'error'; code: ChatErrorCode }
  | { type: 'done'; interaction_id: string }
