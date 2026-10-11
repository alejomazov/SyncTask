import { useEffect, useState } from 'react'

import Pagination from '../../components/Pagination'
import { adminService } from '../../services/adminService'
import type { Page } from '../../types/admin'
import type { AdminConnection } from '../../types/connections'
import { providerLabel, STATUS_LABELS } from '../connections/labels'
import { errorMessage, formatDateTime } from './format'

const PAGE_SIZE = 20

export default function ConnectionsTab() {
  const [data, setData] = useState<Page<AdminConnection> | null>(null)
  const [page, setPage] = useState(1)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    adminService
      .listConnections({ page, page_size: PAGE_SIZE })
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
  }, [page])

  if (error) {
    return (
      <p className="form-error" role="alert">
        {error}
      </p>
    )
  }
  if (data === null) {
    return <p className="page-loading">Cargando…</p>
  }

  return (
    <section>
      <p className="muted">
        Estado de las conexiones de los usuarios con Google. Las conexiones con Microsoft se
        mostrarán aquí cuando se implementen.
      </p>
      <table className="data-table">
        <thead>
          <tr>
            <th>Usuario</th>
            <th>Proveedor</th>
            <th>Cuenta conectada</th>
            <th>Estado</th>
            <th>Conectada</th>
            <th>Token vigente hasta</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((item) => (
            <tr key={item.id}>
              <td>
                {item.user_full_name}
                <br />
                <span className="muted">{item.user_email}</span>
              </td>
              <td>{providerLabel(item.provider)}</td>
              <td>{item.account_email}</td>
              <td>
                <span className={item.status === 'active' ? 'badge badge-ok' : 'badge badge-off'}>
                  {STATUS_LABELS[item.status]}
                </span>
              </td>
              <td>{formatDateTime(item.created_at)}</td>
              <td>{formatDateTime(item.token_expires_at)}</td>
            </tr>
          ))}
          {data.items.length === 0 && (
            <tr>
              <td colSpan={6} className="empty-row">
                Ningún usuario ha conectado cuentas todavía.
              </td>
            </tr>
          )}
        </tbody>
      </table>
      <Pagination page={page} pageSize={PAGE_SIZE} total={data.total} onChange={setPage} />
    </section>
  )
}
