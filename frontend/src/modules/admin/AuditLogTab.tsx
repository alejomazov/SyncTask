import { useEffect, useState, type FormEvent } from 'react'

import Pagination from '../../components/Pagination'
import { adminService } from '../../services/adminService'
import type { AuditLog, Page } from '../../types/admin'
import { errorMessage, formatDateTime } from './format'

const PAGE_SIZE = 20

const ACTION_LABELS: Record<string, string> = {
  'auth.register': 'Registro de cuenta',
  'auth.login': 'Inicio de sesión',
  'auth.login_failed': 'Inicio de sesión fallido',
  'auth.logout': 'Cierre de sesión',
  'admin.user_created': 'Cuenta creada por administrador',
  'admin.user_enabled': 'Cuenta habilitada',
  'admin.user_disabled': 'Cuenta deshabilitada',
  'connection.connected': 'Cuenta externa conectada',
  'connection.failed': 'Conexión de cuenta fallida',
  'connection.disconnected': 'Cuenta externa desconectada',
  'task.created': 'Tarea creada',
  'task.updated': 'Tarea editada',
  'task.completed': 'Tarea completada',
  'task.reopened': 'Tarea reabierta',
  'task.deleted': 'Tarea eliminada',
  'ai.key_saved': 'Clave de IA guardada',
  'ai.key_removed': 'Clave de IA eliminada',
  'ai.action_proposed': 'Acción propuesta por el asistente',
  'ai.action_rejected': 'Acción del asistente rechazada',
  'ai.action_discarded': 'Acción del asistente descartada',
  'settings.updated': 'Configuración actualizada',
}

const REASON_LABELS: Record<string, string> = {
  invalid_credentials: 'credenciales inválidas',
  account_disabled: 'cuenta deshabilitada',
  invalid_state: 'solicitud no válida',
  access_denied: 'el usuario no autorizó',
  permission_not_granted: 'permiso de calendario no concedido',
  provider_error: 'error del proveedor',
}

interface Filters {
  action: string
  actorEmail: string
  dateFrom: string
  dateTo: string
}

const EMPTY_FILTERS: Filters = { action: '', actorEmail: '', dateFrom: '', dateTo: '' }

function describeDetail(log: AuditLog): string {
  const parts: string[] = []
  if (typeof log.detail.email === 'string') parts.push(log.detail.email)
  if (typeof log.detail.account_email === 'string') parts.push(log.detail.account_email)
  if (typeof log.detail.title === 'string') parts.push(log.detail.title)
  if (typeof log.detail.summary === 'string') parts.push(log.detail.summary)
  if (log.detail.via === 'assistant') parts.push('vía asistente')
  if (log.detail.provider === 'anthropic') parts.push('Claude')
  if (log.detail.provider === 'gemini') parts.push('Gemini')
  if (typeof log.detail.ai_model === 'string') parts.push(`modelo ${log.detail.ai_model}`)
  if (log.detail.execution_mode === 'confirm') parts.push('modo confirmar')
  if (log.detail.execution_mode === 'automatic') parts.push('modo automático')
  if (typeof log.detail.reason === 'string') {
    parts.push(REASON_LABELS[log.detail.reason] ?? log.detail.reason)
  }
  return parts.join(' · ') || '—'
}

/** Converts a date input value (local day) to the ISO instant at its start or end. */
function dayBoundary(value: string, endOfDay: boolean): string | undefined {
  if (!value) return undefined
  return new Date(`${value}T${endOfDay ? '23:59:59.999' : '00:00:00'}`).toISOString()
}

export default function AuditLogTab() {
  const [data, setData] = useState<Page<AuditLog> | null>(null)
  const [draft, setDraft] = useState<Filters>(EMPTY_FILTERS)
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS)
  const [page, setPage] = useState(1)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    adminService
      .listAuditLogs({
        action: filters.action,
        actor_email: filters.actorEmail,
        date_from: dayBoundary(filters.dateFrom, false),
        date_to: dayBoundary(filters.dateTo, true),
        page,
        page_size: PAGE_SIZE,
      })
      .then((result) => {
        if (cancelled) return
        setData(result)
        setError(null)
      })
      .catch((err) => {
        if (!cancelled) setError(errorMessage(err))
      })
    return () => {
      cancelled = true
    }
  }, [filters, page])

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setPage(1)
    setFilters(draft)
  }

  function handleClear() {
    setDraft(EMPTY_FILTERS)
    setPage(1)
    setFilters(EMPTY_FILTERS)
  }

  return (
    <section>
      <form className="toolbar" onSubmit={handleSubmit}>
        <label>
          Acción
          <select
            value={draft.action}
            onChange={(e) => setDraft({ ...draft, action: e.target.value })}
          >
            <option value="">Todas</option>
            {Object.entries(ACTION_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Usuario
          <input
            type="search"
            placeholder="Correo"
            value={draft.actorEmail}
            onChange={(e) => setDraft({ ...draft, actorEmail: e.target.value })}
          />
        </label>
        <label>
          Desde
          <input
            type="date"
            value={draft.dateFrom}
            onChange={(e) => setDraft({ ...draft, dateFrom: e.target.value })}
          />
        </label>
        <label>
          Hasta
          <input
            type="date"
            value={draft.dateTo}
            onChange={(e) => setDraft({ ...draft, dateTo: e.target.value })}
          />
        </label>
        <button type="submit">Filtrar</button>
        <button type="button" className="button-secondary" onClick={handleClear}>
          Limpiar
        </button>
      </form>

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}

      {data === null ? (
        !error && <p className="page-loading">Cargando…</p>
      ) : (
        <>
          <table className="data-table">
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Usuario</th>
                <th>Acción</th>
                <th>Detalle</th>
                <th>IP</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((log) => (
                <tr key={log.id}>
                  <td>{formatDateTime(log.created_at)}</td>
                  <td>{log.actor_email ?? '—'}</td>
                  <td>{ACTION_LABELS[log.action] ?? log.action}</td>
                  <td>{describeDetail(log)}</td>
                  <td>{log.ip_address ?? '—'}</td>
                </tr>
              ))}
              {data.items.length === 0 && (
                <tr>
                  <td colSpan={5} className="empty-row">
                    No hay registros para los filtros seleccionados.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={data.total} onChange={setPage} />
        </>
      )}
    </section>
  )
}
