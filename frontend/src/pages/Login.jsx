import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { login } from '../services/api'

function Login({ onLogin }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [totpCode, setTotpCode] = useState('')
  const [needsMfa, setNeedsMfa] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const getRouteForRole = (role) => {
    if (role === 'train_verifier')   return '/verify'
    if (role === 'university_agent') return '/agent'
    return '/dashboard'
  }

  const isFormValid =
    email.trim().length > 0 && password.trim().length > 0 && (!needsMfa || totpCode.trim().length >= 6)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      const response = await login(email, password, needsMfa ? totpCode.trim() : undefined)
      localStorage.setItem('access_token', response.access_token)
      onLogin(response.user)
      setNeedsMfa(false)
      setTotpCode('')
      navigate(getRouteForRole(response.user?.role))
    } catch (err) {
      const msg = err?.message || 'Invalid email or password'
      if (msg === 'MFA_REQUIRED' || msg.includes('MFA_REQUIRED')) {
        setNeedsMfa(true)
        setError('Contul foloseste autentificare 2FA. Introdu codul din aplicatia authenticator.')
      } else {
        setError(msg)
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-100 px-4 py-10 transition-colors duration-300 dark:bg-slate-950">
      <div className="w-full max-w-5xl grid gap-6 md:grid-cols-[1.15fr_1fr]">
        <div className="hidden md:flex rounded-3xl p-8 bg-gradient-to-br from-cyan-700 via-sky-700 to-blue-900 text-white shadow-2xl dark:from-slate-800 dark:via-slate-900 dark:to-slate-950">
          <div className="self-end space-y-4">
            <p className="text-sm uppercase tracking-[0.2em] text-cyan-100">Railway Identity</p>
            <h1 className="text-4xl font-extrabold leading-tight">Acces sigur la bilete, abonamente si validare QR.</h1>
            <p className="text-cyan-50/90 max-w-md">
              Autentifica-te pentru a gestiona calatoriile, drepturile de transport si istoricul validarilor tale.
            </p>
          </div>
        </div>

        <div className="bg-white rounded-3xl p-8 shadow-xl border border-slate-200/80 transition-colors duration-300 dark:bg-slate-900 dark:border-slate-800">
          <h2 className="text-3xl font-black text-slate-900 dark:text-slate-50">Login</h2>
          <p className="text-slate-600 mt-2 mb-6 dark:text-slate-300">Intra in contul tau Railway Platform</p>

          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 p-3 rounded-xl mb-4">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit}>
            <div className="mb-4">
              <label className="block text-slate-700 mb-2 text-sm font-semibold dark:text-slate-200">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value)
                  setNeedsMfa(false)
                  setTotpCode('')
                }}
                className="w-full px-4 py-3 border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-cyan-500 focus:border-cyan-500 transition bg-white text-slate-900 dark:bg-slate-950 dark:text-slate-50 dark:border-slate-700"
                placeholder="you@example.com"
                autoComplete="email"
                required
              />
            </div>

            <div className="mb-4">
              <label className="block text-slate-700 mb-2 text-sm font-semibold dark:text-slate-200">Password</label>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value)
                    setNeedsMfa(false)
                    setTotpCode('')
                  }}
                  className="w-full px-4 py-3 pr-24 border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-cyan-500 focus:border-cyan-500 transition bg-white text-slate-900 dark:bg-slate-950 dark:text-slate-50 dark:border-slate-700"
                  placeholder="Enter your password"
                  autoComplete="current-password"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((prev) => !prev)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-sm font-semibold text-cyan-700 hover:text-cyan-900"
                >
                  {showPassword ? 'Hide' : 'Show'}
                </button>
              </div>
            </div>

            {needsMfa && (
              <div className="mb-6">
                <label className="block text-slate-700 mb-2 text-sm font-semibold dark:text-slate-200">
                  Cod autentificator (TOTP)
                </label>
                <input
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  value={totpCode}
                  onChange={(e) => setTotpCode(e.target.value)}
                  className="w-full px-4 py-3 border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-cyan-500 font-mono tracking-widest dark:bg-slate-950 dark:text-slate-50 dark:border-slate-700"
                  placeholder="000000"
                  maxLength={12}
                />
              </div>
            )}

            <button
              type="submit"
              disabled={loading || !isFormValid}
              className="w-full bg-slate-900 text-white py-3 rounded-xl font-semibold hover:bg-slate-800 disabled:opacity-50 disabled:cursor-not-allowed transition dark:bg-cyan-500 dark:hover:bg-cyan-400 dark:text-slate-950"
            >
              {loading ? 'Signing in...' : needsMfa ? 'Continua cu 2FA' : 'Sign in'}
            </button>
          </form>

          <div className="mt-4 text-sm text-center">
            <span className="text-slate-600 dark:text-slate-300">Nu ai cont? </span>
            <Link to="/register" className="text-cyan-700 font-semibold hover:underline">
              Creeaza cont nou
            </Link>
          </div>

        </div>
      </div>
    </div>
  )
}

export default Login
