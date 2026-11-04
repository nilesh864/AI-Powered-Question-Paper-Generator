import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { apiRequest } from '../services/api.js'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    localStorage.removeItem('qps-user')
    localStorage.removeItem('qps-current-paper')
    localStorage.removeItem('qps-user-id')
    let active = true
    const token = localStorage.getItem('qps-token')
    if (!token) {
      setLoading(false)
      return () => { active = false }
    }
    apiRequest('/auth/me')
      .then((currentUser) => { if (active) { localStorage.setItem('qps-user-id', currentUser.id); setUser(currentUser) } })
      .catch(() => { if (active) { localStorage.removeItem('qps-token'); localStorage.removeItem('qps-user-id'); setUser(null) } })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  useEffect(() => {
    const handleUnauthorized = () => {
      localStorage.removeItem('qps-token')
      localStorage.removeItem('qps-user-id')
      setUser(null)
    }
    window.addEventListener('qps:unauthorized', handleUnauthorized)
    return () => window.removeEventListener('qps:unauthorized', handleUnauthorized)
  }, [])

  async function authenticate(mode, values) {
    const response = await apiRequest(`/auth/${mode}`, { method: 'POST', body: JSON.stringify(values) })
    localStorage.setItem('qps-token', response.access_token)
    localStorage.setItem('qps-user-id', response.user.id)
    setUser(response.user)
    setLoading(false)
    return response.user
  }

  function signOut() {
    localStorage.removeItem('qps-token')
    localStorage.removeItem('qps-user-id')
    localStorage.removeItem('qps-current-paper')
    setUser(null)
  }

  const value = useMemo(() => ({ user, loading, authenticate, signOut }), [user, loading])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  return useContext(AuthContext)
}