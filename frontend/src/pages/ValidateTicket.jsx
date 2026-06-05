import { useState } from 'react'
import { Link } from 'react-router-dom'
import { validateTicketToken } from '../services/api'

const RESULT_STYLE = {
  valid:        { title: 'BILET VALID',          bg: 'bg-emerald-500',  ring: 'ring-emerald-300 dark:ring-emerald-700', icon: '✅' },
  already_used: { title: 'DEJA FOLOSIT',         bg: 'bg-amber-500',    ring: 'ring-amber-300  dark:ring-amber-700',    icon: '⚠️' },
  expired:      { title: 'BILET EXPIRAT',        bg: 'bg-amber-500',    ring: 'ring-amber-300  dark:ring-amber-700',    icon: '⏰' },
  invalid:      { title: 'BILET INVALID',        bg: 'bg-red-500',      ring: 'ring-red-300    dark:ring-red-700',      icon: '❌' },
}

export default function ValidateTicket() {
  const [token, setToken] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState(null) // { result, message, passenger_name, ticket_type, valid_until }
  const [error, setError] = useState(null)

  const handleSubmit = async (e) => {
    e?.preventDefault?.()
    if (!token.trim()) return
    setSubmitting(true)
    setError(null)
    setResult(null)
    try {
      const r = await validateTicketToken(token.trim(), 'web-validator')
      setResult(r)
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  const reset = () => {
    setToken('')
    setResult(null)
    setError(null)
  }

  const style = result ? (RESULT_STYLE[result.result] || RESULT_STYLE.invalid) : null

  return (
    <div className="container mx-auto px-4 py-8 max-w-2xl">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-3xl font-bold text-slate-900 dark:text-slate-50">Validare bilet</h1>
        <Link
          to="/verify"
          className="text-sm text-slate-500 hover:text-slate-700 dark:hover:text-slate-200 border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-1"
        >
          🪪 Verifică identitate
        </Link>
      </div>

      {!result && (
        <form onSubmit={handleSubmit} className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-700 p-6 shadow-sm space-y-4">
          <div>
            <label className="block text-sm font-semibold mb-2 text-slate-700 dark:text-slate-200">
              Token QR bilet
            </label>
            <textarea
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="Lipește aici token-ul scanat din QR-ul biletului…"
              rows={4}
              className="w-full rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 px-3 py-2 font-mono text-sm"
              autoFocus
            />
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-2">
              💡 Token-ul este single-use: după prima validare reușită, nu mai poate fi folosit.
            </p>
          </div>

          {error && (
            <div className="rounded-xl border border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300 px-4 py-3 text-sm">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={submitting || !token.trim()}
            className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold rounded-xl px-4 py-3 transition"
          >
            {submitting ? 'Se validează…' : 'Validează'}
          </button>
        </form>
      )}

      {result && style && (
        <div className={`rounded-2xl shadow-xl ring-4 ${style.ring} overflow-hidden`}>
          <div className={`${style.bg} text-white text-center py-10`}>
            <div className="text-6xl mb-3">{style.icon}</div>
            <div className="text-2xl font-bold tracking-wide">{style.title}</div>
            <div className="text-sm opacity-90 mt-1">{result.message}</div>
          </div>
          <div className="bg-white dark:bg-slate-900 p-6 space-y-3">
            {result.passenger_name && (
              <div>
                <div className="text-xs text-slate-500 dark:text-slate-400">Pasager</div>
                <div className="text-lg font-semibold text-slate-900 dark:text-slate-100">{result.passenger_name}</div>
              </div>
            )}
            {result.ticket_type && (
              <div>
                <div className="text-xs text-slate-500 dark:text-slate-400">Tip bilet / abonament</div>
                <div className="font-semibold text-slate-700 dark:text-slate-200">{result.ticket_type}</div>
              </div>
            )}
            {result.valid_until && (
              <div>
                <div className="text-xs text-slate-500 dark:text-slate-400">Valabil până</div>
                <div className="font-semibold text-slate-700 dark:text-slate-200">{result.valid_until}</div>
              </div>
            )}
            <button
              onClick={reset}
              className="w-full mt-4 bg-blue-600 hover:bg-blue-700 text-white font-semibold rounded-xl px-4 py-3 transition"
            >
              Scanează alt bilet
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
