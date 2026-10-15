import { createContext } from 'react'
import type { AuthTokens, User } from '../api/types'

export interface AuthContextType {
  user: User | null
  loading: boolean
  isAuthenticated: boolean
  login: (tokens: AuthTokens) => void
  logout: () => Promise<void>
  refreshProfile: () => Promise<void>
}

export const AuthContext = createContext<AuthContextType | undefined>(undefined)

