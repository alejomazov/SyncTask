import { useEffect, useState, type FormEvent } from 'react'

import { ApiError } from '../../services/apiClient'
import { settingsService } from '../../services/settingsService'
import type { ExecutionMode, Settings } from '../../types/settings'

const MODES: { id: ExecutionMode; label: string; description: string }[] = [
  {
    id: 'confirm',
    label: 'Confirmar cada acción',
    description: 'El asistente propone la acción y espera tu confirmación antes de ejecutarla.',
  },
  {
    id: 'automatic',
    label: 'Ejecutar automáticamente',
    description:
      'El asistente ejecuta las acciones de inmediato. Eliminar tareas siempre pide confirmación.',
  },
]

type Message = { text: string; ok: boolean }

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings | null>(null)
  const [apiKey, setApiKey] = useState('')
  const [keyMessage, setKeyMessage] = useState<Message | null>(null)
  const [modeMessage, setModeMessage] = useState<Message | null>(null)
  const [busy, setBusy] = useState(false)
  const [loadFailed, setLoadFailed] = useState(false)

  useEffect(() => {
    settingsService
      .get()
      .then(setSettings)
      .catch(() => setLoadFailed(true))
  }, [])

  async function saveKey(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setKeyMessage(null)
    try {
      setSettings(await settingsService.saveAiKey(apiKey))
      setApiKey('')
      setKeyMessage({ text: 'La clave se verificó y quedó guardada.', ok: true })
    } catch (err) {
      const status = err instanceof ApiError ? err.status : 0
      setKeyMessage({
        text:
          status === 422
            ? 'Anthropic rechazó la clave. Revisa que esté completa y vigente; no se guardó.'
            : status === 503
              ? 'No se pudo verificar la clave con Anthropic en este momento. Inténtalo más tarde.'
              : 'No se pudo guardar la clave.',
        ok: false,
      })
    } finally {
      setBusy(false)
    }
  }

  async function removeKey() {
    if (!window.confirm('¿Seguro que quieres eliminar tu clave? El asistente dejará de funcionar.'))
      return
    setBusy(true)
    try {
      setSettings(await settingsService.removeAiKey())
      setKeyMessage({ text: 'La clave se eliminó.', ok: true })
    } catch {
      setKeyMessage({ text: 'No se pudo eliminar la clave.', ok: false })
    } finally {
      setBusy(false)
    }
  }

  async function changeMode(mode: ExecutionMode) {
    setModeMessage(null)
    try {
      setSettings(await settingsService.setExecutionMode(mode))
      setModeMessage({ text: 'Modo de ejecución actualizado.', ok: true })
    } catch {
      setModeMessage({ text: 'No se pudo guardar; se conserva el modo anterior.', ok: false })
    }
  }

  if (loadFailed) {
    return (
      <p className="form-error" role="alert">
        No se pudo cargar la configuración.
      </p>
    )
  }
  if (settings === null) {
    return <p className="page-loading">Cargando…</p>
  }

  return (
    <>
      <h1>Configuración</h1>

      <section className="panel settings-section">
        <h2>Modelo de IA (Claude)</h2>
        <p className="muted">
          El asistente usa el modelo {settings.ai_model} de Anthropic con tu propia clave de acceso
          a la API. La clave se guarda cifrada y el uso se factura en tu cuenta de Anthropic.
        </p>
        <p>
          {settings.ai_key_configured ? (
            <>
              <span className="badge badge-ok">Clave configurada</span> termina en{' '}
              <code>…{settings.ai_key_last4}</code>
            </>
          ) : (
            <span className="badge badge-off">Sin clave</span>
          )}
        </p>

        <form className="toolbar" onSubmit={saveKey}>
          <label>
            {settings.ai_key_configured ? 'Reemplazar clave' : 'Clave de la API de Anthropic'}
            <input
              type="password"
              autoComplete="off"
              placeholder="sk-ant-…"
              required
              minLength={20}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
            />
          </label>
          <button type="submit" disabled={busy}>
            {busy ? 'Verificando…' : 'Guardar clave'}
          </button>
          {settings.ai_key_configured && (
            <button
              type="button"
              className="button-secondary"
              disabled={busy}
              onClick={() => void removeKey()}
            >
              Eliminar clave
            </button>
          )}
        </form>
        {keyMessage && (
          <p
            className={keyMessage.ok ? 'form-success' : 'form-error'}
            role={keyMessage.ok ? 'status' : 'alert'}
          >
            {keyMessage.text}
          </p>
        )}
      </section>

      <section className="panel settings-section">
        <h2>Modo de ejecución</h2>
        <p className="muted">Define qué hace el asistente con las acciones que propone.</p>
        {MODES.map((mode) => (
          <label key={mode.id} className="radio-option">
            <input
              type="radio"
              name="execution-mode"
              checked={settings.execution_mode === mode.id}
              onChange={() => void changeMode(mode.id)}
            />
            <span>
              <strong>{mode.label}</strong>
              <span className="muted">{mode.description}</span>
            </span>
          </label>
        ))}
        {modeMessage && (
          <p
            className={modeMessage.ok ? 'form-success' : 'form-error'}
            role={modeMessage.ok ? 'status' : 'alert'}
          >
            {modeMessage.text}
          </p>
        )}
      </section>
    </>
  )
}
