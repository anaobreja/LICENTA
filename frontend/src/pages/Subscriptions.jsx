import { useEffect, useState, useCallback } from 'react'
import {
  buySubscription,
  getMySubscriptions,
  getSubscriptionQuote,
  searchStations,
} from '../services/api'

const STATUS_META = {
  active:    { label: 'Activ',     cls: 'bg-emerald-100 dark:bg-emerald-900 text-emerald-700 dark:text-emerald-200' },
  expired:   { label: 'Expirat',   cls: 'bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300' },
  cancelled: { label: 'Anulat',    cls: 'bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-200' },
  suspended: { label: 'Suspendat', cls: 'bg-amber-100 dark:bg-amber-900 text-amber-700 dark:text-amber-200' },
}

const TYPE_META = {
  monthly: { label: 'Lunar', sub: '30 zile' },
  annual:  { label: 'Anual', sub: '365 zile' },
}

const TABS = [
  { id: 'active',   label: 'Active',   emptyMsg: 'Nu ai abonamente active.' },
  { id: 'expired',  label: 'Expirate', emptyMsg: 'Nu ai abonamente expirate.' },
]

function categorizeSub(s) {
  if (s.status === 'active') return 'active'
  if (s.status === 'expired') return 'expired'
  return 'cancelled'
}

function fmtDate(iso) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleDateString('ro-RO', { day: '2-digit', month: 'short', year: 'numeric' })
  } catch { return iso }
}


