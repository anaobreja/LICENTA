import { useEffect, useState, useCallback } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { getMyTickets, cancelTicket, rescheduleTicket, searchTrains, getTrainSeats } from '../services/api'
import SeatMap from '../components/SeatMap'

const fmtDate = (s) => {
  if (!s) return ''
  try {
    const d = new Date(s)
    return d.toLocaleString('ro-RO', { dateStyle: 'medium', timeStyle: 'short' })
  } catch { return s }
}

const STATUS_META = {
  active:      { label: 'Activ',        cls: 'bg-emerald-100 dark:bg-emerald-900 text-emerald-700 dark:text-emerald-200' },
  used:        { label: 'Folosit',      cls: 'bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-200' },
  expired:     { label: 'Expirat',      cls: 'bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200' },
  cancelled:   { label: 'Anulat',       cls: 'bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-200' },
  rescheduled: { label: 'Reprogramat',  cls: 'bg-amber-100 dark:bg-amber-900 text-amber-700 dark:text-amber-200' },
  refunded:    { label: 'Returnat',     cls: 'bg-purple-100 dark:bg-purple-900 text-purple-700 dark:text-purple-200' },
}

// ----------------------------------------------------------------------------
// CancelModal — confirma anularea, arata refund estimat
// ----------------------------------------------------------------------------
function CancelModal({ ticket, onClose, onSuccess }) {
  const [confirming, setConfirming] = useState(false)
  const [error, setError] = useState('')

  // Estimam refund-ul client-side ca user-ul sa vada inainte de click.
  // (Backend-ul recalculeaza si decide oricum.)
  const departureIso = ticket?.travel_date
    ? `${ticket.travel_date}T${ticket.departure_time || '00:00'}:00Z`
    : null
  const departureMs = departureIso ? Date.parse(departureIso) : NaN
  const hoursUntilDeparture = isNaN(departureMs)
    ? null
    : (departureMs - Date.now()) / 3_600_000

  let estimatedTier = 'unknown'
  let estimatedRefund = null
  if (hoursUntilDeparture !== null && ticket.price != null) {
    if (hoursUntilDeparture >= 24)     { estimatedTier = 'full'; estimatedRefund = ticket.price }
    else if (hoursUntilDeparture > 0)  { estimatedTier = 'half'; estimatedRefund = ticket.price * 0.5 }
    else                                { estimatedTier = 'none'; estimatedRefund = 0 }
  }

  const tierMsg = {
    full: 'Trenul pleaca peste mai mult de 24h -> refund 100%.',
    half: 'Trenul pleaca in mai putin de 24h -> refund 50% conform CFR.',
    none: 'Trenul a plecat sau e deja folosit -> NU se acorda refund.',
    unknown: 'Nu am putut estima refund-ul. Backend-ul va calcula exact la confirmare.',
  }[estimatedTier]

  const handleConfirm = async () => {
    setConfirming(true)
    setError('')
    try {
      const result = await cancelTicket(ticket.ticket_id)
      onSuccess(result)
    } catch (e) {
      setError(e.detail?.message || e.message || 'Eroare la anulare')
    } finally {
      setConfirming(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="bg-white dark:bg-slate-900 rounded-2xl shadow-2xl max-w-md w-full p-6 space-y-4">
        <h2 className="text-xl font-bold text-slate-900 dark:text-slate-100">
          Anulare bilet
        </h2>

        <div className="text-sm text-slate-600 dark:text-slate-300 space-y-1">
          <p>Sunteti pe cale sa anulati biletul:</p>
          <div className="bg-slate-50 dark:bg-slate-800 rounded-lg p-3 text-xs space-y-0.5">
            <div>Tren <strong>{ticket.train_number || `#${ticket.train_id}`}</strong></div>
            <div>Data: <strong>{ticket.travel_date}</strong></div>
            <div>Pret platit: <strong>{Number(ticket.price).toFixed(2)} RON</strong></div>
          </div>
        </div>

        <div className={`rounded-lg p-3 text-sm border ${
          estimatedTier === 'full' ? 'bg-emerald-50 dark:bg-emerald-900/30 border-emerald-300 dark:border-emerald-700 text-emerald-900 dark:text-emerald-100' :
          estimatedTier === 'half' ? 'bg-amber-50 dark:bg-amber-900/30 border-amber-300 dark:border-amber-700 text-amber-900 dark:text-amber-100' :
          'bg-red-50 dark:bg-red-900/30 border-red-300 dark:border-red-700 text-red-900 dark:text-red-100'
        }`}>
          <div className="font-semibold mb-1">{tierMsg}</div>
          {estimatedRefund !== null && (
            <div>Refund estimat: <strong>{estimatedRefund.toFixed(2)} RON</strong></div>
          )}
        </div>

        {error && (
          <div className="bg-red-50 dark:bg-red-900/30 border border-red-300 dark:border-red-800 text-red-700 dark:text-red-300 text-sm rounded-lg p-2">
            {error}
          </div>
        )}

        <div className="flex gap-2 justify-end">
          <button
            onClick={onClose}
            disabled={confirming}
            className="px-4 py-2 rounded-xl border border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition"
          >
            Renunta
          </button>
          <button
            onClick={handleConfirm}
            disabled={confirming || estimatedTier === 'none'}
            className="px-4 py-2 rounded-xl bg-red-600 hover:bg-red-700 text-white font-semibold disabled:opacity-50"
          >
            {confirming ? 'Se anuleaza...' : 'Confirma anularea'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ----------------------------------------------------------------------------
// RescheduleModal — alege alt tren pe ACELASI traseu + (optional) alte locuri
// ----------------------------------------------------------------------------
function RescheduleModal({ ticket, onClose, onSuccess }) {
  const [newDate, setNewDate] = useState(ticket.travel_date)
  const [candidates, setCandidates] = useState([])
  const [loadingCandidates, setLoadingCandidates] = useState(false)
  const [selectedTrain, setSelectedTrain] = useState(null)
  const [seatIds, setSeatIds] = useState([])
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  // La schimbarea datei, cautam trenuri pe acelasi traseu
  useEffect(() => {
    if (!newDate || !ticket.departure_station_id || !ticket.arrival_station_id) return
    setLoadingCandidates(true)
    searchTrains(ticket.departure_station_id, ticket.arrival_station_id, newDate)
      .then(rows => {
        // Excludem trenul curent (e acelasi bilet, n-are sens sa-l reprogramezi pe el)
        const filtered = (rows || []).filter(t => t.train_id !== ticket.train_id)
        setCandidates(filtered)
      })
      .catch(e => setError(e.message))
      .finally(() => setLoadingCandidates(false))
  }, [newDate, ticket])

  const handleConfirm = async () => {
    if (!selectedTrain) {
      setError('Selectati un tren nou.')
      return
    }
    setSubmitting(true)
    setError('')
    try {
      const result = await rescheduleTicket(ticket.ticket_id, {
        new_train_id: selectedTrain.train_id,
        new_travel_date: newDate,
        new_seat_ids: seatIds.length > 0 ? seatIds : undefined,
      })
      onSuccess(result)
    } catch (e) {
      setError(e.detail?.message || e.message || 'Eroare la reprogramare')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 overflow-y-auto">
      <div className="bg-white dark:bg-slate-900 rounded-2xl shadow-2xl max-w-4xl w-full p-6 my-8 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-bold text-slate-900 dark:text-slate-100">
            Reprogramare bilet
          </h2>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 text-xl">x</button>
        </div>

        <div className="text-xs text-slate-500">
          Reprogramare permisa doar pe acelasi traseu. Diferenta de pret nu se restituie.
        </div>

        <div className="bg-slate-50 dark:bg-slate-800 rounded-lg p-3 text-sm">
          <div><strong>Traseu:</strong> {ticket.departure_station || `Statia ${ticket.departure_station_id}`} -> {ticket.arrival_station || `Statia ${ticket.arrival_station_id}`}</div>
          <div><strong>Bilet curent:</strong> tren {ticket.train_number || `#${ticket.train_id}`} pe {ticket.travel_date}</div>
        </div>

        <div>
          <label className="block text-sm font-semibold mb-1">Data noua</label>
          <input
            type="date"
            value={newDate}
            onChange={(e) => { setNewDate(e.target.value); setSelectedTrain(null); setSeatIds([]) }}
            min={new Date().toISOString().slice(0, 10)}
            className="rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2"
          />
        </div>

        <div>
          <label className="block text-sm font-semibold mb-1">Trenuri disponibile pe acest traseu</label>
          {loadingCandidates && <div className="text-xs text-slate-500">Se cauta...</div>}
          {!loadingCandidates && candidates.length === 0 && (
            <div className="text-xs text-slate-500 italic">Niciun tren disponibil pe traseu in aceasta zi.</div>
          )}
          {candidates.length > 0 && (
            <div className="space-y-1 max-h-48 overflow-y-auto">
              {candidates.map((t) => (
                <label
                  key={t.train_id}
                  className={`flex items-center gap-3 p-2 rounded-lg border cursor-pointer ${
                    selectedTrain?.train_id === t.train_id
                      ? 'border-emerald-500 bg-emerald-50 dark:bg-emerald-900/30'
                      : 'border-slate-300 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800'
                  }`}
                >
                  <input
                    type="radio"
                    name="new-train"
                    checked={selectedTrain?.train_id === t.train_id}
                    onChange={() => { setSelectedTrain(t); setSeatIds([]) }}
                  />
                  <span className="font-semibold">{t.train_number}</span>
                  <span className="text-xs text-slate-500">({t.train_type || 'tren'})</span>
                  <span className="text-xs ml-auto">{t.departure_time} -> {t.arrival_time}</span>
                </label>
              ))}
            </div>
          )}
        </div>

        {selectedTrain && (
          <div className="border-t border-slate-200 dark:border-slate-700 pt-4">
            <div className="text-sm font-semibold mb-2">Alege locuri (optional)</div>
            <SeatMap
              trainId={selectedTrain.train_id}
              travelDate={newDate}
              onSelectionChange={setSeatIds}
              maxSeats={2}
            />
          </div>
        )}

        {error && (
          <div className="bg-red-50 dark:bg-red-900/30 border border-red-300 dark:border-red-800 text-red-700 dark:text-red-300 text-sm rounded-lg p-2">
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
            onClick={handleConfirm}
            disabled={submitting || !selectedTrain}
            className="px-4 py-2 rounded-xl bg-amber-600 hover:bg-amber-700 text-white font-semibold disabled:opacity-50"
          >
            {submitting ? 'Se reprogrameaza...' : 'Confirma reprogramarea'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ----------------------------------------------------------------------------
// TicketCard
// ----------------------------------------------------------------------------
function TicketCard({ t, highlight, onCancel, onReschedule }) {
  const status = STATUS_META[t.ticket_status] || STATUS_META.active
  const canModify = t.ticket_status === 'active'

  return (
    <div className={`rounded-2xl border p-4 transition ${
      highlight
        ? 'border-emerald-500 bg-emerald-50 dark:bg-emerald-900/30 ring-2 ring-emerald-300'
        : 'border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800'
    }`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-bold text-slate-900 dark:text-slate-100">
            Tren {t.train_number || `#${t.train_id}`}
          </div>
          <div className="text-xs text-slate-500 mt-0.5">
            {t.departure_station || `St. ${t.departure_station_id}`}
            {' -> '}
            {t.arrival_station || `St. ${t.arrival_station_id}`}
          </div>
        </div>
        <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${status.cls}`}>
          {status.label}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2 mt-3 text-xs">
        <div>
          <div className="text-slate-500">Data calatorie</div>
          <div className="font-semibold">{t.travel_date}</div>
        </div>
        <div>
          <div className="text-slate-500">Pret</div>
          <div className="font-semibold">{Number(t.price || 0).toFixed(2)} RON</div>
        </div>
        {t.ticket_type && (
          <div>
            <div className="text-slate-500">Tip</div>
            <div className="font-semibold">{t.ticket_type === 'return' ? 'Dus-intors' : 'Simplu'}</div>
          </div>
        )}
        {t.seats && t.seats.length > 0 && (
          <div>
            <div className="text-slate-500">Locuri</div>
            <div className="font-semibold">{t.seats.join(', ')}</div>
          </div>
        )}
        {t.cancel_refund_amount != null && (
          <div className="col-span-2">
            <div className="text-slate-500">Refund acordat</div>
            <div className="font-semibold text-emerald-600 dark:text-emerald-400">
              {Number(t.cancel_refund_amount).toFixed(2)} RON
            </div>
          </div>
        )}
      </div>

      {canModify && (
        <div className="flex gap-2 mt-3 pt-3 border-t border-slate-200 dark:border-slate-700">
          <button
            onClick={() => onReschedule(t)}
            className="flex-1 px-3 py-1.5 rounded-lg text-xs font-semibold border border-amber-300 dark:border-amber-700 text-amber-700 dark:text-amber-300 hover:bg-amber-50 dark:hover:bg-amber-900/30"
          >
            Reprogramare
          </button>
          <button
            onClick={() => onCancel(t)}
            className="flex-1 px-3 py-1.5 rounded-lg text-xs font-semibold border border-red-300 dark:border-red-700 text-red-700 dark:text-red-300 hover:bg-red-50 dark:hover:bg-red-900/30"
          >
            Anulare
          </button>
        </div>
      )}
    </div>
  )
}

// ----------------------------------------------------------------------------
// MyTickets page
// ----------------------------------------------------------------------------
export default function MyTickets() {
  const [tickets, setTickets] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [toast, setToast] = useState(null)
  const [cancelTarget, setCancelTarget] = useState(null)
  const [rescheduleTarget, setRescheduleTarget] = useState(null)

  const location = useLocation()
  const highlightId = location.state?.newTicketId

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const rows = await getMyTickets()
      setTickets(rows || [])
      setError('')
    } catch (e) {
      setError(e.message || 'Eroare la incarcare')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const handleCancelSuccess = (result) => {
    setCancelTarget(null)
    setToast({
      kind: 'success',
      msg: `Bilet anulat. Refund: ${Number(result.refund_amount).toFixed(2)} RON (${result.refund_tier === 'full' ? '100%' : result.refund_tier === 'half' ? '50%' : '0%'}).`,
    })
    refresh()
  }

  const handleRescheduleSuccess = (result) => {
    setRescheduleTarget(null)
    setToast({
      kind: 'success',
      msg: `Bilet reprogramat. Bilet nou: #${result.new_ticket_id}.`,
    })
    refresh()
  }

  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), 5000)
    return () => clearTimeout(t)
  }, [toast])

  return (
    <div className="container mx-auto px-4 py-6 max-w-4xl">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Biletele mele</h1>
        <Link
          to="/buy-ticket"
          className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-semibold"
        >
          Cumpara bilet nou
        </Link>
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

      {!loading && tickets.length === 0 && (
        <div className="bg-slate-50 dark:bg-slate-800 rounded-2xl p-6 text-center text-slate-500">
          Nu ai cumparat inca niciun bilet. <Link to="/buy-ticket" className="text-emerald-600 underline">Cumpara primul</Link>.
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        {tickets.map((t) => (
          <TicketCard
            key={t.ticket_id}
            t={t}
            highlight={String(t.ticket_id) === String(highlightId)}
            onCancel={setCancelTarget}
            onReschedule={setRescheduleTarget}
          />
        ))}
      </div>

      {cancelTarget && (
        <CancelModal
          ticket={cancelTarget}
          onClose={() => setCancelTarget(null)}
          onSuccess={handleCancelSuccess}
        />
      )}

      {rescheduleTarget && (
        <RescheduleModal
          ticket={rescheduleTarget}
          onClose={() => setRescheduleTarget(null)}
          onSuccess={handleRescheduleSuccess}
        />
      )}
    </div>
  )
}
