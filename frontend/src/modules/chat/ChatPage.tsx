import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { Link } from 'react-router-dom'

import { chatService } from '../../services/chatService'
import { settingsService } from '../../services/settingsService'
import type { AssistantAction, ChatErrorCode, ChatEvent, Interaction } from '../../types/chat'
import type { Settings } from '../../types/settings'
import ActionCard from './ActionCard'
import HistoryPanel from './HistoryPanel'

/** One instruction and its reply, either loaded from the history or still streaming. */
interface Turn {
  key: string
  interactionId: string | null
  instruction: string
  response: string
  actions: AssistantAction[]
  error: string | null
}

const ERROR_MESSAGES: Record<ChatErrorCode, string> = {
  invalid_key: 'El proveedor del modelo rechazó tu clave. Revísala en Configuración.',
  key_without_access: 'Tu clave no tiene acceso al modelo. Revísala en Configuración.',
  rate_limited:
    'Se alcanzó el límite de uso de tu cuenta con el proveedor del modelo. Inténtalo en unos minutos.',
  provider_rejected:
    'El proveedor del modelo no aceptó la solicitud. Revisa el estado y el saldo de tu cuenta.',
  provider_unavailable: 'El servicio del modelo no está disponible en este momento.',
}

const STATUS_MESSAGES: Record<string, string> = {
  list_tasks: 'Consultando tus tareas…',
  get_calendar_events: 'Consultando tu agenda…',
  list_emails: 'Consultando tus correos…',
  get_email: 'Leyendo el correo…',
}

function toTurn(interaction: Interaction): Turn {
  return {
    key: interaction.id,
    interactionId: interaction.id,
    instruction: interaction.instruction,
    response: interaction.response,
    actions: interaction.actions,
    error: interaction.status === 'error' ? 'No se pudo completar esta instrucción.' : null,
  }
}

