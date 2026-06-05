import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { buyTicket, getTicketsCatalog, quoteTicket } from '../services/api'

const TYPE_LABEL = { single: 'Bilet simplu', return: 'Dus-întors' }

export default function BuyTicket() {
  const navigate = useNavigate()
  const [catalog, setCatalog] = useState([])
  const [selectedTrainId, setSelectedTrainId] = useState('')
  const [travelDate, setTravelDate] = useState(() => {
    const d = new Date()
    d.setDate(d.getDate() + 1)
    return d.toISOString().slice(0, 10)
  })
  const [ticketType, setTicketType] = useState('single')
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    let alive = true
    getTicketsCatalog()
      .then((rows) => { if (alive) setCatalog(rows || []) })
      .catch((e) => { if (alive) setError(e.message) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [])

  const selectedRoute = useMemo(
    () => catalog.find((r) => String(r.train_id) === String(selectedTrainId)),
    [catalog, selectedTrainId]
  )

  const [quote, setQuote] = useState(null)
  const [quoting, setQuoting] = useState(false)

  // Cere preview pret de la backend cand userul are toate datele
  useEffect(() => {
    if (!selectedRoute || !travelDate || !ticketType) {
      setQuote(null)
      return
    }
    let alive = true
    setQuoting(true)
    quoteTicket({
      train_id: selectedRoute.train_id,
      departure_station_id: selectedRoute.departure_id,
      arrival_station_id: selectedRoute.arrival_id,
      travel_date: travelDate,
      ticket_type: ticketType,
    })
      .then((q) => { if (alive) setQuote(q) })
      .catch(() => { if (alive) setQuote(null) })
      .finally(() => { if (alive) setQuoting(false) })
    return () => { alive = false }
  }, [selectedRoute, travelDate, ticketType])

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!selectedRoute) {
      setError('Selectează o rută')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      const r = await buyTicket({
        train_id: selectedRoute.train_id,
        departure_station_id: selectedRoute.departure_id,
        arrival_station_id: selectedRoute.arrival_id,
        travel_date: travelDate,
        ticket_type: ticketType,
      })
      // după cumpărare → MyTickets, cu un highlight pe biletul nou
      navigate('/tickets', { state: { newTicketId: r.ticket_id } })
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="h-8 bg-slate-200 dark:bg-slate-800 rounded-xl w-48 mb-6 animate-pulse" />
        <div className="h-40 bg-slate-100 dark:bg-slate-900 rounded-2xl animate-pulse" />
      </div>
    )
  }

  const minDate = new Date().toISOString().slice(0, 10)

  return (
    <div className="container mx-auto px-4 py-8 max-w-2xl">
      <h1 className="text-3xl font-bold mb-6 text-slate-900 dark:text-slate-50">Cumpără bilet</h1>

      {error && (
        <div className="mb-4 rounded-xl border border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300 px-4 py-3 text-sm">
          {error}
        </div>
      )}

      <form
        onSubmit={handleSubmit}
        className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-700 p-6 shadow-sm space-y-5"
      >
        <div>
          <label className="block text-sm font-semibold mb-2 text-slate-700 dark:text-slate-200">Rută</label>
          <select
            value={selectedTrainId}
            onChange={(e) => setSelectedTrainId(e.target.value)}
            required
            className="w-full rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 px-3 py-2"
          >
            <option value="">Alege ruta…</option>
            {catalog.map((r) => (
              <option key={r.train_id} value={r.train_id}>
                {r.departure_name} → {r.arrival_name} · {r.train_number} ({r.train_type}) · {r.operator_name}
              </option>
            ))}
          </select>
          {selectedRoute && (
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-2">
              Distanță: {selectedRoute.total_distance_km} km · Capacitate: {selectedRoute.capacity_seats} locuri
            </p>
          )}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          <div>
            <label className="block text-sm font-semibold mb-2 text-slate-700 dark:text-slate-200">Data călătoriei</label>
            <input
              type="date"
              value={travelDate}
              min={minDate}
              onChange={(e) => setTravelDate(e.target.value)}
              required
              className="w-full rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 px-3 py-2"
            />
          </div>

          <div>
            <label className="block text-sm font-semibold mb-2 text-slate-700 dark:text-slate-200">Tip bilet</label>
            <select
              value={ticketType}
              onChange={(e) => setTicketType(e.target.value)}
              className="w-full rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 px-3 py-2"
            >
              {Object.entries(TYPE_LABEL).map(([v, l]) => (
                <option key={v} value={v}>{l}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Preview tarif din BD - transparenta GDPR + legal */}
        {selectedRoute && (
          <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 p-4">
            <div className="text-xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-2">
              Detalii tarif
            </div>
            {quoting && (
              <div className="text-sm text-slate-500 dark:text-slate-400 animate-pulse">Calculez tariful…</div>
            )}
            {!quoting && quote && (
              <div className="space-y-1.5 text-sm">
                <div className="flex justify-between">
                  <span className="text-slate-600 dark:text-slate-400">Distanță:</span>
                  <span className="font-mono text-slate-700 dark:text-slate-200">{quote.distance_km} km</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-600 dark:text-slate-400">Tarif normal {ticketType === 'return' ? '(dus-întors)' : '(dus)'}:</span>
                  <span className="font-mono text-slate-700 dark:text-slate-200">{quote.base_price.toFixed(2)} RON</span>
                </div>
                {quote.discount_percent > 0 && (
                  <div className="flex justify-between text-emerald-600 dark:text-emerald-400">
                    <span>Reducere student (OUG 11/2024) {quote.discount_percent}%:</span>
                    <span className="font-mono">−{quote.savings.toFixed(2)} RON</span>
                  </div>
                )}
                <div className="border-t border-slate-200 dark:border-slate-700 mt-2 pt-2 flex justify-between items-baseline">
                  <span className="font-bold text-slate-900 dark:text-slate-100">Plătești:</span>
                  <span className="font-bold text-xl text-emerald-600 dark:text-emerald-400 font-mono">
                    {quote.final_price.toFixed(2)} RON
                  </span>
                </div>
              </div>
            )}
            {!quoting && !quote && (
              <div className="text-xs text-slate-500 dark:text-slate-400">
                💡 Studenții cu credențial activ primesc automat 90% reducere (OUG 11/2024, număr nelimitat de călătorii).
              </div>
            )}
          </div>
        )}

        <div className="flex gap-3 pt-2">
          <button
            type="submit"
            disabled={submitting || !selectedRoute}
            className="flex-1 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold rounded-xl px-4 py-3 transition"
          >
            {submitting ? 'Se procesează…' : 'Cumpără bilet'}
          </button>
          <Link
            to="/tickets"
            className="px-4 py-3 rounded-xl border border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800 transition"
          >
            Biletele mele
          </Link>
        </div>
      </form>
    </div>
  )
}
