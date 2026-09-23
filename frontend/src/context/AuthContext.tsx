import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api } from '../api/client'
import type { User } from '../types/api'

interface AuthContextValue {
  user: User | null
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)
const USER_KEY = 'lct_current_user'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const saved = localStorage.getItem(USER_KEY)
    if (saved) {
      try { setUser(JSON.parse(saved) as User) } catch { localStorage.removeItem(USER_KEY) }
    }
    setLoading(false)
  }, [])

  const value = useMemo<AuthContextValue>(() => ({
    user,
    loading,
    login: async (username, password) => {
      const response = await api.login(username, password)
      localStorage.setItem('lct_access_token', response.access_token)
      localStorage.setItem(USER_KEY, JSON.stringify(response.user))
      setUser(response.user)
    },
    logout: () => {
      localStorage.removeItem('lct_access_token')
      localStorage.removeItem(USER_KEY)
      setUser(null)
    },
  }), [user, loading])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside AuthProvider')
  return context
}
