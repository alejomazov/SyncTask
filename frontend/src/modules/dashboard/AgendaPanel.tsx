import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { calendarService } from '../../services/calendarService'
import type { CalendarEvent, CalendarEventsResponse } from '../../types/calendar'

const DAYS_AHEAD = 7

const dayFormat = new Intl.DateTimeFormat('es-CL', {
  weekday: 'long',
  day: 'numeric',
  month: 'long',
})
const timeFormat = new Intl.DateTimeFormat('es-CL', { hour: '2-digit', minute: '2-digit' })

/** Parses the start of an event in the user's local time zone. */
function startDate(event: CalendarEvent): Date {
  // A bare ISO date would be parsed as UTC and could shift to the previous local day.
  return new Date(event.all_day ? `${event.start}T00:00:00` : event.start)
}

function dayKey(date: Date): string {
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`
}

function groupByDay(events: CalendarEvent[]): { label: string; events: CalendarEvent[] }[] {
  const groups = new Map<string, { label: string; events: CalendarEvent[] }>()
  for (const event of events) {
    const date = startDate(event)
    const key = dayKey(date)
    if (!groups.has(key)) groups.set(key, { label: dayFormat.format(date), events: [] })
    groups.get(key)!.events.push(event)
  }
  return [...groups.values()]
}

function timeRange(event: CalendarEvent): string {
  if (event.all_day) return 'Todo el día'
  return `${timeFormat.format(new Date(event.start))} – ${timeFormat.format(new Date(event.end))}`
}

export default function AgendaPanel() {
  const [data, setData] = useState<CalendarEventsResponse | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let cancelled = false
    const from = new Date()
    from.setHours(0, 0, 0, 0)
    const to = new Date(from)
    to.setDate(to.getDate() + DAYS_AHEAD)

    calendarService
      .listEvents(from, to)
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

  return (
    <section className="panel">
      <h2>Agenda de los próximos {DAYS_AHEAD} días</h2>

      {failed && (
        <p className="form-error" role="alert">
          No se pudo cargar la agenda.
        </p>
      )}
      {!failed && data === null && <p className="page-loading">Cargando…</p>}

      {data !== null && data.accounts.length === 0 && (
        <p className="muted">
          Aún no tienes cuentas conectadas.{' '}
          <Link to="/connections">Conecta tu cuenta de Google</Link> para ver tu agenda.
        </p>
      )}

      {data?.accounts
        .filter((account) => account.error !== null)
        .map((account) => (
          <p key={account.account_id} className="form-error" role="alert">
            {account.error === 'needs_reauth' ? (
              <>
                La cuenta {account.account_email} requiere reconexión.{' '}
                <Link to="/connections">Reconectar</Link>
              </>
            ) : (
              <>No se pudo consultar el calendario de {account.account_email} en este momento.</>
            )}
          </p>
        ))}

      {data !== null && data.accounts.length > 0 && data.events.length === 0 && (
        <p className="muted">No hay eventos en este período.</p>
      )}

      {data !== null &&
        groupByDay(data.events).map((group) => (
          <div key={group.label} className="agenda-day">
            <h3>{group.label}</h3>
            <ul>
              {group.events.map((event) => (
                <li key={`${event.account_id}-${event.id}`}>
                  <span className="agenda-time">{timeRange(event)}</span>
                  <span className="agenda-info">
                    {event.html_link ? (
                      <a href={event.html_link} target="_blank" rel="noreferrer">
                        {event.title}
                      </a>
                    ) : (
                      event.title
                    )}
                    <span className="muted">
                      {event.location ? `${event.location} · ` : ''}
                      {event.account_email}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ))}
    </section>
  )
}
