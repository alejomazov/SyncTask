const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

let onUnauthorized: (() => void) | null = null

/** Registers the callback run when a request fails because the session is missing or expired. */
export function setUnauthorizedHandler(handler: (() => void) | null) {
  onUnauthorized = handler
}

async function request(path: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })

  if (!response.ok) {
    if (response.status === 401) onUnauthorized?.()
    const body = await response.json().catch(() => null)
    const detail = typeof body?.detail === 'string' ? body.detail : response.statusText
    throw new ApiError(response.status, detail)
  }
  return response
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await request(path, init)
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

/**
 * Sends a POST request and reads the reply as Server-Sent Events, calling `onEvent` with the
 * parsed `data` of each event as it arrives.
 */
export async function apiStream<T>(
  path: string,
  body: unknown,
  onEvent: (event: T) => void,
): Promise<void> {
  const response = await request(path, { method: 'POST', body: JSON.stringify(body) })
  if (!response.body) throw new ApiError(response.status, 'Empty response')

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += value
    // Events are separated by a blank line; keep the unfinished tail in the buffer.
    const chunks = buffer.split('\n\n')
    buffer = chunks.pop() ?? ''
    for (const chunk of chunks) {
      const data = chunk
        .split('\n')
        .filter((line) => line.startsWith('data: '))
        .map((line) => line.slice('data: '.length))
        .join('\n')
      if (data) onEvent(JSON.parse(data) as T)
    }
  }
}
