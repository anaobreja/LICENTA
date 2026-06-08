/**
 * SeatMap — vizualizare interactiva a vagoanelor + locurilor unui tren.
 *
 * Props:
 *   trainId      (number) — id-ul trenului
 *   travelDate   (string YYYY-MM-DD)
 *   onSelectionChange (function) — primeste array de seat_ids selectate
 *   maxSeats     (number, default 4) — limita selectie simultana
 *
 * Comportament:
 *   - La mount: GET /trains/{id}/seats?travel_date=... -> layout-ul.
 *   - Polling la 5s pentru actualizare live (alti useri ocupa/elibereaza).
 *   - Click pe loc liber: POST /seats/hold -> devine "mine_held" (galben).
 *   - Click pe loc deja "mine_held": POST /seats/release -> redevine "free".
 *   - Click pe loc "sold" sau "held" (de alt user): ignorat + toast.
 *
 * Status -> culoare:
 *   free      — alb / gri deschis (selectabil)
 *   mine_held — galben (selectia curenta a userului)
 *   mine_sold — albastru (cumparat de mine in trecut)
 *   sold      — rosu / inchis (ocupat de alt user)
 *   held      — portocaliu (rezervat temporar de alt user)
 */
import { useEffect, useState, useCallback, useRef } from 'react'
import { getTrainSeats, holdSeat, releaseSeat } from '../services/api'

const STATUS_STYLES = {
  free:       'bg-white dark:bg-slate-700 text-slate-700 dark:text-slate-200 border-slate-300 dark:border-slate-600 hover:bg-emerald-50 dark:hover:bg-emerald-900/30 hover:border-emerald-400 cursor-pointer',
  mine_held:  'bg-yellow-300 text-yellow-900 border-yellow-500 ring-2 ring-yellow-400 cursor-pointer',
  mine_sold:  'bg-blue-500 text-white border-blue-600 cursor-not-allowed',
  sold:       'bg-red-400 text-white border-red-500 cursor-not-allowed',
  held:       'bg-orange-300 text-orange-900 border-orange-500 cursor-not-allowed',
}

const STATUS_LABEL = {
  free: 'liber',
  mine_held: 'al tau (hold 5 min)',
  mine_sold: 'cumparat de tine',
  sold: 'ocupat',
  held: 'rezervat de altcineva',
}

function Seat({ seat, onClick, disabled }) {
  const style = STATUS_STYLES[seat.status] || STATUS_STYLES.free
  const isClickable = seat.status === 'free' || seat.status === 'mine_held'
  return (
    <button
      type="button"
      disabled={disabled || !isClickable}
      onClick={() => isClickable && onClick(seat)}
      title={`Loc ${seat.label} — ${STATUS_LABEL[seat.status]}${seat.is_window ? ' (geam)' : ''}`}
      className={`w-9 h-9 text-xs font-semibold rounded-md border-2 transition ${style} ${disabled ? 'opacity-60' : ''}`}
    >
      {seat.label}
    </button>
  )
}

