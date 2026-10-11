import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'

import { setUnauthorizedHandler } from '../../services/apiClient'
import { authService, type LoginPayload, type RegisterPayload } from '../../services/authService'
import type { User } from '../../types/user'
import { AuthContext, type AuthContextValue } from './authContext'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null))
    authService
      .me()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false))
    return () => setUnauthorizedHandler(null)
  }, [])

  const login = useCallback(async (payload: LoginPayload) => {
    setUser(await authService.login(payload))
  }, [])

  const register = useCallback(async (payload: RegisterPayload) => {
    setUser(await authService.register(payload))
  }, [])

  const logout = useCallback(async () => {
    await authService.logout()
    setUser(null)
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({ user, loading, login, register, logout }),
    [user, loading, login, register, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
