import { useEffect, useState, useCallback } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { getMyTickets, cancelTicket } from '../services/api'
import { fmtTrainType } from '../utils/trainType'

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
// Categorisare bilete in tab-uri: Active / Onorate / Anulate
// ----------------------------------------------------------------------------
// - active:    status='active' si travel_date >= azi
//              (biletele reprogramate sunt deja 'active' pe noul ID -> aici)
// - completed: status in {used, expired} sau active cu travel_date < azi
//              (backend-ul face oricum lazy expire la GET /tickets/my, dar tinem
//               si fallback-ul client-side pentru afisare consistenta)
// - cancelled: status in {cancelled, refunded, rescheduled}
//              (biletul VECHI dupa reprogramare ramane 'rescheduled' -> aici)
function categorizeTicket(t) {
  const status = t?.ticket_status
  if (status === 'cancelled' || status === 'refunded' || status === 'rescheduled') {
    return 'cancelled'
  }
  if (status === 'used' || status === 'expired') {
    return 'completed'
  }
  if (status === 'active') {
    // travel_date vine ca string 'YYYY-MM-DD' din backend
    const travelDate = t.travel_date ? new Date(t.travel_date + 'T23:59:59') : null
    if (travelDate && travelDate < new Date()) {
      return 'completed'
    }
    return 'active'
  }
  // Default: orice altceva e considerat "completed" ca sa nu polueze tab-ul Active
  return 'completed'
}

// Pentru o calatorie multi-leg, categoria = a primului leg neonoarat.
// Daca toate leg-urile sunt onorate (used/expired) -> completed.
// Daca toate sunt anulate -> cancelled. Daca cel putin unul e activ -> active.
function categorizeEntry(entry) {
  if (entry.kind === 'single') return categorizeTicket(entry.ticket)
  if (entry.kind === 'ticket_journey') return categorizeTicket(entry.ticket)
  const items = entry.kind === 'multi_pax' ? entry.passengers : entry.legs
  const cats = items.map(categorizeTicket)
  if (cats.includes('active')) return 'active'
  if (cats.every((c) => c === 'cancelled')) return 'cancelled'
  return 'completed'
}

const TABS = [
  { id: 'active',    label: 'Active',  emptyMsg: 'Nu ai nicio calatorie activa in acest moment.' },
  { id: 'completed', label: 'Onorate', emptyMsg: 'Nu ai inca nicio calatorie onorata.' },
  { id: 'cancelled', label: 'Anulate', emptyMsg: 'Nu ai bilete anulate sau reprogramate.' },
]

// ----------------------------------------------------------------------------
// Helper: parseaza un string seat din formatul backend 'V2-15A' -> {car: 2, seat: '15A'}
// ----------------------------------------------------------------------------
// Backend-ul trimite locurile ca array de string-uri concatenate: ['V2-15A'].
// Pentru UI le impartim in vagon (numar) si loc (numar+litera).
// Returneaza null pentru seat-uri fara format valid (defensiv).
function parseSeat(seatStr) {
  if (!seatStr || typeof seatStr !== 'string') return null
  // Formatul standard: 'V<n>-<seat>' ex: 'V2-15A'.
  const m = seatStr.match(/^V(\d+)[-_]?(.+)$/i)
  if (m) return { car: m[1], seat: m[2] }
  // Fallback: nu putem extrage vagonul -> consideram totul ca 'seat'.
  return { car: '?', seat: seatStr }
}

// Numele pasagerului afișat pe bilet. Backend-ul intoarce passenger_name
// (cand cumperi pentru altcineva) sau display_passenger_name (numele cumparatorului).
// Cerinta UX: numele apare INTOTDEAUNA — conductorul trebuie sa stie pe cine
// sa verifice. Fara fallback la "—".
function ticketPassengerName(t) {
  const name = (t?.passenger_name || t?.display_passenger_name || '').trim()
  return name || 'Pasager'
}

// Eticheta pentru reducerea aplicata pe bilet.
//  - 100% + uses_subscription_id  -> "Acoperit de abonament"
//  - >0% fara subscription        -> "Reducere student X%"
//  - 0%                           -> null (nu afisam nimic)
function discountLabel(t) {
  const pct = Number(t?.discount_applied || 0)
  if (t?.uses_subscription_id && pct >= 99) return 'Acoperit de abonament'
  if (pct > 0) return `Reducere student ${Math.round(pct)}%`
  return null
}

// Format pret cu max 2 zecimale + suffix RON. Suporta 0.
function fmtRON(v) {
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  return `${n.toFixed(2)} RON`
}

