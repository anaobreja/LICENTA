import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { getMyTickets } from '../services/api'

const STATUS_BADGE = {
  active:    { label: 'Activ',     cls: 'bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300' },
  used:      { label: 'Folosit',   cls: 'bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400' },
  expired:   { label: 'Expirat',   cls: 'bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300' },
  cancelled: { label: 'Anulat',    cls: 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300' },
  refunded:  { label: 'Rambursat', cls: 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300' },
}

const fmtDate = (iso) => {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleDateString('ro-RO', { day: '2-digit', month: 'long', year: 'numeric' })
  } catch { return iso }
}

function TicketCard({ t, highlight }) {
  const badge = STATUS_BADGE[t.ticket_status] || { label: t.ticket_status, cls: 'bg-slate-200 text-slate-700' }
  return (
    <div className={`rounded-2xl border p-5 shadow-sm bg-white dark:bg-slate-900 transition
      ${highlight ? 'border-emerald-400 ring-2 ring-emerald-300 dark:ring-emerald-700' : 'border-slate-200 dark:border-slate-700'}`}>
      <div className="flex items-start justify-between gap-3 mb-3">
        <div>
          <div className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-1">
            #{t.ticket_id} · {t.train_number} · {t.train_type}
          </div>
          <div className="text-lg font-bold text-slate-900 dark:text-slate-100">
            {t.departure_name} <span className="text-slate-400">→</span> {t.arrival_name}
          </div>
          <div className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            {t.departure_code} → {t.arrival_code}
          </div>
        </div>
        <span className={`text-xs font-semibold px-2 py-1 rounded-full whitespace-nowrap ${badge.cls}`}>{badge.label}</span>
      </div>

      <div className="grid grid-cols-3 gap-3 text-sm">
        <div>
          <div className="text-xs text-slate-500 dark:text-slate-400">Călătorie</div>
          <div className="font-semibold text-slate-700 dark:text-slate-200">{fmtDate(t.travel_date)}</div>
        </div>
        <div>
          <div className="text-xs text-slate-500 dark:text-slate-400">Tip</div>
          <div className="font-semibold text-slate-700 dark:text-slate-200">{t.ticket_type}</div>
        </div>
        <div>
          <div className="text-xs text-slate-500 dark:text-slate-400">Preț</div>
          <div className="font-semibold text-slate-900 dark:text-slate-100">
            {t.price?.toFixed?.(2) ?? t.price} RON
            {t.discount_applied > 0 && (
              <span className="ml-1 text-xs text-emerald-600 dark:text-emerald-400">(-{t.discount_applied}%)</span>
            )}
          </div>
        </div>
      </div>

      {t.ticket_status === 'active' && t.qr_token && (
        <details className="mt-4 group">
          <summary className="cursor-pointer text-sm font-semibold text-blue-600 dark:text-cyan-400 hover:underline">
            🪪 Arată QR pentru conductor
          </summary>
          <div className="mt-3 flex flex-col items-center gap-2 p-4 rounded-xl bg-slate-50 dark:bg-slate-800">
            <img
              alt="QR bilet"
              src={`https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(t.qr_token)}`}
              className="rounded-lg bg-white p-2"
            />
            <code className="text-[10px] text-slate-500 dark:text-slate-400 break-all max-w-xs text-center">
              {t.qr_token}
            </code>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Prezintă acest cod conductorului. Folosință unică.
            </p>
          </div>
        </details>
      )}
    </div>
  )
}

export default function MyTickets() {
  const location = useLocation()
  const newTicketId = location.state?.newTicketId
  const [tickets, setTickets] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const refresh = async () => {
    setLoading(true)
    try {
      const data = await getMyTickets()
      setTickets(data || [])
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { refresh() }, [])

  const active = tickets.filter((t) => t.ticket_status === 'active')
  const past = tickets.filter((t) => t.ticket_status !== 'active')

  return (
    <div className="container mx-auto px-4 py-8 max-w-3xl">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-3xl font-bold text-slate-900 dark:text-slate-50">Biletele mele</h1>
        <div className="flex gap-2">
          <button
            onClick={refresh}
            className="text-xs text-slate-500 hover:text-slate-700 dark:hover:text-slate-200 border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-1"
          >
            ↻ Refresh
          </button>
          <Link
            to="/tickets/buy"
            className="bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-semibold rounded-xl px-4 py-2 transition"
          >
            + Cumpără bilet
          </Link>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-xl border border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300 px-4 py-3 text-sm">
          {error}
        </div>
      )}

      {loading ? (
        <div className="space-y-3">
          {[1, 2].map((i) => (
            <div key={i} className="h-32 bg-slate-100 dark:bg-slate-900 rounded-2xl animate-pulse" />
          ))}
        </div>
      ) : tickets.length === 0 ? (
        <div className="text-center py-12 rounded-2xl border border-dashed border-slate-300 dark:border-slate-700">
          <p className="text-slate-500 dark:text-slate-400">Nu ai bilete încă.</p>
          <Link to="/tickets/buy" className="inline-block mt-3 text-blue-600 dark:text-cyan-400 font-semibold underline">
            Cumpără primul bilet →
          </Link>
        </div>
      ) : (
        <>
          {active.length > 0 && (
            <div className="space-y-3 mb-6">
              <h2 className="text-sm font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">Active</h2>
              {active.map((t) => (
                <TicketCard key={t.ticket_id} t={t} highlight={t.ticket_id === newTicketId} />
              ))}
            </div>
          )}
          {past.length > 0 && (
            <div className="space-y-3">
              <h2 className="text-sm font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">Istoric</h2>
              {past.map((t) => (
                <TicketCard key={t.ticket_id} t={t} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