export default function ChatPage() {
  const [turns, setTurns] = useState<Turn[] | null>(null)
  const [settings, setSettings] = useState<Settings | null>(null)
  const [view, setView] = useState<'conversation' | 'history'>('conversation')
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [activity, setActivity] = useState<string | null>(null)
  const [resolving, setResolving] = useState(false)
  const [pageError, setPageError] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    Promise.all([settingsService.get(), chatService.listConversation()])
      .then(([loadedSettings, interactions]) => {
        setSettings(loadedSettings)
        setTurns(interactions.map(toTurn))
      })
      .catch(() => setPageError('No se pudo cargar el chat.'))
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'end' })
  }, [turns, activity, view])

  function updateTurn(key: string, change: (turn: Turn) => Turn) {
    setTurns((current) => current?.map((turn) => (turn.key === key ? change(turn) : turn)) ?? null)
  }

  async function send() {
    const message = input.trim()
    if (!message || sending) return

    const key = `live-${Date.now()}`
    setTurns((current) => [
      ...(current ?? []),
      { key, interactionId: null, instruction: message, response: '', actions: [], error: null },
    ])
    setInput('')
    setSending(true)
    setActivity('Pensando…')

    function handleEvent(event: ChatEvent) {
      switch (event.type) {
        case 'text':
          setActivity(null)
          updateTurn(key, (turn) => ({ ...turn, response: turn.response + event.delta }))
          break
        case 'status':
          setActivity(STATUS_MESSAGES[event.tool] ?? 'Trabajando…')
          break
        case 'action':
          setActivity('Pensando…')
          updateTurn(key, (turn) => ({
            ...turn,
            interactionId: event.interaction_id,
            actions: [...turn.actions, event.action],
          }))
          break
        case 'error':
          updateTurn(key, (turn) => ({ ...turn, error: ERROR_MESSAGES[event.code] }))
          break
        case 'done':
          updateTurn(key, (turn) => ({ ...turn, interactionId: event.interaction_id }))
          break
      }
    }

    try {
      await chatService.sendMessage(message, handleEvent)
    } catch {
      updateTurn(key, (turn) => ({
        ...turn,
        error: 'Se perdió la conexión con el servidor. Inténtalo nuevamente.',
      }))
    } finally {
      setSending(false)
      setActivity(null)
    }
  }

  async function resolveAction(turn: Turn, action: AssistantAction, confirm: boolean) {
    if (!turn.interactionId) return
    setResolving(true)
    try {
      const updated = confirm
        ? await chatService.confirmAction(turn.interactionId, action.id)
        : await chatService.discardAction(turn.interactionId, action.id)
      updateTurn(turn.key, (current) => ({ ...current, actions: updated.actions }))
    } catch {
      setPageError('No se pudo resolver la acción. Recarga la página e inténtalo nuevamente.')
    } finally {
      setResolving(false)
    }
  }

  async function newConversation() {
    try {
      await chatService.resetConversation()
      setTurns([])
    } catch {
      setPageError('No se pudo iniciar una nueva conversación.')
    }
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    void send()
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      void send()
    }
  }

  if (turns === null || settings === null) {
    return pageError ? (
      <p className="form-error" role="alert">
        {pageError}
      </p>
    ) : (
      <p className="page-loading">Cargando…</p>
    )
  }

  const keyConfigured = settings.assistant_ready
  const modelNames = Object.fromEntries(
    settings.available_models.map((model) => [model.id, model.name]),
  )

  return (
    <div className="chat">
      <div className="chat-header">
        <h1>Chat</h1>
        <span className="chat-model">
          Modelo: <strong>{modelNames[settings.ai_model] ?? settings.ai_model}</strong>{' '}
          <Link to="/settings">Cambiar</Link>
          {settings.custom_instructions && (
            <>
              {' · '}
              <Link to="/settings">Instrucciones personalizadas activas</Link>
            </>
          )}
        </span>
        <button
          type="button"
          className="button-secondary"
          disabled={sending || turns.length === 0}
          onClick={() => void newConversation()}
        >
          Nueva conversación
        </button>
      </div>

      <div className="tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={view === 'conversation'}
          className={view === 'conversation' ? 'tab tab-active' : 'tab'}
          onClick={() => setView('conversation')}
        >
          Conversación
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={view === 'history'}
          className={view === 'history' ? 'tab tab-active' : 'tab'}
          onClick={() => setView('history')}
        >
          Historial
        </button>
      </div>

      {!keyConfigured && (
        <p className="notice">
          Para usar el asistente necesitas guardar tu clave de acceso para el modelo elegido.{' '}
          <Link to="/settings">Ir a Configuración</Link>. El panel y las tareas siguen disponibles
          sin ella.
        </p>
      )}

      {pageError && (
        <p className="form-error" role="alert">
          {pageError}
        </p>
      )}

      {view === 'history' ? (
        <HistoryPanel modelNames={modelNames} />
      ) : (
        <>
          <div className="chat-messages" aria-live="polite">
            {turns.length === 0 && keyConfigured && (
              <p className="muted">
                Escribe una instrucción, por ejemplo: «¿Qué tengo esta semana?» o «Crea una tarea
                para enviar el informe el viernes a las 10».
              </p>
            )}
            {turns.map((turn) => (
              <div key={turn.key} className="chat-turn">
                <p className="chat-bubble chat-user">{turn.instruction}</p>
                {turn.response && <p className="chat-bubble chat-assistant">{turn.response}</p>}
                {turn.actions.map((action) => (
                  <ActionCard
                    key={action.id}
                    action={action}
                    enabled={!sending && !resolving}
                    onConfirm={() => void resolveAction(turn, action, true)}
                    onDiscard={() => void resolveAction(turn, action, false)}
                  />
                ))}
                {turn.error && (
                  <p className="form-error" role="alert">
                    {turn.error}
                  </p>
                )}
              </div>
            ))}
            {activity && <p className="chat-activity">{activity}</p>}
            <div ref={bottomRef} />
          </div>

          <form className="chat-form" onSubmit={handleSubmit}>
            <textarea
              rows={2}
              maxLength={4000}
              placeholder="Escribe una instrucción…"
              aria-label="Instrucción para el asistente"
              disabled={!keyConfigured}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
            />
            <button type="submit" disabled={!keyConfigured || sending || !input.trim()}>
              {sending ? 'Enviando…' : 'Enviar'}
            </button>
          </form>
        </>
      )}
    </div>
  )
}