// ----------------------------------------------------------------------------
// CancelModal — confirma anularea, arata refund estimat
// ----------------------------------------------------------------------------
function CancelModal({ ticket, onClose, onSuccess }) {
  const [confirming, setConfirming] = useState(false)
  const [error, setError] = useState('')

  // Acceptam un singur bilet SAU un array (grup multi-pax)
  const tickets = Array.isArray(ticket) ? ticket : [ticket]
  const primary = tickets[0]
  const isGroup = tickets.length > 1

  const isAlreadyInactive = tickets.every(
    (t) => t?.ticket_status && ['cancelled', 'refunded'].includes(t.ticket_status)
  )

  // Refund estimat pe primul bilet (toate au acelasi tren/data)
  const departureIso = primary?.travel_date
    ? `${primary.travel_date}T${primary.departure_time || '00:00'}:00Z`
    : null
  const departureMs = departureIso ? Date.parse(departureIso) : NaN
  const hoursUntilDeparture = isNaN(departureMs)
    ? null
    : (departureMs - Date.now()) / 3_600_000

  const totalPrice = tickets.reduce((s, t) => s + Number(t?.price || 0), 0)

  let estimatedTier = 'unknown'
  let estimatedRefund = null
  if (hoursUntilDeparture !== null) {
    if (hoursUntilDeparture >= 24)     { estimatedTier = 'full'; estimatedRefund = totalPrice }
    else if (hoursUntilDeparture > 0)  { estimatedTier = 'half'; estimatedRefund = totalPrice * 0.5 }
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
      let lastResult = null
      for (const t of tickets) {
        try {
          lastResult = await cancelTicket(t.ticket_id)
        } catch (e) {
          // Sarim peste biletele deja anulate
          if (e.detail?.error === 'invalid_status') continue
          throw e
        }
      }
      onSuccess(lastResult)
    } catch (e) {
      setError(e.detail?.message || e.message || 'Eroare la anulare')
    } finally {
      setConfirming(false)
    }
  }

  const anyRescheduled = tickets.some((t) => t?.ticket_status === 'rescheduled')

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="bg-white dark:bg-slate-900 rounded-2xl shadow-2xl max-w-md w-full p-6 space-y-4">
        <h2 className="text-xl font-bold text-slate-900 dark:text-slate-100">
          Anulare {isGroup ? `${tickets.length} bilete` : 'bilet'}
        </h2>

        {isAlreadyInactive ? (
          <div className="bg-amber-50 dark:bg-amber-900/30 border border-amber-300 dark:border-amber-700 rounded-lg p-4 text-sm text-amber-800 dark:text-amber-200">
            {isGroup ? 'Aceste bilete sunt deja anulate.' : 'Acest bilet este deja anulat.'}
          </div>
        ) : (
          <>
            {anyRescheduled && (
              <div className="bg-amber-50 dark:bg-amber-900/30 border border-amber-300 dark:border-amber-700 rounded-lg p-3 text-xs text-amber-800 dark:text-amber-200">
                {isGroup ? 'Unele bilete au fost' : 'Acest bilet a fost'} <strong>reprogramate</strong>. Anularea returnează banii pentru rezervarea originală.
              </div>
            )}
            <div className="text-sm text-slate-600 dark:text-slate-300 space-y-1">
              <p>Sunteti pe cale sa anulati {isGroup ? `${tickets.length} bilete` : 'biletul'}:</p>
              <div className="bg-slate-50 dark:bg-slate-800 rounded-lg p-3 text-xs space-y-0.5">
                <div>Tren <strong>{primary.train_number || `#${primary.train_id}`}</strong></div>
                <div>Data: <strong>{primary.travel_date}</strong></div>
                <div>Pret total: <strong>{totalPrice.toFixed(2)} RON</strong></div>
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
          </>
        )}

        <div className="flex gap-2 justify-end">
          <button
            onClick={onClose}
            disabled={confirming}
            className="px-4 py-2 rounded-xl border border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition"
          >
            {isAlreadyInactive ? 'Inchide' : 'Renunta'}
          </button>
          {!isAlreadyInactive && (
            <button
              onClick={handleConfirm}
              disabled={confirming || estimatedTier === 'none'}
              className="px-4 py-2 rounded-xl bg-red-600 hover:bg-red-700 text-white font-semibold disabled:opacity-50"
            >
              {confirming ? 'Se anuleaza...' : 'Confirma anularea'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}


// ----------------------------------------------------------------------------
// Grupare bilete in calatorii multi-leg
// ----------------------------------------------------------------------------
function groupTicketsIntoJourneys(tickets) {
  // Returneaza o lista mixta de:
  //   { kind: 'single',    ticket }
  //   { kind: 'journey',   journey_group_id, legs: [...] }
  //   { kind: 'multi_pax', purchase_key, passengers: [...] }
  // Biletele cumparate impreuna (acelasi tren + data + purchase_time exact)
  // sunt grupate ca 'multi_pax'. PostgreSQL returneaza NOW() identic pentru
  // toate inserturile dintr-o tranzactie, deci purchase_time e identic.
  if (!Array.isArray(tickets)) return []

  // Pas 1: colecteaza grupurile potentiale multi-pax
  const paxMap = new Map()
  for (const t of tickets) {
    if (t.journey_group_id && (t.total_legs || 1) > 1) continue
    const pkey = t.purchase_time
      ? `${t.train_id}|${t.travel_date}|${t.purchase_time}`
      : null
    if (!pkey) continue
    if (!paxMap.has(pkey)) paxMap.set(pkey, [])
    paxMap.get(pkey).push(t)
  }

  // Pas 2: construieste rezultatul pastrand ordinea originala
  const journeyGroups = new Map()
  const usedIds = new Set()
  const result = []

  for (const t of tickets) {
    if (usedIds.has(t.ticket_id)) continue

    // Bilet nou tip journey (cumparat prin /tickets/buy-journey)
    // Are `legs` array atasat din backend cu segmentele individuale.
    if (Array.isArray(t.legs) && t.legs.length > 1) {
      result.push({ kind: 'ticket_journey', ticket: t, legs: t.legs })
      usedIds.add(t.ticket_id)
      continue
    }

    const gid = t.journey_group_id
    if (gid && (t.total_legs || 1) > 1) {
      if (!journeyGroups.has(gid)) {
        const entry = { kind: 'journey', journey_group_id: gid, legs: [] }
        journeyGroups.set(gid, entry)
        result.push(entry)
      }
      journeyGroups.get(gid).legs.push(t)
      usedIds.add(t.ticket_id)
      continue
    }

    const pkey = t.purchase_time
      ? `${t.train_id}|${t.travel_date}|${t.purchase_time}`
      : null
    const group = pkey ? paxMap.get(pkey) : null
    if (group && group.length > 1) {
      result.push({ kind: 'multi_pax', purchase_key: pkey, passengers: group })
      group.forEach(g => usedIds.add(g.ticket_id))
      continue
    }

    result.push({ kind: 'single', ticket: t })
    usedIds.add(t.ticket_id)
  }

  for (const entry of journeyGroups.values()) {
    entry.legs.sort((a, b) => (a.leg_index ?? 0) - (b.leg_index ?? 0))
  }
  return result
}

function formatTransferMinutes(mins) {
  if (mins == null) return ''
  if (mins < 60) return `${mins} min`
  const h = Math.floor(mins / 60)
  const m = mins % 60
  return m === 0 ? `${h}h` : `${h}h${m}m`
}

// ----------------------------------------------------------------------------
// JourneyCard - calatorie cu schimbare (>= 2 legs)
// ----------------------------------------------------------------------------
// ============================================================================
// COMPONENTE DE AFISARE BILETE - design "Boarding Pass"
// ============================================================================
// Arhitectura UI (hibrid):
//   1. Card compact in lista (TicketCard / JourneyCard):
//      - ruta XL cu statii si ore
//      - vagon si loc ca 2 cutii mari separate
//      - pasagerul afisat INTOTDEAUNA (numele de pe document)
//      - buton CTA "Vezi bilet & QR" + click pe card = deschide modal
//   2. Modal full-screen "Boarding Pass" (BoardingPassModal):
//      - tot biletul aerisit, cu QR mare jos
//      - butoane Anulare / Reprogramare in interior
//      - overlay diagonal FOLOSIT / ANULAT pentru bilete inactive
//      - banner reprogramare cu link la noul ID
// ============================================================================

// ---------------------------------------------------------------------------
// SeatBox - cutie mare cu vagon + loc, formata vizual
// ---------------------------------------------------------------------------
// Pentru biletul afisat in card sau in modal, locurile (V2-15A) sunt impartite
// vizual in 2 cutii alaturate ca pe un boarding pass real:
//   ┌────────┐ ┌────────┐
//   │ VAGON  │ │  LOC   │
//   │   2    │ │  15A   │
//   └────────┘ └────────┘
// size: 'sm' (in card) | 'lg' (in modal).
function SeatBox({ car, seat, size = 'sm' }) {
  const isLg = size === 'lg'
  const labelCls = isLg ? 'text-xs' : 'text-[10px]'
  const valueCls = isLg ? 'text-3xl' : 'text-xl'
  const boxCls = isLg
    ? 'min-w-[80px] px-4 py-2'
    : 'min-w-[58px] px-3 py-1.5'
  return (
    <div className="flex gap-2">
      <div className={`${boxCls} rounded-lg border-2 border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-700/50 text-center`}>
        <div className={`${labelCls} font-semibold tracking-wider text-slate-500 dark:text-slate-400`}>VAGON</div>
        <div className={`${valueCls} font-bold text-slate-900 dark:text-slate-100 leading-none mt-0.5`}>{car}</div>
      </div>
      <div className={`${boxCls} rounded-lg border-2 border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-700/50 text-center`}>
        <div className={`${labelCls} font-semibold tracking-wider text-slate-500 dark:text-slate-400`}>LOC</div>
        <div className={`${valueCls} font-bold text-slate-900 dark:text-slate-100 leading-none mt-0.5`}>{seat}</div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// RouteHeader - statii cu sageata in mijloc si orele dedesubt
// ---------------------------------------------------------------------------
// size: 'sm' (in card) | 'lg' (in modal).
function RouteHeader({ from, to, fromTime, toTime, size = 'sm' }) {
  const isLg = size === 'lg'
  const stationCls = isLg
    ? 'text-xl sm:text-2xl font-bold leading-tight'
    : 'text-sm sm:text-base font-bold leading-tight'
  const timeCls = isLg ? 'text-lg font-mono' : 'text-sm font-mono'
  return (
    <div className="flex items-center justify-between gap-3">
      <div className="min-w-0 flex-1">
        <div className={`${stationCls} text-slate-900 dark:text-slate-50 break-words`}>
          {from}
        </div>
        {fromTime && (
          <div className={`${timeCls} text-emerald-700 dark:text-emerald-400 mt-1`}>{fromTime}</div>
        )}
      </div>
      <div className="text-emerald-600 dark:text-emerald-400 shrink-0 px-1" aria-hidden="true">
        <svg className={isLg ? 'w-10 h-10' : 'w-6 h-6'} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M14 5l7 7m0 0l-7 7m7-7H3" />
        </svg>
      </div>
      <div className="min-w-0 flex-1 text-right">
        <div className={`${stationCls} text-slate-900 dark:text-slate-50 break-words`}>
          {to}
        </div>
        {toTime && (
          <div className={`${timeCls} text-emerald-700 dark:text-emerald-400 mt-1`}>{toTime}</div>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// PriceBlock - defalcarea pretului pentru un bilet (sau journey)
// ---------------------------------------------------------------------------
// Afiseaza pentru fiecare bilet (pasager): nume, pret, reducere aplicata.
// Sub lista: total. Cand exista doar 1 pasager, lista e mai compacta.
function PriceBlock({ tickets }) {
  const total = tickets.reduce((s, t) => s + Number(t.price || 0), 0)
  // Cand exista 1 singur bilet, NU repetam numele pasagerului (apare deja in
  // sectiunea PASAGER de sus). In schimb, folosim ca label tipul biletului
  // (tren+numar) sau "Bilet" generic.
  // Pentru multi-pax / multi-leg, numele ramane necesar pentru distinctie.
  const showPassengerLabel = tickets.length > 1
  return (
    <div>
      <div className="text-xs font-semibold tracking-wider text-slate-500 dark:text-slate-400 mb-2">
        DETALII PRET
      </div>
      <div className="space-y-2">
        {tickets.map((t, i) => {
          const label = discountLabel(t)
          const isCovered = t.uses_subscription_id && Number(t.price || 0) === 0
          const rowLabel = showPassengerLabel
            ? ticketPassengerName(t)
            : (t.train_type && t.train_number
                ? `${fmtTrainType(t.train_type)} ${t.train_number}`
                : 'Bilet')
          return (
            <div
              key={t.ticket_id ?? i}
              className="flex justify-between items-start gap-3 text-sm"
            >
              <div className="min-w-0">
                <div className="font-semibold text-slate-900 dark:text-slate-100 truncate">
                  {rowLabel}
                </div>
                {label && (
                  <div className="text-xs text-emerald-700 dark:text-emerald-300 mt-0.5">
                    {label}
                  </div>
                )}
              </div>
              <div className="text-right shrink-0">
                {isCovered ? (
                  <div className="font-mono font-semibold text-emerald-700 dark:text-emerald-300">
                    Gratuit
                  </div>
                ) : (
                  <div className="font-mono font-semibold text-slate-900 dark:text-slate-100">
                    {fmtRON(t.price)}
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>
      {tickets.length > 1 && (
        <div className="flex justify-between items-center mt-3 pt-3 border-t border-slate-200 dark:border-slate-700">
          <span className="font-semibold text-slate-700 dark:text-slate-300">Total</span>
          <span className="font-mono font-bold text-lg text-slate-900 dark:text-slate-100">
            {fmtRON(total)}
          </span>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// StatusOverlay - banda diagonala FOLOSIT / ANULAT peste QR
// ---------------------------------------------------------------------------
function StatusOverlay({ status }) {
  if (status === 'active') return null
  let label, cls
  if (status === 'used') { label = 'FOLOSIT'; cls = 'bg-blue-600' }
  else if (status === 'cancelled' || status === 'refunded') { label = 'ANULAT'; cls = 'bg-red-600' }
  else if (status === 'expired') { label = 'EXPIRAT'; cls = 'bg-slate-500' }
  else if (status === 'rescheduled') { label = 'REPROGRAMAT'; cls = 'bg-amber-600' }
  else return null
  return (
    <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
      <div className={`px-8 py-2 ${cls} text-white text-2xl sm:text-3xl font-black tracking-widest rotate-[-12deg] shadow-lg opacity-95 border-4 border-white/30`}>
        {label}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// BoardingPassModal - vederea extinsa full-screen
// ---------------------------------------------------------------------------
// Primeste:
//   - tickets: array de bilete care apartin aceleiasi calatorii
//              (1 bilet = bilet simplu, N = multi-leg sau multi-pax)
//   - onClose, onCancel, onReschedule: callbacks
// Logica:
//   - Pentru calatorie multi-leg (acelasi pasager, mai multe leg-uri), afisam
//     un mini-boarding-pass per leg cu transfer intre ele.
//   - Pentru multi-pax (acelasi tren, mai multi pasageri), afisam 1 boarding
//     pass cu detalii pret per pasager.
function BoardingPassModal({ tickets, onClose, onCancel, onReschedule }) {
  // tickets poate fi: [t1], [leg1, leg2, ...] (multi-leg) sau [pax1, pax2, ...] (multi-pax)
  const isMultiLeg = tickets.length > 1 && tickets[0].journey_group_id
  const isMultiPax = tickets.length > 1 && !tickets[0].journey_group_id
  const headerTicket = tickets[0]
  const canCancel = tickets.some((t) => t.ticket_status === 'active')

  function getQR(ticket) {
    return ticket.qr_data_url
  }

  // Esc inchide modal-ul
  useEffect(() => {
    function onKey(e) { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-start sm:items-center justify-center p-2 sm:p-4 overflow-y-auto"
      role="dialog"
      aria-modal="true"
      aria-labelledby="boarding-pass-title"
      onClick={onClose}
    >
      <div
        className="bg-white dark:bg-slate-800 rounded-2xl shadow-2xl w-full max-w-2xl my-4"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-5 py-4 border-b border-slate-200 dark:border-slate-700 flex items-center justify-between gap-3">
          <div>
            <div id="boarding-pass-title" className="text-xs font-semibold tracking-widest text-emerald-700 dark:text-emerald-400">
              BILET TREN
            </div>
            <div className="text-sm text-slate-500 dark:text-slate-400">CFR Calatori</div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 text-2xl leading-none"
            aria-label="Inchide"
          >
            x
          </button>
        </div>

        {/* Banner reprogramare (daca biletul afisat e cel vechi) */}
        {headerTicket.ticket_status === 'rescheduled' && (
          <div className="px-5 py-3 bg-amber-50 dark:bg-amber-900/30 border-b border-amber-200 dark:border-amber-800 text-sm text-amber-800 dark:text-amber-200">
            ⚠ Acest bilet a fost reprogramat. Caută noul bilet activ in lista.
          </div>
        )}

        <div className="px-5 py-5 space-y-5">
          {/* Multi-leg: un mini-pass per leg cu separator TRANSFER */}
          {/* Multi-pax: un boarding pass per pasager cu separator PASAGER N */}
          {/* Single: 1 boarding pass complet */}
          {isMultiLeg ? (
            tickets.map((leg, idx) => (
              <div key={leg.ticket_id}>
                {idx > 0 && (
                  <div className="text-center my-4 text-xs font-semibold tracking-widest text-slate-500 dark:text-slate-400">
                    --- TRANSFER {leg.transfer_minutes != null ? formatTransferMinutes(leg.transfer_minutes) : ''} ---
                  </div>
                )}
                <BoardingPassLeg
                  ticket={leg}
                  qrSrc={getQR(leg)}
                  loadingQr={false}
                  legLabel={`Tren ${idx + 1}/${tickets.length}`}
                />
              </div>
            ))
          ) : isMultiPax ? (
            tickets.map((pax, idx) => (
              <div key={pax.ticket_id}>
                {idx > 0 && (
                  <div className="text-center my-4 text-xs font-semibold tracking-widest text-slate-500 dark:text-slate-400">
                    ─── PASAGER {idx + 1} ───
                  </div>
                )}
                <BoardingPassLeg
                  ticket={pax}
                  qrSrc={getQR(pax)}
                  loadingQr={false}
                />
              </div>
            ))
          ) : (
            <BoardingPassLeg
              ticket={headerTicket}
              qrSrc={getQR(headerTicket)}
              loadingQr={false}
            />
          )}

          {/* Detalii pret - mereu jos */}
          <div className="border-t border-dashed border-slate-300 dark:border-slate-600 pt-4">
            <PriceBlock tickets={tickets} />
          </div>
        </div>

        {/* Footer cu actiuni */}
        <div className="px-5 py-4 border-t border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 rounded-b-2xl flex flex-wrap gap-2 justify-between items-center">
          <div className="text-xs text-slate-500 dark:text-slate-400">
            Bilet #{headerTicket.ticket_id}
            {headerTicket.purchase_time && (
              <> · Cumparat {fmtDate(headerTicket.purchase_time)}</>
            )}
          </div>
          {canCancel && (
            <div className="flex gap-2">
              <button
                onClick={() => {
                  onClose()
                  const activeTickets = tickets.filter(t => t.ticket_status === 'active')
                  onReschedule(activeTickets.length > 1 ? activeTickets : headerTicket)
                }}
                className="px-3 py-1.5 rounded-lg text-sm font-semibold border border-amber-300 dark:border-amber-700 text-amber-700 dark:text-amber-300 hover:bg-amber-50 dark:hover:bg-amber-900/30"
              >
                Reprogramare
              </button>
              <button
                onClick={() => { onClose(); onCancel(headerTicket) }}
                className="px-3 py-1.5 rounded-lg text-sm font-semibold border border-red-300 dark:border-red-700 text-red-700 dark:text-red-300 hover:bg-red-50 dark:hover:bg-red-900/30"
              >
                Anulare
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// BoardingPassLeg - corpul unui boarding pass pentru un singur leg/bilet
// Layout compact: detalii stanga + QR dreapta
// ---------------------------------------------------------------------------
function BoardingPassLeg({ ticket: t, qrSrc, loadingQr, legLabel }) {
  const seats = (t.seats || []).map(parseSeat).filter(Boolean)
  const status = t.ticket_status || 'active'

  const qrLabel = status === 'active' ? 'Arată conductorului'
    : status === 'used' ? 'Validat'
    : status === 'cancelled' || status === 'refunded' ? 'Anulat'
    : status === 'expired' ? 'Expirat'
    : 'Reprogramat'

  return (
    <div className="flex gap-3 items-start">
      {/* Stânga: toate detaliile */}
      <div className="flex-1 min-w-0 space-y-2">
        {/* Tren + data */}
        <div className="flex items-baseline justify-between gap-2">
          <div>
            {legLabel && (
              <div className="text-[10px] font-semibold tracking-widest text-slate-500 dark:text-slate-400">
                {legLabel}
              </div>
            )}
            <div className="text-base font-bold text-slate-900 dark:text-slate-50">
              {fmtTrainType(t.train_type)} {t.train_number || `#${t.train_id}`}
              {t.operator_name && (
                <span className="ml-2 text-xs font-normal text-slate-500 dark:text-slate-400">{t.operator_name}</span>
              )}
            </div>
          </div>
          <div className="text-xs text-slate-500 dark:text-slate-400 shrink-0">
            {fmtDate(t.travel_date)}
          </div>
        </div>

        {/* Ruta */}
        <RouteHeader
          from={t.departure_station}
          to={t.arrival_station}
          fromTime={t.departure_time}
          toTime={t.arrival_time}
          size="lg"
        />

        {/* Separator + pasager + loc */}
        <div className="pt-2 border-t border-dashed border-slate-300 dark:border-slate-600">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <div>
              <div className="text-[10px] font-semibold tracking-wider text-slate-500 dark:text-slate-400 mb-0.5">
                PASAGER
              </div>
              <div className="text-sm font-bold text-slate-900 dark:text-slate-50">
                {ticketPassengerName(t)}
              </div>
            </div>
            {seats.length > 0 && (
              <div className="flex gap-1.5">
                {seats.map((s, i) => (
                  <SeatBox key={i} car={s.car} seat={s.seat} size="sm" />
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Dreapta: QR compact */}
      <div className="flex flex-col items-center shrink-0">
        <div className="relative bg-white p-2 rounded-lg border border-slate-200 dark:border-slate-600 shadow-sm">
          {qrSrc ? (
            <img
              src={qrSrc}
              alt="Cod QR bilet"
              className={`w-32 h-32 sm:w-36 sm:h-36 ${status !== 'active' ? 'opacity-40' : ''}`}
            />
          ) : (
            <div className="w-32 h-32 sm:w-36 sm:h-36 flex items-center justify-center text-slate-400 text-xs text-center">
              {loadingQr ? 'Se încarcă...' : 'QR indisponibil'}
            </div>
          )}
          <StatusOverlay status={status} />
        </div>
        <div className="mt-1 text-[10px] text-slate-500 dark:text-slate-400 text-center max-w-[9rem]">
          {qrLabel}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// CompactTicketBody - sumarul afisat in card (single leg)
// ---------------------------------------------------------------------------
// Continut: tren + data + ruta + pasager + vagon/loc.
// NU contine QR, NU contine pretul detaliat (alea sunt in modal).
function CompactTicketBody({ ticket: t }) {
  const seats = (t.seats || []).map(parseSeat).filter(Boolean)

  return (
    <div className="space-y-3">
      <div className="flex items-baseline justify-between gap-2">
        <div className="text-sm font-bold text-slate-900 dark:text-slate-50">
          {fmtTrainType(t.train_type)} {t.train_number || `#${t.train_id}`}
        </div>
        <div className="text-xs text-slate-500 dark:text-slate-400">
          {fmtDate(t.travel_date)}
        </div>
      </div>

      <RouteHeader
        from={t.departure_station}
        to={t.arrival_station}
        fromTime={t.departure_time}
        toTime={t.arrival_time}
      />

      <div className="space-y-1.5 pt-1 border-t border-slate-100 dark:border-slate-700/50">
        <div className="flex items-center justify-between gap-2 text-xs">
          <span className="text-slate-700 dark:text-slate-300 font-medium truncate">
            {ticketPassengerName(t)}
          </span>
          {seats.length > 0 ? (
            <span className="font-mono text-slate-500 dark:text-slate-400 shrink-0">
              V{seats[0].car} · {seats[0].seat}
            </span>
          ) : (
            <span className="text-slate-400 dark:text-slate-500 text-[10px] shrink-0">fără loc</span>
          )}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// TicketCard - card pentru un bilet simplu (1 leg, 1 pasager)
// ---------------------------------------------------------------------------
function TicketCard({ t, highlight, onCancel, onReschedule, onShowQR }) {
  const status = STATUS_META[t.ticket_status] || STATUS_META.active
  const canModify = t.ticket_status === 'active'
  const isCancelled = ['cancelled', 'refunded', 'rescheduled'].includes(t.ticket_status)

  return (
    <div
      className={`rounded-2xl border-2 transition-all ${
        highlight
          ? 'border-emerald-500 shadow-lg ring-2 ring-emerald-200 dark:ring-emerald-900'
          : 'border-slate-200 dark:border-slate-700 hover:border-emerald-300 dark:hover:border-emerald-700'
      } bg-white dark:bg-slate-800 overflow-hidden`}
    >
      {/* Badge status sus-stanga */}
      <div className="flex items-center justify-between px-4 pt-3">
        <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${status.cls}`}>
          {status.label}
        </span>
        {t.cancel_refund_amount != null && (
          <span className="text-xs text-slate-500 dark:text-slate-400">
            Refund: {fmtRON(t.cancel_refund_amount)}
          </span>
        )}
      </div>

      {/* Continut clickable (deschide modal) */}
      <button
        type="button"
        onClick={() => onShowQR(t)}
        className="w-full text-left px-4 py-3"
      >
        <CompactTicketBody ticket={t} />
      </button>

      {/* Actiuni */}
      <div className="px-4 pb-3 pt-1 flex flex-wrap gap-2 border-t border-slate-100 dark:border-slate-700/50">
        {!isCancelled && (
          <button
            type="button"
            onClick={() => onShowQR(t)}
            className="flex-1 min-w-[140px] px-3 py-2 rounded-lg text-sm font-semibold bg-emerald-600 hover:bg-emerald-700 text-white"
          >
            Vezi bilet & QR
          </button>
        )}
        {canModify && (
          <>
            <button
              onClick={() => onReschedule(t)}
              className="px-3 py-2 rounded-lg text-sm font-semibold border border-amber-300 dark:border-amber-700 text-amber-700 dark:text-amber-300 hover:bg-amber-50 dark:hover:bg-amber-900/30"
            >
              Reprogramare
            </button>
            <button
              onClick={() => onCancel(t)}
              className="px-3 py-2 rounded-lg text-sm font-semibold border border-red-300 dark:border-red-700 text-red-700 dark:text-red-300 hover:bg-red-50 dark:hover:bg-red-900/30"
            >
              Anulare
            </button>
          </>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// JourneyCard - card pentru o calatorie cu transfer (>= 2 legs, acelasi pasager)
// ---------------------------------------------------------------------------
function JourneyCard({ legs, highlightId, onCancel, onReschedule, onShowQR }) {
  const isHighlighted = legs.some((l) => String(l.ticket_id) === String(highlightId))
  const firstLeg = legs[0]
  const lastLeg = legs[legs.length - 1]
  const allActive = legs.every((l) => l.ticket_status === 'active')
  const anyActive = legs.some((l) => l.ticket_status === 'active')
  const displayStatus = allActive
    ? 'active'
    : legs.every((l) => ['used', 'expired'].includes(l.ticket_status))
    ? 'used'
    : legs.every((l) => ['cancelled', 'refunded', 'rescheduled'].includes(l.ticket_status))
    ? 'cancelled'
    : 'mixed'
  const statusMeta = STATUS_META[displayStatus] || { label: 'Mixt', cls: 'bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200' }

  return (
    <div
      className={`rounded-2xl border-2 transition-all ${
        isHighlighted
          ? 'border-emerald-500 shadow-lg ring-2 ring-emerald-200 dark:ring-emerald-900'
          : 'border-slate-200 dark:border-slate-700 hover:border-emerald-300 dark:hover:border-emerald-700'
      } bg-white dark:bg-slate-800 overflow-hidden`}
    >
      <div className="flex items-center justify-between px-4 pt-3">
        <div className="flex items-center gap-2">
          <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${statusMeta.cls}`}>
            {statusMeta.label}
          </span>
          <span className="text-[10px] font-semibold tracking-wider text-slate-500 dark:text-slate-400">
            CALATORIE CU {legs.length - 1} TRANSFER{legs.length > 2 ? 'URI' : ''}
          </span>
        </div>
      </div>

      <button
        type="button"
        onClick={() => onShowQR(legs)}
        className="w-full text-left px-4 py-3"
      >
        <div className="space-y-3">
          <div className="flex items-baseline justify-between gap-2">
            <div className="text-sm font-bold text-slate-900 dark:text-slate-50">
              {legs.length} trenuri
            </div>
            <div className="text-xs text-slate-500 dark:text-slate-400">
              {fmtDate(firstLeg.travel_date)}
            </div>
          </div>

          <RouteHeader
            from={firstLeg.departure_station}
            to={lastLeg.arrival_station}
            fromTime={firstLeg.departure_time}
            toTime={lastLeg.arrival_time}
          />

          {/* Mini sumar leg-uri */}
          <div className="space-y-1.5 pt-2">
            {legs.map((leg, i) => {
              const firstSeat = (leg.seats || []).map(parseSeat).filter(Boolean)[0]
              return (
                <div key={leg.ticket_id} className="flex items-center justify-between gap-2 text-xs">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="font-bold text-slate-700 dark:text-slate-300">
                      {i + 1}.
                    </span>
                    <span className="text-slate-600 dark:text-slate-400 truncate">
                      {fmtTrainType(leg.train_type)} {leg.train_number}
                    </span>
                    <span className="text-slate-500 dark:text-slate-400 font-mono">
                      {leg.departure_time}-{leg.arrival_time}
                    </span>
                  </div>
                  {firstSeat && (
                    <span className="font-mono text-slate-600 dark:text-slate-300 shrink-0">
                      V{firstSeat.car}, {firstSeat.seat}
                    </span>
                  )}
                </div>
              )
            })}
          </div>

          <div className="flex items-end justify-between pt-1">
            <div>
              <div className="text-[10px] font-semibold tracking-wider text-slate-500 dark:text-slate-400">
                PASAGER
              </div>
              <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                {ticketPassengerName(firstLeg)}
              </div>
            </div>
          </div>
        </div>
      </button>

      <div className="px-4 pb-3 pt-1 flex flex-wrap gap-2 border-t border-slate-100 dark:border-slate-700/50">
        <button
          type="button"
          onClick={() => onShowQR(legs)}
          className="flex-1 min-w-[140px] px-3 py-2 rounded-lg text-sm font-semibold bg-emerald-600 hover:bg-emerald-700 text-white"
        >
          Vezi bilet & QR
        </button>
        {anyActive && (
          <>
            <button
              onClick={() => onReschedule(firstLeg)}
              className="px-3 py-2 rounded-lg text-sm font-semibold border border-amber-300 dark:border-amber-700 text-amber-700 dark:text-amber-300 hover:bg-amber-50 dark:hover:bg-amber-900/30"
              title="Reprogramare primul leg"
            >
              Reprogramare
            </button>
            <button
              onClick={() => onCancel(firstLeg)}
              className="px-3 py-2 rounded-lg text-sm font-semibold border border-red-300 dark:border-red-700 text-red-700 dark:text-red-300 hover:bg-red-50 dark:hover:bg-red-900/30"
              title="Anulare primul leg"
            >
              Anulare
            </button>
          </>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// MultiPaxCard - card pentru un bilet cu mai multi pasageri (acelasi tren)
// ---------------------------------------------------------------------------
function MultiPaxCard({ passengers, highlightId, onCancel, onReschedule, onShowQR }) {
  const isHighlighted = passengers.some((p) => String(p.ticket_id) === String(highlightId))
  const first = passengers[0]
  const allActive = passengers.every((p) => p.ticket_status === 'active')
  const anyActive = passengers.some((p) => p.ticket_status === 'active')
  const displayStatus = anyActive
    ? 'active'
    : passengers.every((p) => ['used', 'expired'].includes(p.ticket_status))
    ? 'used'
    : passengers.every((p) => ['cancelled', 'refunded', 'rescheduled'].includes(p.ticket_status))
    ? 'cancelled'
    : 'active'
  const statusMeta = STATUS_META[displayStatus] || STATUS_META.active

  return (
    <div
      className={`rounded-2xl border-2 transition-all ${
        isHighlighted
          ? 'border-emerald-500 shadow-lg ring-2 ring-emerald-200 dark:ring-emerald-900'
          : 'border-slate-200 dark:border-slate-700 hover:border-emerald-300 dark:hover:border-emerald-700'
      } bg-white dark:bg-slate-800 overflow-hidden`}
    >
      <div className="flex items-center justify-between px-4 pt-3">
        <div className="flex items-center gap-2">
          <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${statusMeta.cls}`}>
            {statusMeta.label}
          </span>
          <span className="text-[10px] font-semibold tracking-wider text-slate-500 dark:text-slate-400">
            {passengers.length} PASAGERI
          </span>
        </div>
      </div>

      <button
        type="button"
        onClick={() => onShowQR(passengers)}
        className="w-full text-left px-4 py-3"
      >
        <div className="space-y-3">
          <div className="flex items-baseline justify-between gap-2">
            <div className="text-sm font-bold text-slate-900 dark:text-slate-50">
              {fmtTrainType(first.train_type)} {first.train_number || `#${first.train_id}`}
            </div>
            <div className="text-xs text-slate-500 dark:text-slate-400">
              {fmtDate(first.travel_date)}
            </div>
          </div>

          <RouteHeader
            from={first.departure_station}
            to={first.arrival_station}
            fromTime={first.departure_time}
            toTime={first.arrival_time}
          />

          <div className="space-y-1.5 pt-1 border-t border-slate-100 dark:border-slate-700/50">
            {passengers.map((p) => {
              const seat = (p.seats || []).map(parseSeat).filter(Boolean)[0]
              return (
                <div key={p.ticket_id} className="flex items-center justify-between gap-2 text-xs">
                  <span className="text-slate-700 dark:text-slate-300 font-medium truncate">
                    {ticketPassengerName(p)}
                  </span>
                  {seat ? (
                    <span className="font-mono text-slate-500 dark:text-slate-400 shrink-0">
                      V{seat.car} · {seat.seat}
                    </span>
                  ) : (
                    <span className="text-slate-400 dark:text-slate-500 text-[10px] shrink-0">fără loc</span>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      </button>

      <div className="px-4 pb-3 pt-1 flex flex-wrap gap-2 border-t border-slate-100 dark:border-slate-700/50">
        {displayStatus !== 'cancelled' && (
          <button
            type="button"
            onClick={() => onShowQR(passengers)}
            className="flex-1 min-w-[140px] px-3 py-2 rounded-lg text-sm font-semibold bg-emerald-600 hover:bg-emerald-700 text-white"
          >
            Vezi bilete & QR
          </button>
        )}
        {anyActive && (
          <>
            <button
              onClick={() => onReschedule(passengers.filter(p => p.ticket_status === 'active'))}
              className="px-3 py-2 rounded-lg text-sm font-semibold border border-amber-300 dark:border-amber-700 text-amber-700 dark:text-amber-300 hover:bg-amber-50 dark:hover:bg-amber-900/30"
            >
              Reprogramare
            </button>
            <button
              onClick={() => onCancel(passengers.filter(p => ['active', 'rescheduled'].includes(p.ticket_status)))}
              className="px-3 py-2 rounded-lg text-sm font-semibold border border-red-300 dark:border-red-700 text-red-700 dark:text-red-300 hover:bg-red-50 dark:hover:bg-red-900/30"
            >
              Anulare
            </button>
          </>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// TicketJourneyModal - boarding pass pentru un bilet cu ticket_legs
// Fiecare leg are propriul QR (qr_data_url) si detalii de tren.
// ---------------------------------------------------------------------------
function TicketJourneyModal({ ticket, legs, onClose, onCancel }) {
  const canCancel = ticket.ticket_status === 'active'

  useEffect(() => {
    function onKey(e) { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-start sm:items-center justify-center p-2 sm:p-4 overflow-y-auto"
      role="dialog" aria-modal="true"
      onClick={onClose}
    >
      <div
        className="bg-white dark:bg-slate-800 rounded-2xl shadow-2xl w-full max-w-2xl my-4"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header modal */}
        <div className="px-5 py-4 border-b border-slate-200 dark:border-slate-700 flex items-center justify-between gap-3">
          <div>
            <div className="text-xs font-semibold tracking-widest text-emerald-700 dark:text-emerald-400">
              BILET CU {legs.length} SEGMENTE · CFR Călători
            </div>
            <div className="text-sm font-semibold text-slate-700 dark:text-slate-200 mt-0.5">
              {legs[0]?.departure_station} → {legs[legs.length - 1]?.arrival_station}
            </div>
          </div>
          <button type="button" onClick={onClose}
            className="text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 text-xl leading-none p-1"
            aria-label="Inchide">✕</button>
        </div>

        <div className="px-5 py-4 space-y-4">
          {legs.map((leg, idx) => {
            const parsedSeat = leg.seat_display ? parseSeat(leg.seat_display) : null
            return (
            <div key={leg.leg_id} className="rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden">
              {/* Bara superioară segment */}
              <div className="flex items-center justify-between px-4 py-2 bg-slate-50 dark:bg-slate-700/40 border-b border-slate-200 dark:border-slate-700">
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-semibold tracking-widest text-slate-500 dark:text-slate-400">
                    SEG {idx + 1}/{legs.length}
                  </span>
                  <span className="text-sm font-bold text-slate-800 dark:text-slate-100">
                    {fmtTrainType(leg.train_type)} {leg.train_number}
                  </span>
                </div>
                <span className="text-xs text-slate-500 dark:text-slate-400">{leg.travel_date}</span>
              </div>

              {/* Corp segment: rută + QR */}
              <div className="flex gap-3 p-4 items-start">
                {/* Stânga: rută + pasager + loc */}
                <div className="flex-1 min-w-0 space-y-3">
                  {/* Rută */}
                  <div className="flex items-start gap-2">
                    <div className="flex-1 min-w-0">
                      <div className="text-base font-bold text-slate-900 dark:text-slate-50 leading-tight break-words">
                        {leg.departure_station}
                      </div>
                      {leg.departure_time && (
                        <div className="text-lg font-mono text-emerald-600 dark:text-emerald-400">{leg.departure_time}</div>
                      )}
                    </div>
                    <div className="text-emerald-500 dark:text-emerald-400 shrink-0 mt-1">
                      <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                      </svg>
                    </div>
                    <div className="flex-1 min-w-0 text-right">
                      <div className="text-base font-bold text-slate-900 dark:text-slate-50 leading-tight break-words">
                        {leg.arrival_station}
                      </div>
                      {leg.arrival_time && (
                        <div className="text-lg font-mono text-emerald-600 dark:text-emerald-400">{leg.arrival_time}</div>
                      )}
                    </div>
                  </div>

                  {/* Pasager + loc + preț */}
                  <div className="flex items-end justify-between gap-3 border-t border-dashed border-slate-200 dark:border-slate-600 pt-2">
                    <div>
                      <div className="text-[10px] font-semibold tracking-wider text-slate-500 dark:text-slate-400 mb-0.5">PASAGER</div>
                      <div className="text-sm font-bold text-slate-900 dark:text-slate-50">{ticketPassengerName(ticket)}</div>
                      {parsedSeat && (
                        <div className="mt-1.5">
                          <SeatBox car={parsedSeat.car} seat={parsedSeat.seat} size="sm" />
                        </div>
                      )}
                    </div>
                    <div className="text-right shrink-0">
                      <div className="text-[10px] font-semibold tracking-wider text-slate-500 dark:text-slate-400 mb-0.5">TARIF</div>
                      <div className="text-base font-bold font-mono text-slate-900 dark:text-slate-100">{fmtRON(leg.price)}</div>
                    </div>
                  </div>
                </div>

                {/* Dreapta: QR */}
                <div className="flex flex-col items-center shrink-0">
                  <div className="relative bg-white p-1.5 rounded-lg border border-slate-200 dark:border-slate-600 shadow-sm">
                    {leg.qr_data_url ? (
                      <img src={leg.qr_data_url} alt={`QR segment ${idx + 1}`}
                        className={`w-28 h-28 sm:w-32 sm:h-32 ${ticket.ticket_status !== 'active' ? 'opacity-40' : ''}`}
                      />
                    ) : (
                      <div className="w-28 h-28 sm:w-32 sm:h-32 flex items-center justify-center text-slate-400 text-xs text-center">
                        QR indisponibil
                      </div>
                    )}
                    <StatusOverlay status={ticket.ticket_status} />
                  </div>
                  <div className="mt-1 text-[10px] text-slate-500 dark:text-slate-400 text-center">
                    Arată conductorului
                  </div>
                </div>
              </div>

              {/* Separator transfer */}
              {idx < legs.length - 1 && (
                <div className="px-4 py-2 bg-amber-50 dark:bg-amber-900/20 border-t border-amber-200 dark:border-amber-800 text-center text-xs font-semibold text-amber-700 dark:text-amber-300 tracking-widest">
                  ⇄ TRANSFER
                </div>
              )}
            </div>
          )})}

          <div className="flex justify-between items-center pt-1">
            <span className="text-sm font-bold text-slate-700 dark:text-slate-300">Total călătorie</span>
            <span className="text-xl font-bold font-mono text-emerald-600 dark:text-emerald-400">
              {fmtRON(legs.reduce((s, l) => s + Number(l.price || 0), 0))}
            </span>
          </div>
        </div>

        <div className="px-5 py-4 border-t border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 rounded-b-2xl flex flex-wrap gap-2 justify-between items-center">
          <div className="text-xs text-slate-500 dark:text-slate-400">
            Bilet #{ticket.ticket_id}
            {ticket.purchase_time && <> · Cumpărat {fmtDate(ticket.purchase_time)}</>}
          </div>
          {canCancel && (
            <button
              onClick={() => { onClose(); onCancel(ticket) }}
              className="px-3 py-1.5 rounded-lg text-sm font-semibold border border-red-300 dark:border-red-700 text-red-700 dark:text-red-300 hover:bg-red-50 dark:hover:bg-red-900/30"
            >
              Anulare
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// TicketJourneyCard - card pentru un bilet cu ticket_legs (buy-journey)
// ---------------------------------------------------------------------------
function TicketJourneyCard({ ticket, legs, highlightId, onCancel, onShowJourney }) {
  const isHighlighted = String(ticket.ticket_id) === String(highlightId)
  const firstLeg = legs[0]
  const lastLeg = legs[legs.length - 1]
  const statusMeta = STATUS_META[ticket.ticket_status] || STATUS_META.active
  const canModify = ticket.ticket_status === 'active'

  return (
    <div className={`rounded-2xl border-2 transition-all ${
      isHighlighted
        ? 'border-emerald-500 shadow-lg ring-2 ring-emerald-200 dark:ring-emerald-900'
        : 'border-slate-200 dark:border-slate-700 hover:border-emerald-300 dark:hover:border-emerald-700'
    } bg-white dark:bg-slate-800 overflow-hidden`}>
      <div className="flex items-center justify-between px-4 pt-3">
        <div className="flex items-center gap-2">
          <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${statusMeta.cls}`}>
            {statusMeta.label}
          </span>
          <span className="text-[10px] font-semibold tracking-wider text-slate-500 dark:text-slate-400">
            {legs.length} SEGMENTE
          </span>
        </div>
      </div>

      <button type="button" onClick={() => onShowJourney(ticket, legs)}
        className="w-full text-left px-4 py-3">
        <div className="space-y-3">
          <div className="flex items-baseline justify-between gap-2">
            <div className="text-sm font-bold text-slate-900 dark:text-slate-50">
              Journey cu schimbare
            </div>
            <div className="text-xs text-slate-500 dark:text-slate-400">
              {firstLeg?.travel_date}
            </div>
          </div>

          <RouteHeader
            from={firstLeg?.departure_station} to={lastLeg?.arrival_station}
            fromTime={firstLeg?.departure_time} toTime={lastLeg?.arrival_time}
          />

          <div className="space-y-1.5 pt-2">
            {legs.map((leg, i) => (
              <div key={leg.leg_id} className="flex items-center justify-between gap-2 text-xs">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="font-bold text-slate-700 dark:text-slate-300">{i + 1}.</span>
                  <span className="text-slate-600 dark:text-slate-400 truncate">
                    {fmtTrainType(leg.train_type)} {leg.train_number}
                  </span>
                  <span className="text-slate-500 dark:text-slate-400 font-mono">
                    {leg.departure_time}-{leg.arrival_time}
                  </span>
                </div>
                <span className="font-mono text-slate-500 dark:text-slate-400 shrink-0">
                  {fmtRON(leg.price)}
                </span>
              </div>
            ))}
          </div>

          <div className="flex items-end justify-between pt-1">
            <div>
              <div className="text-[10px] font-semibold tracking-wider text-slate-500 dark:text-slate-400">PASAGER</div>
              <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                {ticketPassengerName(ticket)}
              </div>
            </div>
            <div className="text-right">
              <div className="text-[10px] text-slate-400 dark:text-slate-500">TOTAL</div>
              <div className="text-sm font-bold font-mono text-slate-900 dark:text-slate-100">
                {fmtRON(legs.reduce((s, l) => s + Number(l.price || 0), 0))}
              </div>
            </div>
          </div>
        </div>
      </button>

      <div className="px-4 pb-3 pt-1 flex flex-wrap gap-2 border-t border-slate-100 dark:border-slate-700/50">
        <button type="button" onClick={() => onShowJourney(ticket, legs)}
          className="flex-1 min-w-[140px] px-3 py-2 rounded-lg text-sm font-semibold bg-emerald-600 hover:bg-emerald-700 text-white">
          Vezi bilete & QR
        </button>
        {canModify && (
          <button onClick={() => onCancel(ticket)}
            className="px-3 py-2 rounded-lg text-sm font-semibold border border-red-300 dark:border-red-700 text-red-700 dark:text-red-300 hover:bg-red-50 dark:hover:bg-red-900/30">
            Anulare
          </button>
        )}
      </div>
    </div>
  )
}

// ----------------------------------------------------------------------------
// MyTickets - componenta principala (lista + tab-uri + modale)
// ----------------------------------------------------------------------------
export default function MyTickets() {
  const navigate = useNavigate()
  const [tickets, setTickets] = useState([])
  const [modalTarget, setModalTarget] = useState(null)
  // { ticket, legs } pentru biletele cu ticket_legs (noul format journey)
  const [journeyModal, setJourneyModal] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [toast, setToast] = useState(null)
  const [cancelTarget, setCancelTarget] = useState(null)
  const [activeTab, setActiveTab] = useState('active')

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
    // Biletul anulat se muta din "Active" in "Anulate". Comutam acolo automat
    // ca utilizatorul sa vada efectul si sa primeasca confirmare vizuala.
    setActiveTab('cancelled')
    refresh()
  }

  const handleReschedule = useCallback((ticketOrGroup) => {
    const tickets = Array.isArray(ticketOrGroup) ? ticketOrGroup : [ticketOrGroup]
    navigate('/tickets/reschedule', { state: { tickets } })
  }, [navigate])

  // Toast de succes dupa revenirea din ReschedulePage
  useEffect(() => {
    if (location.state?.rescheduleMsg) {
      setToast({ kind: 'success', msg: location.state.rescheduleMsg })
      setActiveTab('active')
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

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
          to="/tickets/buy"
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
          Nu ai cumparat inca niciun bilet. <Link to="/tickets/buy" className="text-emerald-600 underline">Cumpara primul</Link>.
        </div>
      )}

      {!loading && tickets.length > 0 && (() => {
        // Grupam o singura data si calculam counter-ele pentru fiecare tab.
        const allEntries = groupTicketsIntoJourneys(tickets)
        const counts = { active: 0, completed: 0, cancelled: 0 }
        const entriesByTab = { active: [], completed: [], cancelled: [] }
        for (const entry of allEntries) {
          const cat = categorizeEntry(entry)
          counts[cat] += 1
          entriesByTab[cat].push(entry)
        }
        const currentEntries = entriesByTab[activeTab] || []
        const currentTabMeta = TABS.find((t) => t.id === activeTab)

        return (
          <>
            {/* Tab bar */}
            <div
              className="flex flex-wrap gap-1 mb-4 border-b border-slate-200 dark:border-slate-700"
              role="tablist"
              aria-label="Categorii bilete"
            >
              {TABS.map((tab) => {
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
                    <span
                      className={`ml-2 inline-flex items-center justify-center min-w-[1.5rem] px-2 py-0.5 rounded-full text-xs font-bold ${
                        isActive
                          ? 'bg-emerald-100 dark:bg-emerald-900 text-emerald-800 dark:text-emerald-200'
                          : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300'
                      }`}
                    >
                      {counts[tab.id]}
                    </span>
                  </button>
                )
              })}
            </div>

            {/* Continut tab curent */}
            {currentEntries.length === 0 ? (
              <div className="bg-slate-50 dark:bg-slate-800 rounded-2xl p-6 text-center text-slate-500">
                {currentTabMeta?.emptyMsg || 'Nu ai bilete in aceasta categorie.'}
              </div>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                {currentEntries.map((entry) =>
                  entry.kind === 'ticket_journey' ? (
                    <TicketJourneyCard
                      key={entry.ticket.ticket_id}
                      ticket={entry.ticket}
                      legs={entry.legs}
                      highlightId={highlightId}
                      onCancel={setCancelTarget}
                      onShowJourney={(t, l) => setJourneyModal({ ticket: t, legs: l })}
                    />
                  ) : entry.kind === 'journey' ? (
                    <JourneyCard
                      key={entry.journey_group_id}
                      legs={entry.legs}
                      highlightId={highlightId}
                      onCancel={setCancelTarget}
                      onReschedule={handleReschedule}
                      onShowQR={setModalTarget}
                    />
                  ) : entry.kind === 'multi_pax' ? (
                    <MultiPaxCard
                      key={entry.purchase_key}
                      passengers={entry.passengers}
                      highlightId={highlightId}
                      onCancel={setCancelTarget}
                      onReschedule={handleReschedule}
                      onShowQR={setModalTarget}
                    />
                  ) : (
                    <TicketCard
                      key={entry.ticket.ticket_id}
                      t={entry.ticket}
                      highlight={String(entry.ticket.ticket_id) === String(highlightId)}
                      onCancel={setCancelTarget}
                      onReschedule={handleReschedule}
                      onShowQR={setModalTarget}
                    />
                  )
                )}
              </div>
            )}
          </>
        )
      })()}

      {journeyModal && (
        <TicketJourneyModal
          ticket={journeyModal.ticket}
          legs={journeyModal.legs}
          onClose={() => setJourneyModal(null)}
          onCancel={setCancelTarget}
        />
      )}

      {cancelTarget && (
        <CancelModal
          ticket={cancelTarget}
          onClose={() => setCancelTarget(null)}
          onSuccess={handleCancelSuccess}
        />
      )}

      {modalTarget && (
        <BoardingPassModal
          tickets={Array.isArray(modalTarget) ? modalTarget : [modalTarget]}
          onClose={() => setModalTarget(null)}
          onCancel={setCancelTarget}
          onReschedule={handleReschedule}
        />
      )}
    </div>
  )
}
