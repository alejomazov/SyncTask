import { Navigate, Outlet, useLocation } from 'react-router-dom'

import { useAuth } from '../modules/auth/useAuth'
import type { UserRole } from '../types/user'

export default function ProtectedRoute({ role }: { role?: UserRole }) {
  const { user, loading } = useAuth()
  const location = useLocation()

  if (loading) {
    return <p className="page-loading">Cargando…</p>
  }
  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  if (role && user.role !== role) {
    return <Navigate to="/dashboard" replace />
  }
  return <Outlet />
}
