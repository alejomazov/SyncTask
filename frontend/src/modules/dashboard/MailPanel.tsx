import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { mailService } from '../../services/mailService'
import type {
  MailAccountResult,
  MailMessage,
  MailMessageDetail,
  MailMessagesResponse,
} from '../../types/mail'

const MESSAGE_LIMIT = 20

const timeFormat = new Intl.DateTimeFormat('es-CL', {
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
})
const dateFormat = new Intl.DateTimeFormat('es-CL', { day: 'numeric', month: 'short' })

/** Time for today's messages, date for older ones. */
function receivedLabel(message: MailMessage): string {
  const received = new Date(message.received_at)
  const sameDay = received.toDateString() === new Date().toDateString()
  return sameDay ? timeFormat.format(received) : dateFormat.format(received)
}

function messageKey(message: MailMessage): string {
  return `${message.account_id}-${message.id}`
}

function AccountError({ account }: { account: MailAccountResult }) {
  if (account.error === 'missing_permission') {
    return (
      <>
        La cuenta {account.account_email} no tiene permiso para leer el correo.{' '}
        <Link to="/connections">Dar permiso</Link>
      </>
    )
  }
  if (account.error === 'needs_reauth') {
    return (
      <>
        La cuenta {account.account_email} requiere reconexión.{' '}
        <Link to="/connections">Reconectar</Link>
      </>
    )
  }
  return <>No se pudo consultar el correo de {account.account_email} en este momento.</>
}

type OpenMessage = { key: string; detail: MailMessageDetail | null; failed: boolean }

export default function MailPanel() {
  const [data, setData] = useState<MailMessagesResponse | null>(null)
  const [failed, setFailed] = useState(false)
  const [open, setOpen] = useState<OpenMessage | null>(null)

  useEffect(() => {
    let cancelled = false
    mailService
      .listMessages(MESSAGE_LIMIT)
      .then((result) => {
        if (!cancelled) setData(result)
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })
    return () => {
      cancelled = true
    }
  }, [])

  async function toggle(message: MailMessage) {
    const key = messageKey(message)
    if (open?.key === key) {
      setOpen(null)
      return
    }
    setOpen({ key, detail: null, failed: false })
    try {
      const detail = await mailService.getMessage(message.account_id, message.id)
      setOpen((current) => (current?.key === key ? { key, detail, failed: false } : current))
    } catch {
      setOpen((current) => (current?.key === key ? { key, detail: null, failed: true } : current))
    }
  }

  const readable = data?.accounts.some((account) => account.error === null) ?? false

  return (
    <section className="panel">
      <h2>Correos recientes</h2>

      {failed && (
        <p className="form-error" role="alert">
          No se pudieron cargar los correos.
        </p>
      )}
      {!failed && data === null && <p className="page-loading">Cargando…</p>}

      {data !== null && data.accounts.length === 0 && (
        <p className="muted">
          Aún no tienes cuentas conectadas.{' '}
          <Link to="/connections">Conecta tu cuenta de Google</Link> para ver tus correos.
        </p>
      )}

      {data?.accounts
        .filter((account) => account.error !== null)
        .map((account) => (
          <p key={account.account_id} className="form-error" role="alert">
            <AccountError account={account} />
          </p>
        ))}

      {data !== null && readable && data.messages.length === 0 && (
        <p className="muted">No hay correos en la bandeja de entrada.</p>
      )}

      {data !== null && data.messages.length > 0 && (
        <ul className="mail-list">
          {data.messages.map((message) => {
            const key = messageKey(message)
            const isOpen = open?.key === key
            return (
              <li key={key} className={message.unread ? 'mail-unread' : undefined}>
                <button
                  type="button"
                  className="mail-row"
                  aria-expanded={isOpen}
                  onClick={() => void toggle(message)}
                >
                  <span className="mail-head">
                    <span className="mail-sender">{message.sender_name}</span>
                    <span className="mail-date">{receivedLabel(message)}</span>
                  </span>
                  <span className="mail-subject">
                    {message.unread && <span className="mail-dot" aria-label="No leído" />}
                    {message.subject}
                  </span>
                  {!isOpen && <span className="muted">{message.snippet}</span>}
                </button>
                {isOpen && (
                  <div className="mail-body">
                    {open.failed && (
                      <p className="form-error" role="alert">
                        No se pudo cargar el correo.
                      </p>
                    )}
                    {!open.failed && open.detail === null && (
                      <p className="page-loading">Cargando…</p>
                    )}
                    {open.detail !== null && (
                      <>
                        <p className="muted">
                          De {message.sender_email || message.sender_name} · para{' '}
                          {message.account_email}
                        </p>
                        <pre>{open.detail.body || '(Este correo no tiene texto.)'}</pre>
                        {open.detail.body_truncated && (
                          <p className="muted">El correo es más largo; se muestra el comienzo.</p>
                        )}
                      </>
                    )}
                    <a href={message.html_link} target="_blank" rel="noreferrer">
                      Abrir en Gmail
                    </a>
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
