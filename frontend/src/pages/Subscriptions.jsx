/**
 * Subscriptions — pagina pentru abonamente CFR cu scope pe ruta.
 *
 * Structura:
 *   - Header cu buton "Cumpara abonament nou"
 *   - Lista abonamentelor curente (active, expirate, anulate)
 *   - Modal de cumparare cu quote preview live
 *
 * Reguli de business (vezi backend/subscription_business.py):
 *   - Abonament scope='route' acopera o ruta exacta (origin <-> dest)
 *   - Tipuri: monthly (30 zile) sau annual (365 zile)
 *   - Reducere 50% DOAR pentru studenti verificati pe ruta home <-> universitate
 *   - Anti-overlap: un singur abonament activ per ruta per user
 *   - La cumparare bilet pe ruta acoperita -> price=0 (gratuit) automat
 */
import { useEffect, useState, useCallback } from 'react'
import { Link } from 'react-router-dom'
import {
  buySubscription,
  cancelSubscription,
  getMySubscriptions,
  getSubscriptionQuote,
  searchStations,
} from '../services/api'

const STATUS_META = {
  active:    { label: 'Activ',    cls: 'bg-emerald-100 dark:bg-emerald-900 text-emerald-700 dark:text-emerald-200' },
  expired:   { label: 'Expirat',  cls: 'bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300' },
  cancelled: { label: 'Anulat',   cls: 'bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-200' },
  suspended: { label: 'Suspendat', cls: 'bg-amber-100 dark:bg-amber-900 text-amber-700 dark:text-amber-200' },
}

const TYPE_META = {
  monthly: { label: 'Lunar (30 zile)' },
  annual:  { label: 'Anual (365 zile)' },
}


