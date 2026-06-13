import { useEffect, useState, useMemo } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { rescheduleTicket, searchTrains } from '../services/api'
import SeatMap from '../components/SeatMap'
import { fmtTrainType } from '../utils/trainType'

function passengerLabel(t) {
  return (t.passenger_name || t.display_passenger_name || '').trim() || 'Tu (cumparator)'
}

export default function ReschedulePage() {
  const navigate = useNavigate()
  const location = useLocation()
  // Suporta si formatul vechi { ticket } pentru compatibilitate
  const tickets = location.state?.tickets
    || (location.state?.ticket ? [location.state.ticket] : null)

  const ref = tickets?.[0]  // biletul de referinta pentru ruta/data

  // Detectam clasa biletului original din primul loc (format "V{n}-{label}")
  // Vagon 1 = clasa 1, restul = clasa 2. Null daca biletul nu are loc selectat.
  const ticketClass = useMemo(() => {
    const seats = ref?.seats
    if (!seats?.length) return null
    const m = seats[0].match(/^V(\d+)/)
    const carNum = m ? parseInt(m[1]) : null
    return carNum === 1 ? 1 : 2
  }, [ref])

  const today = new Date().toISOString().slice(0, 10)
  const [newDate, setNewDate] = useState(ref?.travel_date || today)
  const [trains, setTrains] = useState([])
  const [searching, setSearching] = useState(false)
  const [selectedTrain, setSelectedTrain] = useState(null)
  const [selectedSeatDetails, setSelectedSeatDetails] = useState([])
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!tickets) navigate('/tickets')
  }, [tickets, navigate])

  useEffect(() => {
    if (!ref || !newDate) return
    let alive = true
    setSearching(true)
    setSelectedTrain(null)
    setSelectedSeatDetails([])
    setError(null)
    searchTrains(ref.departure_station_id, ref.arrival_station_id, newDate)
      .then(rows => {
        if (!alive) return
        // Excludem trenul curent doar daca data selectata e aceeasi cu cea originala
        // (pe alta zi, acelasi tren e o optiune valida)
        const sameDay = newDate === ref.travel_date
        const usedTrainIds = sameDay ? new Set(tickets.map(t => t.train_id)) : new Set()
        setTrains((rows || []).filter(t => !usedTrainIds.has(t.train_id)))
      })
      .catch(e => { if (alive) setError(e.message) })
      .finally(() => { if (alive) setSearching(false) })
    return () => { alive = false }
  }, [newDate, ref])

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!selectedTrain) { setError('Selectati un tren nou.'); return }
    if (selectedSeatDetails.length < tickets.length) {
      setError(`Trebuie sa selectezi ${tickets.length} loc${tickets.length > 1 ? 'uri' : ''} — câte unul per pasager.`)
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      const results = []
      for (let i = 0; i < tickets.length; i++) {
        const t = tickets[i]
        const seat = selectedSeatDetails[i]
        try {
          const result = await rescheduleTicket(t.ticket_id, {
            new_train_id: selectedTrain.train_id,
            new_travel_date: newDate,
            new_seat_ids: seat ? [seat.seat_id] : undefined,
          })
          results.push(result)
        } catch (innerErr) {
          const msg = innerErr.detail?.message || innerErr.message || ''
          // Daca biletul a fost deja reprogramat intr-o iteratie anterioara (retry),
          // sarim peste el fara sa oprim intregul grup.
          if (msg.includes('rescheduled')) continue
          throw innerErr
        }
      }
      if (results.length === 0) {
        setError('Niciunul dintre bilete nu a putut fi reprogramat.')
        setSubmitting(false)
        return
      }
      navigate('/tickets', {
        state: {
          newTicketId: results[0].new_ticket_id,
          rescheduleMsg: results.length > 1
            ? `${results.length} bilete reprogramate cu succes.`
            : `Bilet reprogramat cu succes. Bilet nou: #${results[0].new_ticket_id}.`,
        },
      })
    } catch (e) {
      setError(e.detail?.message || e.message || 'Eroare la reprogramare')
      setSubmitting(false)
    }
  }

  if (!tickets) return null

  const isMulti = tickets.length > 1

  return (
    <div className="container mx-auto px-4 py-8 max-w-3xl">
      <h1 className="text-3xl font-bold mb-6 text-slate-900 dark:text-slate-50">
        Reprogramare bilet{isMulti ? 'e' : ''}
      </h1>

      {error && (
        <div className="mb-4 rounded-xl border border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300 px-4 py-3 text-sm">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-700 p-6 shadow-sm space-y-5">

        {/* Traseu fix (readonly) */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          <div>
            <label className="block text-sm font-semibold mb-2 text-slate-700 dark:text-slate-200">
              De la
            </label>
            <div className="w-full rounded-xl border border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-700 dark:text-slate-300 px-3 py-2 text-sm">
              {ref.departure_station}
            </div>
          </div>
          <div>
            <label className="block text-sm font-semibold mb-2 text-slate-700 dark:text-slate-200">
              Până la
            </label>
            <div className="w-full rounded-xl border border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-700 dark:text-slate-300 px-3 py-2 text-sm">
              {ref.arrival_station}
            </div>
          </div>
        </div>

        {/* Data noua + bilet curent */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          <div>
            <label className="block text-sm font-semibold mb-2 text-slate-700 dark:text-slate-200">
              Data călătoriei
            </label>
            <input
              type="date"
              value={newDate}
              min={today}
              onChange={(e) => setNewDate(e.target.value)}
              className="w-full rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 px-3 py-2"
            />
          </div>
          <div>
            <label className="block text-sm font-semibold mb-2 text-slate-700 dark:text-slate-200">
              Bilet{isMulti ? 'e' : ''} curent{isMulti ? 'e' : ''}
            </label>
            <div className="w-full rounded-xl border border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-500 dark:text-slate-400 px-3 py-2 text-sm">
              {fmtTrainType(ref.train_type)} {ref.train_number} · {ref.travel_date}
              {(ref.departure_time || ref.arrival_time) && (
                <span> · {ref.departure_time?.slice(0,5)}{ref.arrival_time ? `–${ref.arrival_time.slice(0,5)}` : ''}</span>
              )}
              {isMulti && <span className="ml-1 text-xs">({tickets.length} pasageri)</span>}
            </div>
          </div>
        </div>

        {/* Pasageri (doar pentru multi-pax) */}
        {isMulti && (
          <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 p-3">
            <div className="text-xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-2">
              Pasageri reprogramați
            </div>
            <div className="space-y-1">
              {tickets.map((t, i) => (
                <div key={t.ticket_id} className="flex items-center justify-between text-sm">
                  <span className="text-slate-700 dark:text-slate-300">{passengerLabel(t)}</span>
                  {selectedSeatDetails[i] ? (
                    <span className="font-mono text-xs text-emerald-700 dark:text-emerald-400 font-semibold">
                      V{selectedSeatDetails[i].car_number}-{selectedSeatDetails[i].label}
                    </span>
                  ) : (
                    <span className="text-xs text-slate-400 dark:text-slate-500 italic">fără loc selectat</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Lista trenuri */}
        <div className="border-t border-slate-200 dark:border-slate-700 pt-5">
          <h2 className="text-sm font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-3">
            Trenuri directe ({trains.length})
          </h2>

          {searching && (
            <div className="text-sm text-slate-500">Caut trenuri...</div>
          )}

          {!searching && trains.length === 0 && (
            <div className="text-sm text-slate-500 p-3 rounded-xl border border-dashed border-slate-300 dark:border-slate-700">
              Niciun tren disponibil pe acest traseu în ziua selectată.
            </div>
          )}

          {!searching && trains.length > 0 && (
            <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
              {trains.map(t => (
                <label
                  key={t.train_id}
                  className={`flex items-center justify-between gap-3 p-3 rounded-xl border cursor-pointer transition
                    ${selectedTrain?.train_id === t.train_id
                      ? 'border-emerald-400 bg-emerald-50 dark:bg-emerald-900/20'
                      : 'border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800'
                    }`}
                >
                  <input
                    type="radio"
                    name="train"
                    className="sr-only"
                    checked={selectedTrain?.train_id === t.train_id}
                    onChange={() => { setSelectedTrain(t); setSelectedSeatDetails([]) }}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                      {fmtTrainType(t.train_type)} {t.train_number}
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
          )}
        </div>

        {/* SeatMap */}
        {selectedTrain && (
          <div className="border-t border-slate-200 dark:border-slate-700 pt-5">
            <div className="flex items-center justify-between mb-1">
              <h3 className="text-sm font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                Alege loc{isMulti ? 'uri' : ''} (obligatoriu)
              </h3>
              <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                selectedSeatDetails.length === tickets.length
                  ? 'bg-emerald-100 dark:bg-emerald-900 text-emerald-700 dark:text-emerald-300'
                  : 'bg-amber-100 dark:bg-amber-900 text-amber-700 dark:text-amber-300'
              }`}>
                {selectedSeatDetails.length}/{tickets.length} selectate
              </span>
            </div>
            {ticketClass !== null && (
              <p className="text-xs text-slate-500 dark:text-slate-400 mb-1">
                Doar locuri de <strong>clasa {ticketClass}</strong> (ca biletul original).
              </p>
            )}
            {isMulti && (
              <p className="text-xs text-slate-500 dark:text-slate-400 mb-3">
                Selectează {tickets.length} locuri — câte unul per pasager, în ordinea listei de mai sus.
              </p>
            )}
            <SeatMap
              trainId={selectedTrain.train_id}
              travelDate={newDate}
              onSelectionChange={setSelectedSeatDetails}
              maxSeats={tickets.length}
              restrictToClass={ticketClass}
            />
          </div>
        )}

        {/* Rezumat */}
        {selectedTrain && (
          <div className="border-t border-slate-200 dark:border-slate-700 pt-5">
            <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 p-4 text-sm">
              <div className="text-xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-2">
                Reprogramare selectată
              </div>
              <div className="font-semibold text-slate-900 dark:text-slate-100">
                {ref.departure_station} → {ref.arrival_station}
              </div>
              <div className="text-slate-500 dark:text-slate-400 mt-0.5">
                {fmtTrainType(selectedTrain.train_type)} {selectedTrain.train_number} · {newDate} · {selectedTrain.departure_time?.slice(0,5)}–{selectedTrain.arrival_time?.slice(0,5)}
              </div>
            </div>
          </div>
        )}

        <div className="flex gap-3 justify-end pt-2">
          <button
            type="button"
            onClick={() => navigate('/tickets')}
            disabled={submitting}
            className="px-5 py-2.5 rounded-xl border border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 font-semibold transition disabled:opacity-50"
          >
            Renunță
          </button>
          <button
            type="submit"
            disabled={!selectedTrain || submitting || selectedSeatDetails.length < tickets.length}
            className="px-5 py-2.5 rounded-xl bg-amber-600 hover:bg-amber-700 text-white font-semibold disabled:opacity-50 transition"
          >
            {submitting
              ? 'Se reprogramează...'
              : isMulti
                ? `Confirmă reprogramarea (${tickets.length} bilete)`
                : 'Confirmă reprogramarea'}
          </button>
        </div>
      </form>
    </div>
  )
}
