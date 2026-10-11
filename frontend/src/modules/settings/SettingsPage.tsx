import { useEffect, useState } from 'react'

import { ApiError } from '../../services/apiClient'
import { settingsService } from '../../services/settingsService'
import type { ExecutionMode, Settings } from '../../types/settings'
import ProviderKeyCard from './ProviderKeyCard'

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

/** Guidance shown under the model selector, by model id. */
const MODEL_HINTS: Record<string, string> = {
  'claude-fable-5-1': 'El más capaz y el de mayor costo; sus respuestas pueden tardar más.',
  'claude-opus-5-5': 'Alta capacidad para interpretar instrucciones complejas.',
  'claude-sonnet-5-5': 'Equilibrio entre rapidez, capacidad y costo para el uso diario.',
  'claude-haiku-5-5': 'El más rápido y económico de Claude; adecuado para instrucciones simples.',
  'gemini-3.1-pro-preview':
    'El más capaz de Gemini. Está en vista previa: Google puede cambiarlo o retirarlo.',
  'gemini-3.8-flash': 'El modelo Flash más reciente de Gemini, rápido y de uso general.',
  'gemini-3.5-flash-lite':
    'El más rápido y económico de Gemini; adecuado para instrucciones simples.',
}

type Message = { text: string; ok: boolean }

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings | null>(null)
  const [modeMessage, setModeMessage] = useState<Message | null>(null)
  const [modelMessage, setModelMessage] = useState<Message | null>(null)
  const [changingModel, setChangingModel] = useState(false)
  const [loadFailed, setLoadFailed] = useState(false)

  useEffect(() => {
    settingsService
      .get()
      .then(setSettings)
      .catch(() => setLoadFailed(true))
  }, [])

  async function changeModel(model: string) {
    setChangingModel(true)
    setModelMessage(null)
    try {
      setSettings(await settingsService.setAiModel(model))
      setModelMessage({ text: 'Modelo actualizado.', ok: true })
    } catch (err) {
      const status = err instanceof ApiError ? err.status : 0
      setModelMessage({
        text:
          status === 422
            ? 'Tu clave no tiene acceso a ese modelo; se conserva el modelo anterior.'
            : status === 503
              ? 'No se pudo verificar el modelo en este momento. Inténtalo más tarde.'
              : 'No se pudo cambiar el modelo.',
        ok: false,
      })
    } finally {
      setChangingModel(false)
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

  const selectedProvider = settings.providers.find((item) => item.id === settings.ai_provider)

  return (
    <>
      <h1>Configuración</h1>

      <section className="panel settings-section">
        <h2>Modelo de IA</h2>
        <p className="muted">
          El asistente puede usar modelos de Claude (Anthropic) o de Gemini (Google), con tu propia
          clave de acceso a la API de cada proveedor. Las claves se guardan cifradas y el uso se
          factura en tu cuenta del proveedor, según el modelo que elijas.
        </p>

        <div className="toolbar">
          <label>
            Modelo del asistente
            <select
              value={settings.ai_model}
              disabled={changingModel}
              onChange={(e) => void changeModel(e.target.value)}
            >
              {settings.providers.map((provider) => (
                <optgroup
                  key={provider.id}
                  label={provider.key_configured ? provider.name : `${provider.name} (sin clave)`}
                >
                  {settings.available_models
                    .filter((model) => model.provider === provider.id)
                    .map((model) => (
                      <option key={model.id} value={model.id}>
                        {model.name}
                      </option>
                    ))}
                </optgroup>
              ))}
            </select>
          </label>
        </div>
        {MODEL_HINTS[settings.ai_model] && (
          <p className="form-hint">{MODEL_HINTS[settings.ai_model]}</p>
        )}
        {!settings.assistant_ready && selectedProvider && (
          <p className="form-error" role="alert">
            El modelo elegido es de {selectedProvider.name} y aún no has guardado esa clave: el
            asistente no funcionará hasta que la agregues o elijas un modelo de otro proveedor.
          </p>
        )}
        {modelMessage && (
          <p
            className={modelMessage.ok ? 'form-success' : 'form-error'}
            role={modelMessage.ok ? 'status' : 'alert'}
          >
            {modelMessage.text}
          </p>
        )}

        {settings.providers.map((provider) => (
          <ProviderKeyCard
            key={provider.id}
            provider={provider}
            selectedModel={settings.ai_model}
            onChange={setSettings}
          />
        ))}
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
