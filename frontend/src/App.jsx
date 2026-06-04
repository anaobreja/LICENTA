import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { useState, useEffect } from 'react'

// Pages
import Login from './pages/Login'
import Register from './pages/Register'
import Dashboard from './pages/Dashboard'
import Documents from './pages/Documents'
import Notifications from './pages/Notifications'
import Credentials from './pages/Credentials'
import PresentIdentity from './pages/PresentIdentity'
import VerifyPresentation from './pages/VerifyPresentation'
import Profile from './pages/Profile'
import UniversityAgentDashboard from './pages/UniversityAgentDashboard'
import Settings from './pages/Settings'

// Components
import ProtectedRoute from './components/ProtectedRoute'
import Navigation from './components/Navigation'

// Services
import { checkAuth } from './services/api'

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'dark')

  useEffect(() => {
    const root = document.documentElement
    root.classList.toggle('dark', theme === 'dark')
    root.style.colorScheme = theme === 'dark' ? 'dark' : 'light'
    localStorage.setItem('theme', theme)
  }, [theme])

  useEffect(() => {
    // Check if user is already authenticated
    const checkAuthStatus = async () => {
      try {
        const userData = await checkAuth()
        if (userData) {
          setUser(userData)
          setIsAuthenticated(true)
        }
      } catch (error) {
        console.log('Not authenticated')
      } finally {
        setLoading(false)
      }
    }

    checkAuthStatus()
  }, [])

  const handleLogin = (userData) => {
    setUser(userData)
    setIsAuthenticated(true)
  }

  const handleLogout = () => {
    setUser(null)
    setIsAuthenticated(false)
    localStorage.removeItem('access_token')
  }

  const handleThemeChange = (nextTheme) => {
    setTheme(nextTheme)
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-50 transition-colors duration-300">
        <div className="text-xl font-semibold">Loading...</div>
      </div>
    )
  }

  return (
    <Router>
      <div className="min-h-screen bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-50 transition-colors duration-300">
        {isAuthenticated && (
          <Navigation
            user={user}
            onLogout={handleLogout}
          />
        )}
        
        <Routes>
          {/* Public Routes */}
          <Route 
            path="/login" 
            element={
              isAuthenticated ? <Navigate to="/dashboard" /> : <Login onLogin={handleLogin} />
            } 
          />

          <Route
            path="/register"
            element={
              isAuthenticated ? <Navigate to="/dashboard" /> : <Register />
            }
          />

          {/* Protected Passenger Routes */}
          <Route 
            path="/dashboard" 
            element={
              <ProtectedRoute isAuthenticated={isAuthenticated} user={user} role="passenger">
                <Dashboard user={user} />
              </ProtectedRoute>
            } 
          />

          <Route
            path="/documents"
            element={
              <ProtectedRoute isAuthenticated={isAuthenticated} user={user} role="passenger">
                <Documents />
              </ProtectedRoute>
            }
          />

          <Route
            path="/notifications"
            element={
              <ProtectedRoute isAuthenticated={isAuthenticated} user={user} role="passenger">
                <Notifications />
              </ProtectedRoute>
            }
          />

          <Route
            path="/credentials"
            element={
              <ProtectedRoute isAuthenticated={isAuthenticated} user={user} role="passenger">
                <Credentials />
              </ProtectedRoute>
            }
          />

          <Route
            path="/present"
            element={
              <ProtectedRoute isAuthenticated={isAuthenticated} user={user} role="passenger">
                <PresentIdentity />
              </ProtectedRoute>
            }
          />

          <Route
            path="/profile"
            element={
              <ProtectedRoute isAuthenticated={isAuthenticated} user={user}>
                <Profile user={user} onAccountDeleted={handleLogout} />
              </ProtectedRoute>
            }
          />

          <Route
            path="/settings"
            element={
              <ProtectedRoute isAuthenticated={isAuthenticated} user={user}>
                <Settings user={user} theme={theme} onThemeChange={handleThemeChange} />
              </ProtectedRoute>
            }
          />

          {/* Train Verifier Routes */}
          <Route 
            path="/verify" 
            element={
              <ProtectedRoute isAuthenticated={isAuthenticated} user={user} role="train_verifier">
                <VerifyPresentation />
              </ProtectedRoute>
            } 
          />


          {/* University Agent */}
          <Route
            path="/agent"
            element={
              <ProtectedRoute isAuthenticated={isAuthenticated} user={user} role="university_agent">
                <UniversityAgentDashboard />
              </ProtectedRoute>
            }
          />

          {/* Default */}
          <Route path="/" element={<Navigate to={user?.role === 'university_agent' ? '/agent' : '/dashboard'} />} />
          <Route path="*" element={<Navigate to={user?.role === 'university_agent' ? '/agent' : '/dashboard'} />} />
        </Routes>
      </div>
    </Router>
  )
}

export default App

