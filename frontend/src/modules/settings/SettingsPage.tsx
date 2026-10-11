import { NavLink, Outlet } from 'react-router-dom'

const SECTIONS = [
  { to: '/settings/ai', label: 'Inteligencia artificial', hint: 'Modelo, claves e instrucciones' },
  { to: '/settings/account', label: 'Cuenta', hint: 'Tus datos y tu sesión' },
]

export default function SettingsPage() {
  return (
    <>
      <h1>Configuración</h1>
      <div className="settings-layout">
        <nav className="settings-nav" aria-label="Secciones de configuración">
          {SECTIONS.map((section) => (
            <NavLink key={section.to} to={section.to}>
              <span>{section.label}</span>
              <span className="muted">{section.hint}</span>
            </NavLink>
          ))}
        </nav>
        <div className="settings-content">
          <Outlet />
        </div>
      </div>
    </>
  )
}
