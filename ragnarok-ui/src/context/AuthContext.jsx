import { createContext, useContext, useState, useEffect, useMemo } from 'react'
import { API_BASE_URL } from '../api/client'

const AuthContext = createContext(null)

// Custom helper function to decode JWT token payload in pure JavaScript
function decodeJwt(token) {
  try {
    const base64Url = token.split('.')[1]
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/')
    const jsonPayload = decodeURIComponent(
      window.atob(base64)
        .split('')
        .map(c => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
        .join('')
    )
    return JSON.parse(jsonPayload)
  } catch (error) {
    console.error('Failed to decode JWT token', error)
    return null
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem('ragnarok_token')
    const storedUser = localStorage.getItem('ragnarok_user')
    if (token && storedUser) {
      try {
        const payload = decodeJwt(token)
        if (payload && payload.exp && Date.now() / 1000 < payload.exp) {
          const parsed = JSON.parse(storedUser)
          if (parsed && parsed.role) {
            parsed.role = parsed.role.toUpperCase()
          }
          if (payload.role) {
            const normRole = payload.role.toUpperCase()
            parsed.role = normRole
            parsed.roleName = normRole === 'PLATFORM_ADMIN'
              ? 'Platform Admin'
              : normRole === 'TENANT_ADMIN'
              ? 'Tenant Admin'
              : 'Người dùng'
          }
          setUser(parsed)
        } else {
          // Token expired or invalid, clear session
          localStorage.removeItem('ragnarok_user')
          localStorage.removeItem('ragnarok_token')
          localStorage.removeItem('tenantId')
          setUser(null)
        }
      } catch (e) {
        localStorage.removeItem('ragnarok_user')
        localStorage.removeItem('ragnarok_token')
        localStorage.removeItem('tenantId')
        setUser(null)
      }
    } else {
      setUser(null)
    }
    setLoading(false)
  }, [])

  const login = async (username, password) => {
    try {
      if (!username || !password) {
        throw new Error('Vui lòng điền đầy đủ tên đăng nhập và mật khẩu.')
      }

      if (password.length < 6) {
        throw new Error('Mật khẩu phải dài từ 6 ký tự trở lên.')
      }

      const response = await fetch(`${API_BASE_URL}/v1/auth/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Request-ID': crypto.randomUUID()
        },
        body: JSON.stringify({ username, password })
      })

      const body = await response.json().catch(() => ({}))
      if (!response.ok) {
        if (response.status === 401 || response.status === 400) {
          throw new Error('Tên đăng nhập hoặc mật khẩu không chính xác. Vui lòng kiểm tra lại.')
        }
        
        const detailStr = typeof body.detail === 'string' ? body.detail : body.detail?.message || body.detail?.error_code
        throw new Error(detailStr || 'Đăng nhập thất bại. Vui lòng kiểm tra kết nối.')
      }

      const { access_token } = body
      const payload = decodeJwt(access_token)
      if (!payload) {
        throw new Error('Đăng nhập thất bại: Token phản hồi không hợp lệ.')
      }

      const name = payload.full_name || payload.username || username.split('@')[0]
      const initials = name.split(' ').map(p => p[0]).filter(Boolean).slice(0, 2).join('').toUpperCase() || name.substring(0, 2).toUpperCase()

      const userRole = (payload.role || '').toUpperCase()
      let roleName = 'Người dùng'
      if (userRole === 'PLATFORM_ADMIN') {
        roleName = 'Platform Admin'
      } else if (userRole === 'TENANT_ADMIN') {
        roleName = 'Tenant Admin'
      }

      const userData = {
        id: payload.sub,
        username: payload.username,
        email: payload.username.includes('@') ? payload.username : `${payload.username}@ragnarok.ai`,
        name: name.charAt(0).toUpperCase() + name.slice(1),
        initials: initials,
        role: userRole,
        roleName: roleName,
        tenantId: payload.tenant_id,
        avatarBg: getRandomGradient(payload.username)
      }

      localStorage.setItem('ragnarok_token', access_token)
      localStorage.setItem('ragnarok_user', JSON.stringify(userData))
      if (payload.tenant_id && payload.tenant_id !== 'null') {
        localStorage.setItem('tenantId', payload.tenant_id)
      } else {
        localStorage.removeItem('tenantId')
      }
      setUser(userData)
      return userData
    } catch (err) {
      console.error('Login error', err)
      throw err
    }
  }

  const logout = () => {
    localStorage.removeItem('ragnarok_user')
    localStorage.removeItem('ragnarok_token')
    localStorage.removeItem('tenantId')
    setUser(null)
  }

  const value = useMemo(() => ({ user, loading, login, logout }), [user, loading])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// Generate consistent background gradient based on username
function getRandomGradient(str) {
  const gradients = [
    'linear-gradient(135deg, #FF6B6B 0%, #FF8E53 100%)',
    'linear-gradient(135deg, #4E65FF 0%, #92EFFD 100%)',
    'linear-gradient(135deg, #11998e 0%, #38ef7d 100%)',
    'linear-gradient(135deg, #FC466B 0%, #3F5EFB 100%)',
    'linear-gradient(135deg, #7F00FF 0%, #E100FF 100%)',
    'linear-gradient(135deg, #11998e 0%, #38ef7d 100%)',
    'linear-gradient(135deg, #F093FB 0%, #F5576C 100%)',
    'linear-gradient(135deg, #30CFD0 0%, #330867 100%)'
  ]
  
  let hash = 0
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash)
  }
  const index = Math.abs(hash) % gradients.length
  return gradients[index]
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used inside AuthProvider')
  }
  return context
}
