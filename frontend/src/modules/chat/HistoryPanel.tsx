import { useEffect, useState } from 'react'

import { chatService } from '../../services/chatService'
import type { Interaction } from '../../types/chat'
import { ACTION_STATUS_LABELS } from './ActionCard'
import AssistantMessage from './AssistantMessage'

const dateFormat = new Intl.DateTimeFormat('es-CL', { dateStyle: 'medium', timeStyle: 'short' })

/** Past instructions across every conversation, newest first (RF16). */
export default function HistoryPanel({ modelNames }: { modelNames: Record<string, string> }) {
  const [interactions, setInteractions] = useState<Interaction[] | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    chatService
      .listHistory()
      .then((items) => setInteractions([...items].reverse()))
      .catch(() => setFailed(true))
  }, [])

  if (failed) {
    return (
      <p className="form-error" role="alert">
        No se pudo cargar el historial.
      </p>
    )
  }
  if (interactions === null) {
    return <p className="page-loading">Cargando…</p>
  }
  if (interactions.length === 0) {
    return <p className="notice">Aún no hay interacciones registradas.</p>
  }

  return (
    <div className="chat-messages">
      <p className="muted">
        Tus instrucciones anteriores, de la más reciente a la más antigua. Selecciona una para ver
        la respuesta y las acciones realizadas.
      </p>
      {interactions.map((interaction) => (
        <details key={interaction.id} className="history-item">
          <summary>
            <span className="history-date">
              {dateFormat.format(new Date(interaction.created_at))}
            </span>
            <span className="history-instruction">{interaction.instruction}</span>
          </summary>
          <div className="history-body">
            {interaction.response ? (
              <AssistantMessage text={interaction.response} />
            ) : (
              <p className="muted">Sin respuesta registrada.</p>
            )}
            {interaction.status === 'error' && (
              <p className="form-error">No se pudo completar esta instrucción.</p>
            )}
            {interaction.actions.length > 0 && (
              <ul className="history-actions">
                {interaction.actions.map((action) => (
                  <li key={action.id}>
                    {action.summary} — <em>{ACTION_STATUS_LABELS[action.status]}</em>
                  </li>
                ))}
              </ul>
            )}
            {interaction.model && (
              <p className="form-hint">
                Modelo: {modelNames[interaction.model] ?? interaction.model}
              </p>
            )}
          </div>
        </details>
      ))}
    </div>
  )
}
