import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import Icon, { type IconName } from '../../components/Icon'
import { unreadLabel, useLayoutContext } from '../../layouts/layoutContext'
import { calendarService } from '../../services/calendarService'
import { tasksService } from '../../services/tasksService'
import type { CalendarEvent } from '../../types/calendar'
import type { Task } from '../../types/task'
import { useAuth } from '../auth/useAuth'

const dateFormat = new Intl.DateTimeFormat('es-CL', {
  weekday: 'long',
  day: 'numeric',
  month: 'long',
})
const timeFormat = new Intl.DateTimeFormat('es-CL', {
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
})

interface AgendaItem {
  key: string
  /** Null for all-day events. */
  time: Date | null
  title: string
  source: string
  icon: IconName
  link: string | null
  tag: 'Atrasada' | 'Hoy' | null
}

function greeting(hour: number): string {
  if (hour < 12) return 'Buen día'
  if (hour < 20) return 'Buenas tardes'
  return 'Buenas noches'
}

function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`
}

function eventStart(event: CalendarEvent): Date {
  // A bare ISO date would be parsed as UTC and could shift to the previous local day.
  return new Date(event.all_day ? `${event.start}T00:00:00` : event.start)
}

/** Pending tasks that are overdue or due before the end of today. */
function urgentTasks(tasks: Task[], endOfDay: Date): Task[] {
  return tasks
    .filter((task) => task.status === 'pending' && task.due_at !== null)
    .filter((task) => new Date(task.due_at!) < endOfDay)
    .sort((a, b) => new Date(a.due_at!).getTime() - new Date(b.due_at!).getTime())
}

function buildAgenda(events: CalendarEvent[], urgent: Task[], startOfDay: Date): AgendaItem[] {
  const items: AgendaItem[] = events.map((event) => ({
    key: `event-${event.account_id}-${event.id}`,
    time: event.all_day ? null : eventStart(event),
    title: event.title,
    source: event.account_email,
    icon: 'calendar',
    link: event.html_link,
    tag: null,
  }))
  for (const task of urgent) {
    const due = new Date(task.due_at!)
    items.push({
      key: `task-${task.id}`,
      time: due,
      title: task.title,
      source: 'Tarea',
      icon: 'tasks',
      link: null,
      tag: due < startOfDay ? 'Atrasada' : 'Hoy',
    })
  }
  // Overdue tasks first, then all-day events, then by time.
  const rank = (item: AgendaItem) =>
    item.tag === 'Atrasada' ? -2 : item.time === null ? -1 : item.time.getTime()
  return items.sort((a, b) => rank(a) - rank(b))
}

export default function TodayPage() {
  const { user } = useAuth()
  const { unread } = useLayoutContext()
  const [events, setEvents] = useState<CalendarEvent[] | null>(null)
  const [tasks, setTasks] = useState<Task[] | null>(null)
  const [hasAccounts, setHasAccounts] = useState(true)
  const [now] = useState(() => new Date())

  const startOfDay = new Date(now)
  startOfDay.setHours(0, 0, 0, 0)
  const endOfDay = new Date(startOfDay)
  endOfDay.setDate(endOfDay.getDate() + 1)
  const dayStart = startOfDay.getTime()

  useEffect(() => {
    let cancelled = false
    const from = new Date(dayStart)
    const to = new Date(dayStart)
    to.setDate(to.getDate() + 1)
    calendarService
      .listEvents(from, to)
      .then((result) => {
        if (cancelled) return
        // Multi-day events that started earlier are returned too; keep those of today.
        setEvents(result.events.filter((event) => eventStart(event) >= from))
        setHasAccounts(result.accounts.length > 0)
      })
      .catch(() => {
        if (!cancelled) setEvents([])
      })
    tasksService
      .list()
      .then((result) => {
        if (!cancelled) setTasks(result)
      })
      .catch(() => {
        if (!cancelled) setTasks([])
      })
    return () => {
      cancelled = true
    }
  }, [dayStart])

  const urgent = tasks ? urgentTasks(tasks, endOfDay) : []
  const agenda = buildAgenda(events ?? [], urgent, startOfDay)
  const nextItem = agenda.find((item) => item.time !== null && item.time >= now) ?? null
  const upcomingEvents = (events ?? []).filter(
    (event) => !event.all_day && eventStart(event) >= now,
  )
  const unreadCount = unread?.messages.length ?? null
  const latestUnread = unread?.messages[0] ?? null
  const loading = events === null || tasks === null
  const firstName = user?.full_name.trim().split(/\s+/)[0] ?? ''

  return (
    <div className="today">
      <header className="today-header">
        <p className="mono-label">{dateFormat.format(now)}</p>
        <h1 className="display">
          {greeting(now.getHours())}, {firstName}.
        </h1>
      </header>

      <div className="stat-grid">
        <Link to="/agenda" className="stat-card">
          <span className="stat-value">{events?.length ?? '–'}</span>
          <span className="mono-label">{events?.length === 1 ? 'Reunión' : 'Reuniones'}</span>
        </Link>
        <Link to="/tasks" className="stat-card stat-warm">
          <span className="stat-value">{tasks ? urgent.length : '–'}</span>
          <span className="mono-label">
            {urgent.length === 1 ? 'Tarea urgente' : 'Tareas urgentes'}
          </span>
        </Link>
        <Link to="/inbox" className="stat-card">
          <span className="stat-value">
            {unreadCount === null ? '–' : unreadLabel(unreadCount)}
          </span>
          <span className="mono-label">
            {unreadCount === 1 ? 'Correo sin leer' : 'Correos sin leer'}
          </span>
        </Link>
      </div>

      <div className="today-grid">
        <section className="summary-card">
          <div className="summary-head">
            <span className="summary-mark">
              <Icon name="today" size={16} />
            </span>
            <h2>Resumen del día</h2>
            <span className="mono-label">{timeFormat.format(now)}</span>
          </div>

          {loading ? (
            <p className="summary-text">Preparando tu resumen…</p>
          ) : (
            <p className="summary-text">
              {events.length === 0 ? (
                'Hoy no tienes reuniones en tu agenda. '
              ) : upcomingEvents.length === 0 ? (
                `Hoy tenías ${plural(events.length, 'reunión', 'reuniones')} y ya no te queda ninguna por delante. `
              ) : (
                <>
                  Hoy tienes {plural(events.length, 'reunión', 'reuniones')}; la próxima es a las{' '}
                  <strong>{timeFormat.format(eventStart(upcomingEvents[0]))}</strong>:{' '}
                  {upcomingEvents[0].title}.{' '}
                </>
              )}
              {urgent.length === 0 ? (
                'No tienes tareas que venzan hoy. '
              ) : (
                <>
                  Tienes <strong>{plural(urgent.length, 'tarea', 'tareas')}</strong> para hoy o
                  atrasadas; la primera es «{urgent[0].title}».{' '}
                </>
              )}
              {latestUnread !== null && unreadCount !== null && (
                <>
                  Hay {plural(unreadCount, 'correo', 'correos')} sin leer; el más reciente es de{' '}
                  {latestUnread.sender_name}: «{latestUnread.subject}».
                </>
              )}
            </p>
          )}

          <div className="summary-actions">
            <Link to="/chat" className="button">
              Preguntar al asistente
            </Link>
            <Link to="/tasks" className="button-quiet">
              Ver tareas
            </Link>
          </div>
        </section>

        <section className="today-agenda">
          <h2>Hoy · agenda unificada</h2>
          {!loading && agenda.length === 0 && (
            <p className="empty-card">
              {hasAccounts ? (
                'No hay reuniones ni tareas para hoy.'
              ) : (
                <>
                  No hay tareas para hoy. <Link to="/connections">Conecta tu cuenta de Google</Link>{' '}
                  para ver tus reuniones.
                </>
              )}
            </p>
          )}
          <ul className="agenda-cards">
            {agenda.map((item) => (
              <li
                key={item.key}
                className={item === nextItem ? 'agenda-card agenda-card-next' : 'agenda-card'}
              >
                <span className="agenda-card-time">
                  {item.time === null
                    ? 'Día'
                    : item.tag === 'Atrasada'
                      ? '—'
                      : timeFormat.format(item.time)}
                </span>
                <span className={`agenda-card-icon agenda-card-icon-${item.icon}`}>
                  <Icon name={item.icon} size={16} />
                </span>
                <span className="agenda-card-info">
                  {item.link ? (
                    <a href={item.link} target="_blank" rel="noreferrer">
                      {item.title}
                    </a>
                  ) : (
                    <span>{item.title}</span>
                  )}
                  <span className="mono-label">{item.source}</span>
                </span>
                {item.tag && (
                  <span className={item.tag === 'Atrasada' ? 'chip chip-alert' : 'chip'}>
                    {item.tag}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  )
}
