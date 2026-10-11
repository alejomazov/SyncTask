import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { connectionsService } from '../../services/connectionsService'
import type { ConnectedAccount } from '../../types/connections'
import { useAuth } from '../auth/useAuth'

const dateFormat = new Intl.DateTimeFormat('es-CL', { dateStyle: 'long' })

const ROLE_LABELS = { user: 'Usuario', admin: 'Administrador' }

export default function AccountSettingsPage() {
  const { user, logout } = useAuth()
  const [accounts, setAccounts] = useState<ConnectedAccount[] | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let cancelled = false
    connectionsService
      .list()
      .then((result) => {
        if (!cancelled) setAccounts(result)
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })
    return () => {
      cancelled = true
    }
  }, [])

  if (!user) return null

  return (
    <>
      <section className="panel settings-section">
        <h2>Tus datos</h2>
        <dl className="detail-list">
          <dt>Nombre</dt>
          <dd>{user.full_name}</dd>
          <dt>Correo electrónico</dt>
          <dd>{user.email}</dd>
          <dt>Tipo de cuenta</dt>
          <dd>{ROLE_LABELS[user.role]}</dd>
          <dt>Miembro desde</dt>
          <dd>{dateFormat.format(new Date(user.created_at))}</dd>
        </dl>
      </section>

      <section className="panel settings-section">
        <h2>Cuentas conectadas</h2>
        {failed && (
          <p className="form-error" role="alert">
            No se pudieron cargar las cuentas conectadas.
          </p>
        )}
        {!failed && accounts === null && <p className="muted">Cargando…</p>}
        {accounts !== null && accounts.length === 0 && (
          <p className="muted">Aún no tienes cuentas conectadas.</p>
        )}
        {accounts !== null && accounts.length > 0 && (
          <ul className="plain-list">
            {accounts.map((account) => (
              <li key={account.id}>
                {account.account_email}{' '}
                <span
                  className={account.status === 'active' ? 'badge badge-ok' : 'badge badge-off'}
                >
                  {account.status === 'active' ? 'Activa' : 'Requiere reconexión'}
                </span>
              </li>
            ))}
          </ul>
        )}
        <p>
          <Link to="/connections">Administrar conexiones</Link>
        </p>
      </section>

      <section className="panel settings-section">
        <h2>Sesión</h2>
        <p className="muted">Cierra tu sesión en este navegador.</p>
        <button type="button" className="button-secondary" onClick={() => void logout()}>
          Cerrar sesión
        </button>
      </section>
    </>
  )
}
