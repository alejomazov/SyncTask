import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { ApiError } from '../../services/apiClient'
import { connectionsService } from '../../services/connectionsService'
import type { ConnectedAccount } from '../../types/connections'
import { providerLabel, STATUS_LABELS } from './labels'

const RESULT_MESSAGES: Record<string, { text: string; ok: boolean }> = {
  connected: { text: 'La cuenta de Google quedó conectada.', ok: true },
  denied: {
    text: 'No se conectó la cuenta: es necesario autorizar el acceso de lectura al calendario.',
    ok: false,
  },
  session_expired: {
    text: 'Tu sesión expiró durante la autorización. Inténtalo nuevamente.',
    ok: false,
  },
  error: { text: 'No se pudo conectar la cuenta de Google. Inténtalo nuevamente.', ok: false },
}

export default function ConnectionsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [accounts, setAccounts] = useState<ConnectedAccount[] | null>(null)
  const [message, setMessage] = useState<{ text: string; ok: boolean } | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      setAccounts(await connectionsService.list())
    } catch {
      setMessage({ text: 'No se pudieron cargar las cuentas conectadas.', ok: false })
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  // Google sends the browser back here with the outcome in the query string.
  useEffect(() => {
    const result = searchParams.get('google')
    if (result === null) return
    setMessage(RESULT_MESSAGES[result] ?? RESULT_MESSAGES.error)
    setSearchParams({}, { replace: true })
  }, [searchParams, setSearchParams])

  async function connectGoogle() {
    setBusy(true)
    setMessage(null)
    try {
      window.location.assign(await connectionsService.googleAuthorizationUrl())
    } catch (err) {
      setBusy(false)
      setMessage({
        text:
          err instanceof ApiError && err.status === 503
            ? 'La integración con Google aún no está configurada en el servidor.'
            : 'No se pudo iniciar la conexión con Google.',
        ok: false,
      })
    }
  }

  async function disconnect(account: ConnectedAccount) {
    const confirmed = window.confirm(
      `¿Seguro que quieres desconectar ${account.account_email}? SyncTask dejará de tener acceso a esa cuenta.`,
    )
    if (!confirmed) return

    setBusy(true)
    try {
      await connectionsService.disconnect(account.id)
      setMessage({ text: `Se desconectó ${account.account_email}.`, ok: true })
      await load()
    } catch {
      setMessage({ text: 'No se pudo desconectar la cuenta.', ok: false })
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <h1>Cuentas conectadas</h1>
      <p className="muted">
        Conecta tus cuentas para ver tu agenda en el panel. SyncTask solo solicita permiso de
        lectura del calendario y nunca conoce tu contraseña.
      </p>

      <div className="toolbar">
        <button type="button" disabled={busy} onClick={() => void connectGoogle()}>
          Conectar cuenta de Google
        </button>
      </div>

      {message && (
        <p
          className={message.ok ? 'form-success' : 'form-error'}
          role={message.ok ? 'status' : 'alert'}
        >
          {message.text}
        </p>
      )}

      {accounts === null ? (
        <p className="page-loading">Cargando…</p>
      ) : accounts.length === 0 ? (
        <p className="notice">Aún no tienes cuentas conectadas.</p>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>Proveedor</th>
              <th>Cuenta</th>
              <th>Estado</th>
              <th aria-label="Acciones" />
            </tr>
          </thead>
          <tbody>
            {accounts.map((account) => (
              <tr key={account.id}>
                <td>{providerLabel(account.provider)}</td>
                <td>{account.account_email}</td>
                <td>
                  <span
                    className={account.status === 'active' ? 'badge badge-ok' : 'badge badge-off'}
                  >
                    {STATUS_LABELS[account.status]}
                  </span>
                </td>
                <td className="cell-actions">
                  {account.status === 'needs_reauth' && (
                    <button type="button" disabled={busy} onClick={() => void connectGoogle()}>
                      Reconectar
                    </button>
                  )}{' '}
                  <button
                    type="button"
                    className="button-secondary"
                    disabled={busy}
                    onClick={() => void disconnect(account)}
                  >
                    Desconectar
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  )
}
