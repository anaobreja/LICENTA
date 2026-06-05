import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { buyTicket, quoteTicket, searchStations, searchTrains } from '../services/api'

const TYPE_LABEL = { single: 'Bilet simplu', return: 'Dus-intors' }

function StationCombobox({ label, value, onChange, placeholder }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (value && !query) setQuery(value.name)
  }, [value])

  useEffect(() => {
    let alive = true
    setLoading(true)
    const t = setTimeout(() => {
      searchStations(query, 15)
        .then(r => { if (alive) setResults(r || []) })
        .catch(() => { if (alive) setResults([]) })
        .finally(() => { if (alive) setLoading(false) })
    }, 200)
    return () => { alive = false; clearTimeout(t) }
  }, [query])

  return (
    <div className="relative">
      <label className="block text-sm font-semibold mb-2 text-slate-700 dark:text-slate-200">{label}</label>
      <input
        type="text"
        value={query}
        onChange={(e) => { setQuery(e.target.value); setOpen(true); if (value) onChange(null) }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 180)}
        placeholder={placeholder}
        className="w-full rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 px-3 py-2"
        autoComplete="off"
      />
      {open && (
        <div className="absolute z-10 mt-1 w-full bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl shadow-lg max-h-72 overflow-auto">
          {loading && <div className="p-3 text-xs text-slate-500">Caut...</div>}
          {!loading && results.length === 0 && <div className="p-3 text-xs text-slate-500">Niciun rezultat</div>}
          {results.map((s) => (
            <button
              key={s.station_id}
              type="button"
              onMouseDown={(e) => { e.preventDefault(); onChange(s); setQuery(s.name); setOpen(false) }}
              className="w-full text-left px-3 py-2 hover:bg-slate-100 dark:hover:bg-slate-700 text-sm"
            >
              <div className="font-semibold text-slate-900 dark:text-slate-100">{s.name}</div>
              <div className="text-xs text-slate-500 dark:text-slate-400">{s.city} - {s.code}</div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

export default function BuyTicket() {
  const navigate = useNavigate()
  const [fromStation, setFromStation] = useState(null)
  const [toStation, setToStation] = useState(null)
  const [travelDate, setTravelDate] = useState(() => {
    const d = new Date(); d.setDate(d.getDate() + 1)
    return d.toISOString().slice(0, 10)
  })
  const [ticketType, setTicketType] = useState('single')
  const [trains, setTrains] = useState([])
  const [searching, setSearching] = useState(false)
  const [selectedTrain, setSelectedTrain] = useState(null)
  const [quote, setQuote] = useState(null)
  const [quoting, setQuoting] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  // 1. Cand avem plecare + sosire, cautam trenuri
  useEffect(() => {
    if (!fromStation || !toStation) { setTrains([]); setSelectedTrain(null); return }
    let alive = true
    setSearching(true); setSelectedTrain(null); setError(null)
    searchTrains(fromStation.station_id, toStation.station_id, travelDate)
      .then(r => { if (alive) setTrains(r || []) })
      .catch(e => { if (alive) setError(e.message) })
      .finally(() => { if (alive) setSearching(false) })
    return () => { alive = false }
  }, [fromStation, toStation, travelDate])

  // 2. Cand userul alege un tren -> quote live
  useEffect(() => {
    if (!selectedTrain || !fromStation || !toStation) { setQuote(null); return }
    let alive = true
    setQuoting(true)
    quoteTicket({
      train_id: selectedTrain.train_id,
      departure_station_id: fromStation.station_id,
      arrival_station_id: toStation.station_id,
      travel_date: travelDate,
      ticket_type: ticketType,
    })
      .then(q => { if (alive) setQuote(q) })
      .catch(() => { if (alive) setQuote(null) })
      .finally(() => { if (alive) setQuoting(false) })
    return () => { alive = false }
  }, [selectedTrain, fromStation, toStation, ticketType, travelDate])

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!selectedTrain) { setError('Selecteaza un tren'); return }
    setSubmitting(true); setError(null)
    try {
      const r = await buyTicket({
        train_id: selectedTrain.train_id,
        departure_station_id: fromStation.station_id,
        arrival_station_id: toStation.station_id,
        travel_date: travelDate,
        ticket_type: ticketType,
      })
      navigate('/tickets', { state: { newTicketId: r.ticket_id } })
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  const minDate = new Date().toISOString().slice(0, 10)

  return (
    <div className="container mx-auto px-4 py-8 max-w-3xl">
      <h1 className="text-3xl font-bold mb-6 text-slate-900 dark:text-slate-50">Cumpara bilet</h1>

      {error && (
        <div className="mb-4 rounded-xl border border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300 px-4 py-3 text-sm">{error}</div>
      )}

      <form onSubmit={handleSubmit} className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-700 p-6 shadow-sm space-y-5">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          <StationCombobox label="De la" value={fromStation} onChange={setFromStation} placeholder="Bucuresti Nord, Cluj-Napoca, ..." />
          <StationCombobox label="Pana la" value={toStation} onChange={setToStation} placeholder="Brasov, Sibiu, Iasi, ..." />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          <div>
            <label className="block text-sm font-semibold mb-2 text-slate-700 dark:text-slate-200">Data calatoriei</label>
            <input type="date" value={travelDate} min={minDate} onChange={(e) => setTravelDate(e.target.value)} required
              className="w-full rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 px-3 py-2" />
          </div>
          <div>
            <label className="block text-sm font-semibold mb-2 text-slate-700 dark:text-slate-200">Tip bilet</label>
            <select value={ticketType} onChange={(e) => setTicketType(e.target.value)}
              className="w-full rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 px-3 py-2">
              {Object.entries(TYPE_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </div>
        </div>

        {/* Lista trenuri */}
        {fromStation && toStation && (
          <div className="border-t border-slate-200 dark:border-slate-700 pt-5">
            <h2 className="text-sm font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-3">
              Trenuri directe ({trains.length})
            </h2>
            {searching && <div className="text-sm text-slate-500">Caut trenuri...</div>}
            {!searching && trains.length === 0 && (
              <div className="text-sm text-slate-500 p-4 rounded-xl border border-dashed border-slate-300 dark:border-slate-700">
                Nu exista tren direct intre aceste statii. Sistemul nu suporta inca conexiuni cu schimbare.
              </div>
            )}
            <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
              {trains.map(t => (
                <label key={t.train_id}
                  className={`flex items-center justify-between gap-3 p-3 rounded-xl border cursor-pointer transition
                    ${selectedTrain?.train_id === t.train_id
                      ? 'border-emerald-400 bg-emerald-50 dark:bg-emerald-900/20'
                      : 'border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800'}`}>
                  <input type="radio" name="train" className="sr-only"
                    checked={selectedTrain?.train_id === t.train_id}
                    onChange={() => setSelectedTrain(t)} />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                      {t.train_type?.toUpperCase()} {t.train_number}
                      <span className="ml-2 text-xs font-normal text-slate-500">{t.operator_name}</span>
                    </div>
                    <div className="text-xs text-slate-500 dark:text-slate-400">
                      {t.departure_time?.slice(0, 5) || '--:--'} - {t.arrival_time?.slice(0, 5) || '--:--'}
                      {t.distance_km && <span className="ml-2">- {t.distance_km.toFixed(0)} km</span>}
                    </div>
                  </div>
                </label>
              ))}
            </div>
          </div>
        )}

        {/* Preview tarif */}
        {selectedTrain && (
          <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 p-4">
            <div className="text-xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-2">Detalii tarif</div>
            {quoting && <div className="text-sm text-slate-500 animate-pulse">Calculez tariful...</div>}
            {!quoting && quote && (
              <div className="space-y-1.5 text-sm">
                <div className="flex justify-between">
                  <span className="text-slate-600 dark:text-slate-400">Distanta:</span>
                  <span className="font-mono">{quote.distance_km?.toFixed?.(1) ?? quote.distance_km} km</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-600 dark:text-slate-400">Tarif normal ({ticketType === 'return' ? 'dus-intors' : 'dus'}):</span>
                  <span className="font-mono">{quote.base_price.toFixed(2)} RON</span>
                </div>
                {quote.discount_percent > 0 && (
                  <div className="flex justify-between text-emerald-600 dark:text-emerald-400">
                    <span>Reducere student {quote.discount_percent}% (OUG 11/2024):</span>
                    <span className="font-mono">-{quote.savings.toFixed(2)} RON</span>
                  </div>
                )}
                <div className="border-t border-slate-200 dark:border-slate-700 mt-2 pt-2 flex justify-between items-baseline">
                  <span className="font-bold text-slate-900 dark:text-slate-100">Platesti:</span>
                  <span className="font-bold text-xl text-emerald-600 dark:text-emerald-400 font-mono">
                    {quote.final_price.toFixed(2)} RON
                  </span>
                </div>
              </div>
            )}
          </div>
        )}

        <div className="flex gap-3 pt-2">
          <button type="submit" disabled={submitting || !selectedTrain}
            className="flex-1 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold rounded-xl px-4 py-3 transition">
            {submitting ? 'Se proceseaza...' : 'Cumpara bilet'}
          </button>
          <Link to="/tickets" className="px-4 py-3 rounded-xl border border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800 transition">
            Biletele mele
          </Link>
        </div>
      </form>
    </div>
  )
}
