import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'

import Icon, { type IconName } from '../components/Icon'
import { useAuth } from '../modules/auth/useAuth'
import { connectionsService } from '../services/connectionsService'
import { mailService } from '../services/mailService'
import type { MailMessagesResponse } from '../types/mail'
import { UNREAD_LIMIT, unreadLabel, type LayoutContext } from './layoutContext'

const NAV: { to: string; label: string; icon: IconName }[] = [
  { to: '/dashboard', label: 'Hoy', icon: 'today' },
  { to: '/agenda', label: 'Agenda', icon: 'calendar' },
  { to: '/inbox', label: 'Bandeja', icon: 'mail' },
  { to: '/tasks', label: 'Tareas', icon: 'tasks' },
  { to: '/chat', label: 'Asistente', icon: 'chat' },
  { to: '/connections', label: 'Conexiones', icon: 'link' },
  { to: '/settings', label: 'Configuración', icon: 'settings' },
]

const ADMIN_ITEM = { to: '/admin', label: 'Administración', icon: 'shield' as IconName }

function initials(name: string): string {
  const words = name.trim().split(/\s+/)
  return ((words[0]?.[0] ?? '') + (words[1]?.[0] ?? '')).toUpperCase() || '?'
}

export default function AppLayout() {
  const { user, logout } = useAuth()
  const [unread, setUnread] = useState<MailMessagesResponse | null>(null)
  const [accountCount, setAccountCount] = useState<number | null>(null)

  useEffect(() => {
    let cancelled = false
    mailService
      .listMessages(UNREAD_LIMIT, true)
      .then((result) => {
        if (!cancelled) setUnread(result)
      })
      .catch(() => undefined)
    connectionsService
      .list()
      .then((accounts) => {
        if (!cancelled) setAccountCount(accounts.length)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [])

  const unreadCount = unread?.messages.length ?? 0
  const items = user?.role === 'admin' ? [...NAV, ADMIN_ITEM] : NAV

  return (
    <div className="app-layout">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">S</span>
          <span className="brand-name">SyncTask</span>
        </div>

        <nav className="sidebar-nav" aria-label="Principal">
          {items.map((item) => (
            <NavLink key={item.to} to={item.to}>
              <Icon name={item.icon} />
              <span>{item.label}</span>
              {item.to === '/inbox' && unreadCount > 0 && (
                <span className="nav-count" aria-label={`${unreadLabel(unreadCount)} sin leer`}>
                  {unreadLabel(unreadCount)}
                </span>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-user">
          <span className="avatar">{initials(user?.full_name ?? '')}</span>
          <span className="sidebar-user-info">
            <span className="sidebar-user-name">{user?.full_name}</span>
            <span className="mono-label">
              {accountCount === null
                ? user?.email
                : `${accountCount} ${accountCount === 1 ? 'cuenta' : 'cuentas'}`}
            </span>
          </span>
          <button
            type="button"
            className="icon-button"
            aria-label="Cerrar sesión"
            title="Cerrar sesión"
            onClick={() => void logout()}
          >
            <Icon name="logout" size={18} />
          </button>
        </div>
      </aside>

      <main className="app-content">
        <Outlet context={{ unread } satisfies LayoutContext} />
      </main>
    </div>
  )
}
