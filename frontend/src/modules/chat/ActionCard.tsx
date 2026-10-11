import type { ActionStatus, AssistantAction } from '../../types/chat'

const STATUS_LABELS: Record<ActionStatus, string> = {
  pending: 'Pendiente de confirmación',
  executed: 'Ejecutada',
  rejected: 'Rechazada: no cumple el formato establecido',
  discarded: 'Descartada',
  failed: 'No se pudo ejecutar',
}

interface ActionCardProps {
  action: AssistantAction
  /** False while the reply is still streaming or another action is being resolved. */
  enabled: boolean
  onConfirm: () => void
  onDiscard: () => void
}

export default function ActionCard({ action, enabled, onConfirm, onDiscard }: ActionCardProps) {
  return (
    <div className={`action-card action-${action.status}`}>
      <div>
        <strong>{action.summary}</strong>
        <span className="action-status">{STATUS_LABELS[action.status]}</span>
      </div>
      {action.status === 'pending' && (
        <span className="action-buttons">
          <button type="button" disabled={!enabled} onClick={onConfirm}>
            Confirmar
          </button>
          <button
            type="button"
            className="button-secondary"
            disabled={!enabled}
            onClick={onDiscard}
          >
            Descartar
          </button>
        </span>
      )}
    </div>
  )
}
