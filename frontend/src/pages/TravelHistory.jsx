import { useEffect, useState } from 'react'
import { getValidationsHistory } from '../services/api'

const RESULT_BADGE = {
  valid:        { label: 'Valid',       cls: 'bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300' },
  invalid:      { label: 'Invalid',     cls: 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300' },
  expired:      { label: 'Expirat',     cls: 'bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300' },
  already_used: { label: 'Re-folosit',  cls: 'bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400' },
}

const fmtDateTime = (iso) => {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('ro-RO', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch { return iso }
}

export default function TravelHistory({ user }) {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let alive = true
    getValidationsHistory(100)
      .then((data) => { if (alive) setRows(data || []) })
      .catch((e) => { if (alive) setError(e.message) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [])

  const isConductor = user?.role === 'train_verifier'

  return (
    <div className="container mx-auto px-4 py-8 max-w-3xl">
      <h1 className="text-3xl font-bold mb-2 text-slate-900 dark:text-slate-50">Istoric călătorii</h1>
      <p className="text-sm text-slate-500 dark:text-slate-400 mb-6">
        {isConductor
          ? 'Validările pe care le-ai efectuat ca controlor de tren.'
          : 'Validările biletelor tale în trenuri.'}
      </p>

      {error && (
        <div className="mb-4 rounded-xl border border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300 px-4 py-3 text-sm">
          {error}
        </div>
      )}

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-20 bg-slate-100 dark:bg-slate-900 rounded-xl animate-pulse" />
          ))}
        </div>
      ) : rows.length === 0 ? (
        <div className="text-center py-12 rounded-2xl border border-dashed border-slate-300 dark:border-slate-700">
          <p className="text-slate-500 dark:text-slate-400">Nu există validări încă.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {rows.map((v) => {
            const badge = RESULT_BADGE[v.validation_result] || { label: v.validation_result, cls: 'bg-slate-200 text-slate-700' }
            const counterparty = isConductor
              ? `${v.passenger_first_name || ''} ${v.passenger_last_name || ''}`.trim() || 'Pasager necunoscut'
              : `${v.conductor_first_name || ''} ${v.conductor_last_name || ''}`.trim() || 'Controlor necunoscut'
            return (
              <div
                key={v.validation_id}
                className="rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 px-4 py-3 flex items-center justify-between gap-3"
              >
                <div className="min-w-0">
                  <div className="text-sm font-semibold text-slate-900 dark:text-slate-100 truncate">
                    {isConductor ? '👤' : '🚂'} {counterparty}
                  </div>
                  <div className="text-xs text-slate-500 dark:text-slate-400">
                    {fmtDateTime(v.validation_time)}
                    {v.source_type && <> · {v.source_type}</>}
                    {v.device_id && <> · {v.device_id}</>}
                  </div>
                </div>
                <span className={`text-xs font-semibold px-2 py-1 rounded-full whitespace-nowrap ${badge.cls}`}>
                  {badge.label}
                </span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
