import { useState, type FormEvent } from 'react'

import { ApiError } from '../../services/apiClient'
import { settingsService } from '../../services/settingsService'
import type { AiProviderId, AiProviderStatus, Settings } from '../../types/settings'

const PLACEHOLDERS: Record<AiProviderId, string> = {
  anthropic: 'sk-ant-…',
  gemini: 'AIza…',
}

const KEY_SOURCES: Record<AiProviderId, string> = {
  anthropic: 'Se crea en la consola de Anthropic.',
  gemini: 'Se crea en Google AI Studio.',
}

interface ProviderKeyCardProps {
  provider: AiProviderStatus
  /** Model selected before saving, to tell the user when saving a key changes it. */
  selectedModel: string
  onChange: (settings: Settings) => void
}

/** Stores, replaces or removes the user's API key for one model provider. */
export default function ProviderKeyCard({
  provider,
  selectedModel,
  onChange,
}: ProviderKeyCardProps) {
  const [apiKey, setApiKey] = useState('')
  const [message, setMessage] = useState<{ text: string; ok: boolean } | null>(null)
  const [busy, setBusy] = useState(false)

  async function save(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setMessage(null)
    try {
      const updated = await settingsService.saveAiKey(provider.id, apiKey)
      onChange(updated)
      setApiKey('')
      const switchedTo =
        updated.ai_model !== selectedModel
          ? updated.available_models.find((model) => model.id === updated.ai_model)
          : undefined
      setMessage({
        text: switchedTo
          ? `La clave se verificó y quedó guardada. El asistente ahora usa ${switchedTo.name}.`
          : 'La clave se verificó y quedó guardada.',
        ok: true,
      })
    } catch (err) {
      const status = err instanceof ApiError ? err.status : 0
      setMessage({
        text:
          status === 422
            ? 'El proveedor rechazó la clave. Revisa que esté completa y vigente; no se guardó.'
            : status === 503
              ? 'No se pudo verificar la clave en este momento. Inténtalo más tarde.'
              : 'No se pudo guardar la clave.',
        ok: false,
      })
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    if (!window.confirm(`¿Seguro que quieres eliminar tu clave de ${provider.name}?`)) return
    setBusy(true)
    try {
      onChange(await settingsService.removeAiKey(provider.id))
      setMessage({ text: 'La clave se eliminó.', ok: true })
    } catch {
      setMessage({ text: 'No se pudo eliminar la clave.', ok: false })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="provider-card">
      <h3>
        {provider.name}{' '}
        {provider.key_configured ? (
          <>
            <span className="badge badge-ok">Clave configurada</span>{' '}
            <code>…{provider.key_last4}</code>
          </>
        ) : (
          <span className="badge badge-off">Sin clave</span>
        )}
      </h3>
      <form className="toolbar" onSubmit={save}>
        <label>
          {provider.key_configured ? 'Reemplazar clave' : 'Clave de la API'}
          <input
            type="password"
            autoComplete="off"
            placeholder={PLACEHOLDERS[provider.id]}
            required
            minLength={20}
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
          />
        </label>
        <button type="submit" disabled={busy}>
          {busy ? 'Verificando…' : 'Guardar clave'}
        </button>
        {provider.key_configured && (
          <button
            type="button"
            className="button-secondary"
            disabled={busy}
            onClick={() => void remove()}
          >
            Eliminar clave
          </button>
        )}
      </form>
      <p className="form-hint">{KEY_SOURCES[provider.id]}</p>
      {message && (
        <p
          className={message.ok ? 'form-success' : 'form-error'}
          role={message.ok ? 'status' : 'alert'}
        >
          {message.text}
        </p>
      )}
    </div>
  )
}
