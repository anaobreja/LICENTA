/**
 * Combobox cu autocomplete pentru stații de tren.
 * Folosit în BuyTicket, Documents, AgentDashboard etc.
 *
 * Props:
 *   - label: string afișat deasupra input-ului
 *   - value: { station_id, name, city, code } sau null
 *   - onChange: callback(station | null)
 *   - placeholder: text pentru input gol
 */
import { useEffect, useState } from 'react'
import { searchStations } from '../services/api'

export default function StationCombobox({ label, value, onChange, placeholder }) {
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
      {label && (
        <label className="block text-sm font-semibold mb-2 text-slate-700 dark:text-slate-200">{label}</label>
      )}
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
