import { NavLink, Outlet } from 'react-router-dom'

import { useAuth } from '../modules/auth/useAuth'

export default function AppLayout() {
  const { user, logout } = useAuth()

  return (
    <div className="app-layout">
      <header className="app-header">
        <span className="app-brand">SyncTask</span>
        <nav className="app-nav">
          <NavLink to="/dashboard">Panel</NavLink>
          <NavLink to="/chat">Chat</NavLink>
          <NavLink to="/connections">Cuentas conectadas</NavLink>
          <NavLink to="/settings">Configuración</NavLink>
          {user?.role === 'admin' && <NavLink to="/admin">Administración</NavLink>}
        </nav>
        <div className="app-user">
          <span>{user?.full_name}</span>
          <button type="button" className="button-secondary" onClick={() => void logout()}>
            Cerrar sesión
          </button>
        </div>
      </header>
      <main className="app-content">
        <Outlet />
      </main>
    </div>
  )
}