function CarLayout({ car, onSeatClick, disabled }) {
  // Grupez locurile per rand (1..15), cu un culoar intre B si C.
  const rows = {}
  for (const s of car.seats) {
    if (!rows[s.row]) rows[s.row] = {}
    rows[s.row][s.letter] = s
  }
  const sortedRows = Object.keys(rows).sort((a, b) => Number(a) - Number(b))

  return (
    <div className="border-2 border-slate-300 dark:border-slate-700 rounded-2xl p-4 bg-slate-50 dark:bg-slate-800/50 inline-block">
      <div className="flex items-center justify-between mb-3">
        <span className="font-bold text-sm">Vagon {car.car_number}</span>
        <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${
          car.car_class === 1
            ? 'bg-purple-100 dark:bg-purple-900 text-purple-700 dark:text-purple-200'
            : 'bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-300'
        }`}>
          Clasa {car.car_class}
        </span>
      </div>

      {/* Layout 2+2: A B | culoar | C D */}
      <div className="flex flex-col gap-1">
        {sortedRows.map((rowNum) => {
          const r = rows[rowNum]
          return (
            <div key={rowNum} className="flex items-center gap-1">
              <span className="w-5 text-xs text-slate-500 text-right">{rowNum}</span>
              {['A', 'B'].map((l) =>
                r[l] ? <Seat key={l} seat={r[l]} onClick={onSeatClick} disabled={disabled} /> : <div key={l} className="w-9 h-9" />
              )}
              <div className="w-3 border-l-2 border-dashed border-slate-300 dark:border-slate-600 h-9 mx-1" />
              {['C', 'D'].map((l) =>
                r[l] ? <Seat key={l} seat={r[l]} onClick={onSeatClick} disabled={disabled} /> : <div key={l} className="w-9 h-9" />
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function Legend() {
  return (
    <div className="flex flex-wrap gap-3 text-xs items-center">
      <span className="flex items-center gap-1.5"><span className="w-4 h-4 rounded border-2 border-slate-300 bg-white inline-block"/> liber</span>
      <span className="flex items-center gap-1.5"><span className="w-4 h-4 rounded border-2 border-yellow-500 bg-yellow-300 inline-block"/> selectia ta</span>
      <span className="flex items-center gap-1.5"><span className="w-4 h-4 rounded border-2 border-blue-600 bg-blue-500 inline-block"/> deja cumparat de tine</span>
      <span className="flex items-center gap-1.5"><span className="w-4 h-4 rounded border-2 border-red-500 bg-red-400 inline-block"/> ocupat</span>
      <span className="flex items-center gap-1.5"><span className="w-4 h-4 rounded border-2 border-orange-500 bg-orange-300 inline-block"/> hold altui user</span>
    </div>
  )
}

export default function SeatMap({ trainId, travelDate, onSelectionChange, maxSeats = 4 }) {
  const [layout, setLayout] = useState(null)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [pendingSeatId, setPendingSeatId] = useState(null)
  const pollRef = useRef(null)

  const loadLayout = useCallback(async () => {
    try {
      const data = await getTrainSeats(trainId, travelDate)
      setLayout(data)
      setErr('')
      // Notifica parent de seat-urile selectate (mine_held)
      const mineHeld = []
      for (const car of (data.cars || [])) {
        for (const s of (car.seats || [])) {
          if (s.status === 'mine_held') mineHeld.push(s.seat_id)
        }
      }
      onSelectionChange?.(mineHeld)
    } catch (e) {
      setErr(e.message || 'Nu am putut incarca harta locurilor')
    } finally {
      setLoading(false)
    }
  }, [trainId, travelDate, onSelectionChange])

  // Mount + polling 5s
  useEffect(() => {
    loadLayout()
    pollRef.current = setInterval(loadLayout, 5000)
    return () => clearInterval(pollRef.current)
  }, [loadLayout])

  const handleSeatClick = async (seat) => {
    if (busy) return
    setBusy(true)
    setPendingSeatId(seat.seat_id)
    try {
      if (seat.status === 'free') {
        // Verifica limita
        const currentlySelected = (layout.cars || [])
          .flatMap(c => c.seats)
          .filter(s => s.status === 'mine_held')
        if (currentlySelected.length >= maxSeats) {
          setErr(`Poti selecta maxim ${maxSeats} locuri simultan.`)
          return
        }
        await holdSeat({ train_id: trainId, seat_id: seat.seat_id, travel_date: travelDate })
      } else if (seat.status === 'mine_held') {
        await releaseSeat({ seat_id: seat.seat_id, travel_date: travelDate })
      }
      await loadLayout()
    } catch (e) {
      const msg = e.detail?.message || e.message || 'Eroare la rezervare'
      setErr(msg)
    } finally {
      setPendingSeatId(null)
      setBusy(false)
    }
  }

  if (loading) {
    return <div className="text-sm text-slate-500 py-4">Se incarca harta locurilor...</div>
  }
  if (err && !layout) {
    return <div className="text-sm text-red-600 py-4">{err}</div>
  }
  if (!layout) return null

  const { summary, cars } = layout

  return (
    <div className="space-y-4">
      {/* Header + summary */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="font-bold text-sm">
            Tren {layout.train.train_number} ({layout.train.train_type})
            {' '}— {layout.train.origin} → {layout.train.destination}
          </div>
          <div className="text-xs text-slate-500 mt-0.5">
            Plecare {layout.train.departure_time} · Sosire {layout.train.arrival_time} · {layout.travel_date}
          </div>
        </div>
        <div className="text-xs text-slate-500">
          <span className="font-semibold">{summary.free}</span> libere · {summary.sold} ocupate
          · {summary.held} hold-uri active
          {summary.mine > 0 && (
            <span className="ml-2 text-yellow-700 dark:text-yellow-400 font-semibold">
              Tu: {summary.mine}
            </span>
          )}
        </div>
      </div>

      <Legend />

      {err && (
        <div className="bg-red-50 dark:bg-red-900/30 border border-red-300 dark:border-red-800 rounded-lg p-2 text-sm text-red-700 dark:text-red-300">
          {err}
        </div>
      )}

      {/* Vagoane (scroll orizontal pe mobile) */}
      <div className="overflow-x-auto pb-4">
        <div className="inline-flex gap-4">
          {cars.map((car) => (
            <CarLayout
              key={car.car_number}
              car={car}
              onSeatClick={handleSeatClick}
              disabled={busy && pendingSeatId !== null}
            />
          ))}
        </div>
      </div>

      <p className="text-xs text-slate-500 italic">
        Locurile selectate sunt rezervate pentru tine timp de 5 minute. Daca nu confirmi
        cumpararea in acest timp, vor reveni la statusul liber.
      </p>
    </div>
  )
}
