import { createContext } from 'react'

import type { LoginPayload, RegisterPayload } from '../../services/authService'
import type { User } from '../../types/user'

export interface AuthContextValue {
  user: User | null
  /** True while the initial session check is in progress. */
  loading: boolean
  login: (payload: LoginPayload) => Promise<void>
  register: (payload: RegisterPayload) => Promise<void>
  logout: () => Promise<void>
}

export const AuthContext = createContext<AuthContextValue | null>(null)