// ----------------------------------------------------------------------------
// StationPicker — typeahead simplu pentru selectie statie
// ----------------------------------------------------------------------------
function StationPicker({ label, value, onChange, placeholder }) {
  const [query, setQuery] = useState('')
  const [options, setOptions] = useState([])
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (value?.name) setQuery(value.name)
  }, [value])

  useEffect(() => {
    if (!open || query.length < 2) { setOptions([]); return }
    let cancelled = false
    searchStations(query, 8).then(rows => {
      if (!cancelled) setOptions(rows || [])
    }).catch(() => setOptions([]))
    return () => { cancelled = true }
  }, [query, open])

  return (
    <div className="relative">
      <label className="block text-sm font-semibold mb-1">{label}</label>
      <input
        type="text"
        value={query}
        onChange={(e) => { setQuery(e.target.value); setOpen(true) }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 200)}
        placeholder={placeholder}
        className="w-full px-3 py-2 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
      />
      {open && options.length > 0 && (
        <ul className="absolute z-10 mt-1 w-full bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-xl shadow-lg max-h-56 overflow-y-auto">
          {options.map(s => (
            <li
              key={s.station_id}
              onClick={() => { onChange(s); setQuery(s.name); setOpen(false) }}
              className="px-3 py-2 hover:bg-slate-100 dark:hover:bg-slate-800 cursor-pointer text-sm"
            >
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
// BuyModal — formular cumparare cu quote live
// ----------------------------------------------------------------------------
function BuyModal({ onClose, onSuccess }) {
  const [from, setFrom] = useState(null)
  const [to, setTo] = useState(null)
  const [type, setType] = useState('monthly')
  const [quote, setQuote] = useState(null)
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  // Refresh quote la fiecare schimbare
  useEffect(() => {
    if (!from?.station_id || !to?.station_id || from.station_id === to.station_id) {
      setQuote(null)
      return
    }
    let cancelled = false
    setLoading(true)
    setError('')
    getSubscriptionQuote({
      from_station_id: from.station_id,
      to_station_id: to.station_id,
      subscription_type: type,
    })
      .then(q => { if (!cancelled) setQuote(q) })
      .catch(e => { if (!cancelled) setError(e.detail?.message || e.message || 'Eroare quote') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [from, to, type])

  const handleSubmit = async () => {
    if (!from || !to) { setError('Selectati ambele statii.'); return }
    setSubmitting(true)
    setError('')
    try {
      const result = await buySubscription({
        from_station_id: from.station_id,
        to_station_id: to.station_id,
        subscription_type: type,
      })
      onSuccess(result)
    } catch (e) {
      setError(e.detail?.message || e.message || 'Eroare la cumparare')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 overflow-y-auto">
      <div className="bg-white dark:bg-slate-900 rounded-2xl shadow-2xl max-w-xl w-full p-6 my-8 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-bold">Cumpara abonament</h2>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 text-xl">×</button>
        </div>

        <StationPicker
          label="Statia de plecare"
          value={from}
          onChange={setFrom}
          placeholder="Tasteaza pentru cautare..."
        />
        <StationPicker
          label="Statia de sosire"
          value={to}
          onChange={setTo}
          placeholder="Tasteaza pentru cautare..."
        />

        <div>
          <label className="block text-sm font-semibold mb-1">Tip abonament</label>
          <div className="flex gap-2">
            {Object.entries(TYPE_META).map(([key, meta]) => (
              <label
                key={key}
                className={`flex-1 p-2 rounded-xl border cursor-pointer text-sm text-center ${
                  type === key
                    ? 'border-emerald-500 bg-emerald-50 dark:bg-emerald-900/30 font-semibold'
                    : 'border-slate-300 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800'
                }`}
              >
                <input
                  type="radio"
                  className="sr-only"
                  checked={type === key}
                  onChange={() => setType(key)}
                />
                {meta.label}
              </label>
            ))}
          </div>
        </div>

        {/* Quote preview */}
        {loading && <div className="text-sm text-slate-500">Se calculeaza pretul...</div>}
        {quote && (
          <div className={`rounded-xl p-3 text-sm border ${
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
            <div className="flex justify-between font-bold text-base pt-2 border-t border-slate-300 dark:border-slate-700 mt-2">
              <span>Total</span>
              <span>{quote.final_price.toFixed(2)} RON</span>
            </div>
            <div className="text-xs mt-2 italic text-slate-600 dark:text-slate-400">
              {quote.discount_reason}
            </div>
          </div>
        )}

        {error && (
          <div className="bg-red-50 dark:bg-red-900/30 border border-red-300 dark:border-red-800 text-red-700 dark:text-red-300 text-sm rounded-xl p-2">
            {error}
          </div>
        )}

        <div className="flex gap-2 justify-end pt-2 border-t border-slate-200 dark:border-slate-700">
          <button
            onClick={onClose}
            disabled={submitting}
            className="px-4 py-2 rounded-xl border border-slate-300 dark:border-slate-600 hover:bg-slate-100 dark:hover:bg-slate-800"
          >
            Renunta
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting || !quote}
            className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-semibold disabled:opacity-50"
          >
            {submitting ? 'Se cumpara...' : 'Confirma cumparare'}
          </button>
        </div>
      </div>
    </div>
  )
}


// ----------------------------------------------------------------------------
// SubscriptionCard
// ----------------------------------------------------------------------------
function SubscriptionCard({ s, onCancel }) {
  const meta = STATUS_META[s.status] || STATUS_META.expired
  const typeMeta = TYPE_META[s.subscription_type] || { label: s.subscription_type }
  const canCancel = s.status === 'active'

  return (
    <div className="rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-bold text-slate-900 dark:text-slate-100">
            {typeMeta.label}
          </div>
          <div className="text-xs text-slate-500 mt-0.5">
            {s.from_station_name || `St. ${s.from_station_id}`}
            {' ↔ '}
            {s.to_station_name || `St. ${s.to_station_id}`}
            {s.route_distance_km && <span> · {s.route_distance_km} km</span>}
          </div>
        </div>
        <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${meta.cls}`}>
          {meta.label}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2 mt-3 text-xs">
        <div>
          <div className="text-slate-500">Valabil de la</div>
          <div className="font-semibold">{s.valid_from}</div>
        </div>
        <div>
          <div className="text-slate-500">Valabil pana</div>
          <div className="font-semibold">{s.valid_until}</div>
        </div>
        <div>
          <div className="text-slate-500">Pret platit</div>
          <div className="font-semibold">{Number(s.price).toFixed(2)} RON</div>
        </div>
        {s.days_remaining !== null && s.days_remaining !== undefined && (
          <div>
            <div className="text-slate-500">Zile ramase</div>
            <div className={`font-semibold ${s.days_remaining <= 7 ? 'text-amber-600 dark:text-amber-400' : ''}`}>
              {s.days_remaining}
              {s.days_remaining <= 7 && <span title="Expira curand!" className="ml-1">⚠️</span>}
            </div>
          </div>
        )}
      </div>

      {canCancel && (
        <div className="flex gap-2 mt-3 pt-3 border-t border-slate-200 dark:border-slate-700">
          <button
            onClick={() => onCancel(s)}
            className="flex-1 px-3 py-1.5 rounded-lg text-xs font-semibold border border-red-300 dark:border-red-700 text-red-700 dark:text-red-300 hover:bg-red-50 dark:hover:bg-red-900/30"
          >
            Anulare cu refund pro-rata
          </button>
        </div>
      )}
    </div>
  )
}


// ----------------------------------------------------------------------------
// CancelModal
// ----------------------------------------------------------------------------
function CancelModal({ sub, onClose, onSuccess }) {
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  // Estimam refund client-side (backend recalculeaza oricum)
  const today = new Date()
  const start = new Date(sub.valid_from)
  const end = new Date(sub.valid_until)
  const totalDays = Math.max(1, (end - start) / 86400000)
  const daysUsed = Math.max(0, (today - start) / 86400000)
  const pctUsed = daysUsed / totalDays

  let estTier, estRefund, tierMsg
  if (today < start) {
    estTier = 'full_not_started'
    estRefund = Number(sub.price)
    tierMsg = 'Abonamentul nu a inceput inca. Refund 100%.'
  } else if (pctUsed >= 0.5) {
    estTier = 'more_than_half_used'
    estRefund = 0
    tierMsg = 'Mai mult de jumatate folosit. Fara refund.'
  } else {
    estTier = 'partial_pro_rata'
    const daysUnused = totalDays - daysUsed
    estRefund = Number(sub.price) * (daysUnused / totalDays) * 0.5
    tierMsg = `Refund pro-rata: ${Math.round(daysUnused)} zile neutilizate × 50% penalty CFR.`
  }

  const handle = async () => {
    setSubmitting(true)
    try {
      const r = await cancelSubscription(sub.subscription_id)
      onSuccess(r)
    } catch (e) {
      setError(e.detail?.message || e.message || 'Eroare anulare')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="bg-white dark:bg-slate-900 rounded-2xl max-w-md w-full p-6 space-y-4">
        <h2 className="text-xl font-bold">Anulare abonament</h2>
        <div className="text-sm text-slate-600 dark:text-slate-300 space-y-1">
          <p>Sunteti pe cale sa anulati abonamentul:</p>
          <div className="bg-slate-50 dark:bg-slate-800 rounded-lg p-3 text-xs space-y-0.5">
            <div>{TYPE_META[sub.subscription_type]?.label}</div>
            <div>{sub.from_station_name} ↔ {sub.to_station_name}</div>
            <div>Pret platit: {Number(sub.price).toFixed(2)} RON</div>
          </div>
        </div>

        <div className={`rounded-lg p-3 text-sm border ${
          estTier === 'full_not_started' ? 'bg-emerald-50 dark:bg-emerald-900/30 border-emerald-300 dark:border-emerald-700' :
          estTier === 'partial_pro_rata' ? 'bg-amber-50 dark:bg-amber-900/30 border-amber-300 dark:border-amber-700' :
          'bg-red-50 dark:bg-red-900/30 border-red-300 dark:border-red-700'
        }`}>
          <div className="font-semibold mb-1">{tierMsg}</div>
          <div>Refund estimat: <strong>{estRefund.toFixed(2)} RON</strong></div>
        </div>

        {error && (
          <div className="bg-red-50 dark:bg-red-900/30 border border-red-300 dark:border-red-800 text-red-700 dark:text-red-300 text-sm rounded-lg p-2">
            {error}
          </div>
        )}

        <div className="flex gap-2 justify-end">
          <button onClick={onClose} disabled={submitting} className="px-4 py-2 rounded-xl border border-slate-300 dark:border-slate-600 hover:bg-slate-100 dark:hover:bg-slate-800">
            Renunta
          </button>
          <button onClick={handle} disabled={submitting} className="px-4 py-2 rounded-xl bg-red-600 hover:bg-red-700 text-white font-semibold disabled:opacity-50">
            {submitting ? 'Se anuleaza...' : 'Confirma anularea'}
          </button>
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
  const [cancelTarget, setCancelTarget] = useState(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const rows = await getMySubscriptions()
      setSubs(rows || [])
      setError('')
    } catch (e) {
      setError(e.message || 'Eroare la incarcare')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), 5000)
    return () => clearTimeout(t)
  }, [toast])

  const handleBuySuccess = (r) => {
    setShowBuy(false)
    setToast({
      kind: 'success',
      msg: `Abonament cumparat! Valabil pana pe ${r.valid_until}. ${r.message}`,
    })
    refresh()
  }

  const handleCancelSuccess = (r) => {
    setCancelTarget(null)
    setToast({
      kind: 'success',
      msg: `Abonament anulat. Refund: ${Number(r.refund_amount).toFixed(2)} RON. ${r.message}`,
    })
    refresh()
  }

  const active = subs.filter(s => s.status === 'active')
  const history = subs.filter(s => s.status !== 'active')

  return (
    <div className="container mx-auto px-4 py-6 max-w-4xl">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Abonamentele mele</h1>
        <button
          onClick={() => setShowBuy(true)}
          className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-semibold"
        >
          Cumpara abonament nou
        </button>
      </div>

      <div className="text-xs text-slate-500 dark:text-slate-400 mb-4">
        Abonamentele acopera o ruta specifica (origin ↔ destination). Biletele cumparate pe ruta acoperita sunt automat gratuite. Studentii verificati pe ruta home ↔ universitate beneficiaza de reducere 50% (OUG 11/2024).
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
        <div className="mb-4 p-3 rounded-xl bg-red-50 dark:bg-red-900/30 border border-red-300 dark:border-red-700 text-red-800 dark:text-red-200 text-sm">
          {error}
        </div>
      )}

      {loading && <div className="text-slate-500">Se incarca...</div>}

      {!loading && subs.length === 0 && (
        <div className="bg-slate-50 dark:bg-slate-800 rounded-2xl p-6 text-center text-slate-500">
          Nu ai cumparat inca niciun abonament. <button onClick={() => setShowBuy(true)} className="text-emerald-600 underline">Cumpara primul</button>.
        </div>
      )}

      {active.length > 0 && (
        <>
          <h2 className="text-sm font-semibold text-slate-600 dark:text-slate-300 mt-4 mb-2">Active ({active.length})</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {active.map(s => (
              <SubscriptionCard key={s.subscription_id} s={s} onCancel={setCancelTarget} />
            ))}
          </div>
        </>
      )}

      {history.length > 0 && (
        <>
          <h2 className="text-sm font-semibold text-slate-600 dark:text-slate-300 mt-6 mb-2">Istoric ({history.length})</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {history.map(s => (
              <SubscriptionCard key={s.subscription_id} s={s} onCancel={setCancelTarget} />
            ))}
          </div>
        </>
      )}

      {showBuy && (
        <BuyModal onClose={() => setShowBuy(false)} onSuccess={handleBuySuccess} />
      )}

      {cancelTarget && (
        <CancelModal
          sub={cancelTarget}
          onClose={() => setCancelTarget(null)}
          onSuccess={handleCancelSuccess}
        />
      )}
    </div>
  )
}