// ----------------------------------------------------------------------------
// StationPicker
// ----------------------------------------------------------------------------
function StationPicker({ label, value, onChange, placeholder }) {
  const [query, setQuery] = useState('')
  const [options, setOptions] = useState([])
  const [open, setOpen] = useState(false)

  useEffect(() => { if (value?.name) setQuery(value.name) }, [value])

  useEffect(() => {
    if (!open || query.length < 2) { setOptions([]); return }
    let cancelled = false
    searchStations(query, 8).then(rows => { if (!cancelled) setOptions(rows || []) }).catch(() => setOptions([]))
    return () => { cancelled = true }
  }, [query, open])

  return (
    <div className="relative">
      <label className="block text-sm font-semibold mb-1 text-slate-700 dark:text-slate-200">{label}</label>
      <input
        type="text"
        value={query}
        onChange={(e) => { setQuery(e.target.value); setOpen(true) }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 200)}
        placeholder={placeholder}
        className="w-full px-3 py-2 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100"
      />
      {open && options.length > 0 && (
        <ul className="absolute z-10 mt-1 w-full bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-xl shadow-lg max-h-56 overflow-y-auto">
          {options.map(s => (
            <li key={s.station_id} onClick={() => { onChange(s); setQuery(s.name); setOpen(false) }}
              className="px-3 py-2 hover:bg-slate-100 dark:hover:bg-slate-800 cursor-pointer text-sm">
              <div className="font-semibold">{s.name}</div>
              <div className="text-xs text-slate-500">{s.city} · {s.code}</div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}


// ----------------------------------------------------------------------------
// BuyModal
// ----------------------------------------------------------------------------
function BuyModal({ onClose, onSuccess }) {
  const [from, setFrom] = useState(null)
  const [to, setTo] = useState(null)
  const [type, setType] = useState('monthly')
  const [quote, setQuote] = useState(null)
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!from?.station_id || !to?.station_id || from.station_id === to.station_id) { setQuote(null); return }
    let cancelled = false
    setLoading(true); setError('')
    getSubscriptionQuote({ from_station_id: from.station_id, to_station_id: to.station_id, subscription_type: type })
      .then(q => { if (!cancelled) setQuote(q) })
      .catch(e => { if (!cancelled) setError(e.detail?.message || e.message || 'Eroare quote') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [from, to, type])

  const handleSubmit = async () => {
    if (!from || !to) { setError('Selectati ambele statii.'); return }
    setSubmitting(true); setError('')
    try {
      onSuccess(await buySubscription({ from_station_id: from.station_id, to_station_id: to.station_id, subscription_type: type }))
    } catch (e) {
      setError(e.detail?.message || e.message || 'Eroare la cumparare')
    } finally { setSubmitting(false) }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 overflow-y-auto">
      <div className="bg-white dark:bg-slate-900 rounded-2xl shadow-2xl max-w-xl w-full p-6 my-8 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-bold text-slate-900 dark:text-slate-100">Cumpara abonament</h2>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 text-2xl leading-none">×</button>
        </div>

        <StationPicker label="Statia de plecare" value={from} onChange={setFrom} placeholder="Tasteaza pentru cautare..." />
        <StationPicker label="Statia de sosire" value={to} onChange={setTo} placeholder="Tasteaza pentru cautare..." />

        <div>
          <label className="block text-sm font-semibold mb-2 text-slate-700 dark:text-slate-200">Tip abonament</label>
          <div className="flex gap-2">
            {Object.entries(TYPE_META).map(([key, meta]) => (
              <label key={key} className={`flex-1 p-3 rounded-xl border cursor-pointer text-sm text-center transition ${
                type === key
                  ? 'border-emerald-500 bg-emerald-50 dark:bg-emerald-900/30 font-semibold text-emerald-700 dark:text-emerald-300'
                  : 'border-slate-300 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-300'
              }`}>
                <input type="radio" className="sr-only" checked={type === key} onChange={() => setType(key)} />
                <div className="font-bold">{meta.label}</div>
                <div className="text-xs opacity-70">{meta.sub}</div>
              </label>
            ))}
          </div>
        </div>

        {loading && <div className="text-sm text-slate-500">Se calculeaza pretul...</div>}
        {quote && (
          <div className={`rounded-xl p-4 text-sm border ${
            quote.is_student_route
              ? 'bg-emerald-50 dark:bg-emerald-900/30 border-emerald-300 dark:border-emerald-700'
              : 'bg-slate-50 dark:bg-slate-800 border-slate-300 dark:border-slate-700'
          }`}>
            <div className="flex justify-between mb-1">
              <span className="text-slate-600 dark:text-slate-400">Distanta</span>
              <span className="font-semibold">{quote.distance_km} km</span>
            </div>
            <div className="flex justify-between mb-1">
              <span className="text-slate-600 dark:text-slate-400">Pret de baza</span>
              <span>{quote.base_price.toFixed(2)} RON</span>
            </div>
            {quote.discount_amount > 0 && (
              <div className="flex justify-between mb-1 text-emerald-700 dark:text-emerald-300">
                <span>Reducere ({quote.discount_pct}%)</span>
                <span>−{quote.discount_amount.toFixed(2)} RON</span>
              </div>
            )}
            <div className="flex justify-between font-bold text-base pt-2 border-t border-slate-300 dark:border-slate-600 mt-2">
              <span>Total</span>
              <span>{quote.final_price.toFixed(2)} RON</span>
            </div>
            {quote.discount_reason && (
              <div className="text-xs mt-2 italic text-slate-500 dark:text-slate-400">{quote.discount_reason}</div>
            )}
          </div>
        )}

        {error && (
          <div className="bg-red-50 dark:bg-red-900/30 border border-red-300 dark:border-red-800 text-red-700 dark:text-red-300 text-sm rounded-xl p-3">
            {error}
          </div>
        )}

        <div className="flex gap-2 justify-end pt-2 border-t border-slate-200 dark:border-slate-700">
          <button onClick={onClose} disabled={submitting}
            className="px-4 py-2 rounded-xl border border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition">
            Renunta
          </button>
          <button onClick={handleSubmit} disabled={submitting || !quote}
            className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-semibold disabled:opacity-50 transition">
            {submitting ? 'Se cumpara...' : 'Confirma cumpararea'}
          </button>
        </div>
      </div>
    </div>
  )
}


// ----------------------------------------------------------------------------
// SubscriptionCard — aceeasi structura ca un MultiPaxCard din MyTickets
// ----------------------------------------------------------------------------
function SubscriptionCard({ s }) {
  const meta = STATUS_META[s.status] || STATUS_META.expired
  const typeMeta = TYPE_META[s.subscription_type] || { label: s.subscription_type, sub: '' }

  return (
    <div className="rounded-2xl border-2 border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 overflow-hidden hover:border-emerald-300 dark:hover:border-emerald-700 transition-all">
      {/* Header — badge status + tip */}
      <div className="flex items-center justify-between px-4 pt-3 pb-1">
        <div className="flex items-center gap-2">
          <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${meta.cls}`}>
            {meta.label}
          </span>
          <span className="text-[10px] font-semibold tracking-wider text-slate-500 dark:text-slate-400 uppercase">
            {typeMeta.label} · {typeMeta.sub}
          </span>
        </div>
        {s.days_remaining != null && s.status === 'active' && (
          <span className={`text-xs font-semibold ${s.days_remaining <= 7 ? 'text-amber-600 dark:text-amber-400' : 'text-slate-500 dark:text-slate-400'}`}>
            {s.days_remaining <= 7 && '⚠ '}{s.days_remaining} zile
          </span>
        )}
      </div>

      {/* Ruta — acelasi stil ca RouteHeader din MyTickets */}
      <div className="px-4 py-3">
        <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 mb-3">
          <div>
            <div className="text-lg font-bold text-slate-900 dark:text-slate-50 leading-tight truncate">
              {s.from_station_name || `St. ${s.from_station_id}`}
            </div>
          </div>
          <div className="text-slate-400 dark:text-slate-500 text-lg">↔</div>
          <div className="text-right">
            <div className="text-lg font-bold text-slate-900 dark:text-slate-50 leading-tight truncate">
              {s.to_station_name || `St. ${s.to_station_id}`}
            </div>
          </div>
        </div>

        {/* Detalii — separator + date + pret */}
        <div className="space-y-1.5 pt-2 border-t border-slate-100 dark:border-slate-700/50">
          <div className="flex items-center justify-between text-xs">
            <span className="text-slate-500 dark:text-slate-400">Valabilitate</span>
            <span className="font-medium text-slate-700 dark:text-slate-300">
              {fmtDate(s.valid_from)} – {fmtDate(s.valid_until)}
            </span>
          </div>
          <div className="flex items-center justify-between text-xs">
            <span className="text-slate-500 dark:text-slate-400">Pret platit</span>
            <span className="font-semibold text-slate-900 dark:text-slate-100">
              {Number(s.price).toFixed(2)} RON
              {s.route_distance_km && <span className="font-normal text-slate-400 ml-1">· {s.route_distance_km} km</span>}
            </span>
          </div>
        </div>
      </div>

    </div>
  )
}


// ----------------------------------------------------------------------------
// Subscriptions page
// ----------------------------------------------------------------------------
export default function Subscriptions() {
  const [subs, setSubs] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [toast, setToast] = useState(null)
  const [showBuy, setShowBuy] = useState(false)
  const [activeTab, setActiveTab] = useState('active')

  const refresh = useCallback(async () => {
    setLoading(true)
    try { setSubs((await getMySubscriptions()) || []); setError('') }
    catch (e) { setError(e.message || 'Eroare la incarcare') }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { refresh() }, [refresh])
  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), 5000)
    return () => clearTimeout(t)
  }, [toast])

  const handleBuySuccess = (r) => {
    setShowBuy(false)
    setToast({ kind: 'success', msg: `Abonament cumparat! Valabil pana pe ${r.valid_until}.` })
    setActiveTab('active')
    refresh()
  }

  return (
    <div className="container mx-auto px-4 py-8 max-w-4xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-3xl font-bold text-slate-900 dark:text-slate-50">Abonamentele mele</h1>
        <button
          onClick={() => setShowBuy(true)}
          className="px-4 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-semibold transition"
        >
          Cumpara abonament nou
        </button>
      </div>

      {toast && (
        <div className={`mb-4 p-3 rounded-xl border text-sm ${
          toast.kind === 'success'
            ? 'bg-emerald-50 dark:bg-emerald-900/30 border-emerald-300 dark:border-emerald-700 text-emerald-800 dark:text-emerald-200'
            : 'bg-red-50 dark:bg-red-900/30 border-red-300 dark:border-red-700 text-red-800 dark:text-red-200'
        }`}>
          {toast.msg}
        </div>
      )}
      {error && (
        <div className="mb-4 rounded-xl border border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-900/30 text-red-800 dark:text-red-200 px-4 py-3 text-sm">
          {error}
        </div>
      )}

      {loading ? (
        <div className="space-y-3">
          {[1, 2].map(i => <div key={i} className="h-36 bg-slate-100 dark:bg-slate-900 rounded-2xl animate-pulse" />)}
        </div>
      ) : (() => {
        const byTab = { active: [], expired: [], cancelled: [] }
        const counts = { active: 0, expired: 0, cancelled: 0 }
        for (const s of subs) {
          const cat = categorizeSub(s)
          byTab[cat].push(s)
          counts[cat]++
        }
        const current = byTab[activeTab] || []
        const currentTab = TABS.find(t => t.id === activeTab)

        return (
          <>
            {/* Tab bar */}
            <div className="flex flex-wrap gap-1 mb-4 border-b border-slate-200 dark:border-slate-700" role="tablist">
              {TABS.map(tab => {
                const isActive = activeTab === tab.id
                return (
                  <button
                    key={tab.id}
                    type="button"
                    role="tab"
                    aria-selected={isActive}
                    onClick={() => setActiveTab(tab.id)}
                    className={`px-4 py-2 text-sm font-semibold border-b-2 -mb-px transition-colors ${
                      isActive
                        ? 'border-emerald-600 text-emerald-700 dark:text-emerald-300'
                        : 'border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'
                    }`}
                  >
                    {tab.label}
                    <span className={`ml-2 inline-flex items-center justify-center min-w-[1.5rem] px-2 py-0.5 rounded-full text-xs font-bold ${
                      isActive
                        ? 'bg-emerald-100 dark:bg-emerald-900 text-emerald-800 dark:text-emerald-200'
                        : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300'
                    }`}>
                      {counts[tab.id]}
                    </span>
                  </button>
                )
              })}
            </div>

            {/* Continut tab */}
            {current.length === 0 ? (
              <div className="text-center py-12 rounded-2xl border border-dashed border-slate-300 dark:border-slate-700">
                <p className="text-slate-500 dark:text-slate-400 mb-3">{currentTab?.emptyMsg}</p>
                {activeTab === 'active' && (
                  <button
                    onClick={() => setShowBuy(true)}
                    className="text-sm text-emerald-600 dark:text-emerald-400 underline"
                  >
                    Cumpara primul abonament
                  </button>
                )}
              </div>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                {current.map(s => (
                  <SubscriptionCard key={s.subscription_id} s={s} />
                ))}
              </div>
            )}
          </>
        )
      })()}

      {showBuy && <BuyModal onClose={() => setShowBuy(false)} onSuccess={handleBuySuccess} />}
    </div>
  )
}
