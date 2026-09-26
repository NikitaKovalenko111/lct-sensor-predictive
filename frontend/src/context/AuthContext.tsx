import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api } from '../api/client'
import { ApiError } from '../api/http'
import { accessTokenStore, CURRENT_USER_KEY } from '../api/runtime'
import type { User } from '../types/api'

interface AuthContextValue {
  user: User | null
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const saved = localStorage.getItem(CURRENT_USER_KEY)
    const token = accessTokenStore.get()
    let savedUser: User | null = null
    if (saved) {
      try { savedUser = JSON.parse(saved) as User } catch { localStorage.removeItem(CURRENT_USER_KEY) }
    }
    if (!token || !savedUser) {
      accessTokenStore.clear()
      setLoading(false)
      return
    }

    let disposed = false
    void api.getCurrentUser().then((identity) => {
      if (disposed || !savedUser) return
      const verifiedUser = { ...savedUser, user_id: identity.user_id, username: identity.username, role: identity.role }
      localStorage.setItem(CURRENT_USER_KEY, JSON.stringify(verifiedUser))
      setUser(verifiedUser)
    }).catch((cause: unknown) => {
      if (disposed) return
      if (!(cause instanceof ApiError) || cause.status !== 401) setUser(savedUser)
    }).finally(() => { if (!disposed) setLoading(false) })

    return () => {
      disposed = true
    }
  }, [])

  useEffect(() => {
    const unauthorized = () => setUser(null)
    window.addEventListener('lct:unauthorized', unauthorized)
    return () => window.removeEventListener('lct:unauthorized', unauthorized)
  }, [])

  const value = useMemo<AuthContextValue>(() => ({
    user,
    loading,
    login: async (username, password) => {
      const response = await api.login(username, password)
      accessTokenStore.set(response.access_token)
      localStorage.setItem(CURRENT_USER_KEY, JSON.stringify(response.user))
      setUser(response.user)
    },
    logout: () => {
      accessTokenStore.clear()
      localStorage.removeItem(CURRENT_USER_KEY)
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
