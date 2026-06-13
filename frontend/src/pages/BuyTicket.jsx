import { useEffect, useState } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { buyJourney, buyTicket, getMySubscriptions, quoteJourney, quoteTicket, searchTrains, suggestTrips } from '../services/api'
import SeatMap from '../components/SeatMap'
import StationCombobox from '../components/StationCombobox.jsx'
import { fmtTrainType } from '../utils/trainType'


export default function BuyTicket() {
  const navigate = useNavigate()
  const location = useLocation()
  const [fromStation, setFromStation] = useState(location.state?.prefillFrom || null)
  const [toStation, setToStation] = useState(location.state?.prefillTo || null)
  const [travelDate, setTravelDate] = useState(() => {
    const d = new Date(); d.setDate(d.getDate() + 1)
    return d.toISOString().slice(0, 10)
  })
  const ticketType = 'single'
  const [trains, setTrains] = useState([])
  // Itinerarii sugerate (direct + cu schimbari) cand nu exista tren direct
  // sau ca alternativa la trenurile directe gasite.
  const [tripSuggestions, setTripSuggestions] = useState([])
  const [suggestingTrips, setSuggestingTrips] = useState(false)
  const [selectedSeatDetails, setSelectedSeatDetails] = useState([])
  const [coveringSubscription, setCoveringSubscription] = useState(null)
  const [searching, setSearching] = useState(false)
  const [selectedTrain, setSelectedTrain] = useState(null)
  // Un obiect per loc: { forMe: boolean, name: string }
  // forMe=true -> passenger_name=null (reducere automata), forMe=false -> name obligatoriu
  const [passengerConfigs, setPassengerConfigs] = useState([])
  const [quote, setQuote] = useState(null)
  const [quoting, setQuoting] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  // --- Journey (multi-leg) purchase state ---
  const [selectedJourney, setSelectedJourney] = useState(null)
  // journeySeats[legIdx] = { seat_id, label, car_number } | null
  const [journeySeats, setJourneySeats] = useState([])
  // which leg's SeatMap is open; null = none
  const [openSeatLeg, setOpenSeatLeg] = useState(null)
  const [journeySubmitting, setJourneySubmitting] = useState(false)
  const [journeyError, setJourneyError] = useState(null)
  // pasageri: [{passenger_name: null}] = titular, {passenger_name: 'Nume'} = altcineva
  const [journeyPassengers, setJourneyPassengers] = useState([{ passenger_name: null }])
  // quote preț journey
  const [journeyQuote, setJourneyQuote] = useState(null)
  const [journeyQuoting, setJourneyQuoting] = useState(false)

  // Verific daca user are abonament activ care acopera ruta selectata.
  // Daca DA, biletul va fi GRATUIT (price=0) automat la cumparare —
  // backend-ul detecteaza acest lucru in /tickets/buy via subscription_business.
  useEffect(() => {
    if (!fromStation?.station_id || !toStation?.station_id || !travelDate) {
      setCoveringSubscription(null)
      return
    }
    let cancelled = false
    getMySubscriptions()
      .then(rows => {
        if (cancelled) return
        const match = (rows || []).find(s =>
          s.status === 'active' &&
          s.subscription_scope === 'route' &&
          s.valid_from <= travelDate && s.valid_until >= travelDate &&
          (
            (s.from_station_id === fromStation.station_id && s.to_station_id === toStation.station_id) ||
            (s.from_station_id === toStation.station_id && s.to_station_id === fromStation.station_id)
          )
        )
        setCoveringSubscription(match || null)
      })
      .catch(() => setCoveringSubscription(null))
    return () => { cancelled = true }
  }, [fromStation, toStation, travelDate])

  // 1. Cand avem plecare + sosire, cautam trenuri DIRECTE
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

  // 2. In paralel, cautam itinerarii (directe + cu schimbari) prin trip planner.
  // Daca exista 0 trenuri directe sau userul vrea alternative -> afisam sugestii.
  useEffect(() => {
    if (!fromStation || !toStation || !travelDate) {
      setTripSuggestions([])
      return
    }
    let alive = true
    setSuggestingTrips(true)
    suggestTrips(fromStation.station_id, toStation.station_id, travelDate, { topN: 5 })
      .then(r => { if (alive) setTripSuggestions(r?.trips || []) })
      .catch(() => { if (alive) setTripSuggestions([]) })
      .finally(() => { if (alive) setSuggestingTrips(false) })
    return () => { alive = false }
  }, [fromStation, toStation, travelDate])

  // selectedSeats = [{seat_id, label, car_number}, ...] in ordinea layout-ului
  // (vagoane crescator, randuri crescator). Primul = cumparatorul.
  const selectedSeatIds = selectedSeatDetails.map(s => s.seat_id)

  // 2. Cand userul alege un tren -> quote live.
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
      seat_ids: selectedSeatIds.length > 0 ? selectedSeatIds : undefined,
    })
      .then(q => { if (alive) setQuote(q) })
      .catch(() => { if (alive) setQuote(null) })
      .finally(() => { if (alive) setQuoting(false) })
    return () => { alive = false }
  }, [selectedTrain, fromStation, toStation, ticketType, travelDate, selectedSeatIds.join(',')])

  // 3. Sincronizeaza passengerConfigs cu selectedSeatDetails
  useEffect(() => {
    setPassengerConfigs((prev) => {
      const n = selectedSeatDetails.length
      if (n === 0) return []
      return Array.from({ length: n }, (_, i) =>
        prev[i] ?? { forMe: i === 0, name: '' }
      )
    })
  }, [selectedSeatDetails])

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!selectedTrain) { setError('Selecteaza un tren'); return }
    if (selectedSeatDetails.length > 0) {
      for (let i = 0; i < passengerConfigs.length; i++) {
        const cfg = passengerConfigs[i]
        if (!cfg.forMe && !(cfg.name || '').trim()) {
          setError(`Completeaza numele pasagerului ${i + 1}.`)
          return
        }
      }
    }
    setSubmitting(true); setError(null)
    try {
      // Construim lista de pasageri; self (forMe=true) vine primul pentru a
      // beneficia de reducerile aplicabile (backend aplica discount la pax_idx=0)
      let passengers = undefined
      if (selectedSeatDetails.length > 0) {
        const mapped = selectedSeatDetails.map((s, idx) => {
          const cfg = passengerConfigs[idx] || { forMe: false, name: '' }
          return {
            seat_id: s.seat_id,
            passenger_name: cfg.forMe ? null : (cfg.name || '').trim() || null,
          }
        })
        mapped.sort((a, b) => {
          if (a.passenger_name === null && b.passenger_name !== null) return -1
          if (a.passenger_name !== null && b.passenger_name === null) return 1
          return 0
        })
        passengers = mapped
      }
      const r = await buyTicket({
        train_id: selectedTrain.train_id,
        departure_station_id: fromStation.station_id,
        arrival_station_id: toStation.station_id,
        travel_date: travelDate,
        ticket_type: ticketType,
        passengers,
      })
      navigate('/tickets', { state: { newTicketId: r.ticket_id, count: r.count } })
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  const buildJourneyLegs = (trip) =>
    trip.legs.map((leg, i) => ({
      train_id: leg.train_id,
      departure_station_id: leg.from_station_id,
      arrival_station_id: leg.to_station_id,
      travel_date: travelDate,
      // 1 pasager: trimite locul selectat (sau null = auto); >1 pasager: backend auto-asignează
      seat_ids: journeyPassengers.length === 1
        ? [journeySeats[i]?.seat_id ?? null]
        : null,
    }))

  const handleSelectJourney = async (trip) => {
    setSelectedJourney(trip)
    setJourneySeats(Array(trip.legs.length).fill(null))
    setOpenSeatLeg(null)
    setJourneyError(null)
    setJourneyQuote(null)
    setJourneyPassengers([{ passenger_name: null }])
    // Fetch quote pentru preview preț + reducere
    setJourneyQuoting(true)
    try {
      const legs = trip.legs.map((leg) => ({
        train_id: leg.train_id,
        departure_station_id: leg.from_station_id,
        arrival_station_id: leg.to_station_id,
        travel_date: travelDate,
        seat_id: null,
      }))
      const q = await quoteJourney({ legs, ticket_type: 'single' })
      setJourneyQuote(q)
    } catch {
      setJourneyQuote(null)
    } finally {
      setJourneyQuoting(false)
    }
  }

  const handleBuyJourney = async () => {
    if (!selectedJourney) return
    for (let i = 0; i < journeyPassengers.length; i++) {
      const pax = journeyPassengers[i]
      if (pax.passenger_name !== null && !(pax.passenger_name || '').trim()) {
        setJourneyError(`Completează numele pasagerului ${i + 1}.`)
        return
      }
    }
    setJourneySubmitting(true)
    setJourneyError(null)
    try {
      const legs = buildJourneyLegs(selectedJourney)
      const passengers = journeyPassengers.map(p => ({
        passenger_name: p.passenger_name === null ? null : (p.passenger_name || '').trim() || null,
      }))
      const r = await buyJourney({ legs, ticket_type: 'single', passengers })
      navigate('/tickets', { state: { newTicketId: r.ticket_id, count: r.leg_count * (r.passenger_count ?? 1) } })
    } catch (err) {
      setJourneyError(err.message)
    } finally {
      setJourneySubmitting(false)
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
        </div>

        {/* Lista trenuri */}
        {fromStation && toStation && (
          <div className="border-t border-slate-200 dark:border-slate-700 pt-5">
            <h2 className="text-sm font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-3">
              Trenuri directe ({trains.length})
            </h2>
            {searching && <div className="text-sm text-slate-500">Caut trenuri...</div>}
            {!searching && trains.length === 0 && (
              <div className="space-y-3">
                <div className="text-sm text-slate-500 p-3 rounded-xl border border-dashed border-slate-300 dark:border-slate-700">
                  Nu exista tren direct intre aceste statii.
                  {tripSuggestions.length > 0 && ' Iata cele mai bune itinerarii cu schimbare:'}
                </div>
                {suggestingTrips && (
                  <div className="text-xs text-slate-400">Caut alternative cu schimbare...</div>
                )}
                {!suggestingTrips && tripSuggestions.length === 0 && (
                  <div className="text-xs text-slate-400">
                    Nu am gasit nici itinerarii cu schimbare. Incearca alta data sau alta gara.
                  </div>
                )}
                {tripSuggestions.map((trip, idx) => {
                  const isSelected = selectedJourney === trip
                  return (
                    <div key={idx} className={`rounded-xl border p-3 space-y-2 transition ${
                      isSelected
                        ? 'border-emerald-400 bg-emerald-50 dark:bg-emerald-900/20'
                        : 'border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50'
                    }`}>
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-semibold text-slate-700 dark:text-slate-200">
                          {trip.transfer_count === 0 ? 'Direct' :
                           trip.transfer_count === 1 ? '1 schimbare' : `${trip.transfer_count} schimbari`}
                          {trip.transfer_stations && trip.transfer_stations.length > 0 && (
                            <span className="ml-1 text-slate-500">(prin {trip.transfer_stations.join(', ')})</span>
                          )}
                        </span>
                        <span className="text-slate-500">
                          {trip.departure_time?.slice(0,5)} {'->'} {trip.arrival_time?.slice(0,5)}
                          {' '}
                          <span className="font-mono">({Math.floor(trip.total_duration_min/60)}h{trip.total_duration_min%60 ? `${trip.total_duration_min%60}m` : ''})</span>
                        </span>
                      </div>
                      <div className="space-y-1.5">
                        {trip.legs.map((leg, li) => (
                          <div key={li} className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-300">
                            <span className="font-mono bg-slate-200 dark:bg-slate-700 px-2 py-0.5 rounded">
                              {fmtTrainType(leg.train_type) || 'T'} {leg.train_number}
                            </span>
                            <span className="flex-1 truncate">
                              {leg.from_station} {leg.departure_time?.slice(0,5)}
                              {' -> '}
                              {leg.to_station} {leg.arrival_time?.slice(0,5)}
                            </span>
                            <span className="text-slate-400">{leg.distance_km}km</span>
                          </div>
                        ))}
                      </div>
                      <div className="pt-1 border-t border-slate-200 dark:border-slate-700">
                        <button
                          type="button"
                          onClick={() => isSelected ? setSelectedJourney(null) : handleSelectJourney(trip)}
                          className={`text-xs font-semibold px-3 py-1.5 rounded-lg transition ${
                            isSelected
                              ? 'bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300'
                              : 'bg-emerald-600 hover:bg-emerald-700 text-white'
                          }`}
                        >
                          {isSelected ? 'Anuleaza selectia' : 'Cumpara journey'}
                        </button>
                      </div>

                      {/* Panou selectie locuri per leg (doar pentru journey selectata) */}
                      {isSelected && (
                        <div className="pt-2 space-y-3">
                          {trip.legs.map((leg, li) => (
                            <div key={li} className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-3">
                              <div className="flex items-center justify-between mb-2">
                                <div className="text-xs font-semibold text-slate-700 dark:text-slate-200">
                                  Leg {li + 1}: {fmtTrainType(leg.train_type)} {leg.train_number}
                                  <span className="ml-2 font-normal text-slate-500">
                                    {leg.from_station} → {leg.to_station}
                                  </span>
                                </div>
                                <div className="flex items-center gap-2">
                                  {journeySeats[li] && (
                                    <span className="text-xs font-mono bg-emerald-100 dark:bg-emerald-900/40 text-emerald-800 dark:text-emerald-200 px-2 py-0.5 rounded">
                                      V{journeySeats[li].car_number}-{journeySeats[li].label}
                                    </span>
                                  )}
                                  <button
                                    type="button"
                                    onClick={() => setOpenSeatLeg(openSeatLeg === li ? null : li)}
                                    className="text-xs px-2 py-1 rounded border border-slate-300 dark:border-slate-600 hover:bg-slate-100 dark:hover:bg-slate-800 transition"
                                  >
                                    {openSeatLeg === li ? 'Inchide harta' : journeySeats[li] ? 'Schimba locul' : 'Alege loc (optional)'}
                                  </button>
                                  {journeySeats[li] && (
                                    <button
                                      type="button"
                                      onClick={() => {
                                        const next = [...journeySeats]
                                        next[li] = null
                                        setJourneySeats(next)
                                      }}
                                      className="text-xs px-2 py-1 rounded border border-red-300 dark:border-red-700 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition"
                                    >
                                      Sterge
                                    </button>
                                  )}
                                </div>
                              </div>
                              {openSeatLeg === li && (
                                <SeatMap
                                  trainId={leg.train_id}
                                  travelDate={travelDate}
                                  maxSeats={1}
                                  onSelectionChange={(seats) => {
                                    const next = [...journeySeats]
                                    next[li] = seats[0] ?? null
                                    setJourneySeats(next)
                                    if (seats[0]) setOpenSeatLeg(null)
                                  }}
                                />
                              )}
                            </div>
                          ))}

                          {/* Preview preț + reducere */}
                          {journeyQuoting && (
                            <div className="text-xs text-slate-500 animate-pulse px-1">Calculez prețul...</div>
                          )}
                          {!journeyQuoting && journeyQuote && (() => {
                            const nPax = journeyPassengers.length
                            // oricare pasager cu passenger_name === null = titular (reducere)
                            const selfCount = journeyPassengers.filter(p => p.passenger_name === null).length
                            const selfIncluded = selfCount > 0
                            const showDiscount = journeyQuote.any_discount && selfIncluded
                            const othersPrice = journeyQuote.total_base
                            const grandTotal = selfCount * journeyQuote.total_final
                              + (nPax - selfCount) * journeyQuote.total_base
                            return (
                              <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 p-3 space-y-2 text-sm">
                                {journeyQuote.is_personal_route && selfIncluded ? (
                                  <div className="text-xs rounded-lg border border-emerald-300 dark:border-emerald-700 bg-emerald-50 dark:bg-emerald-900/20 px-3 py-2 text-emerald-800 dark:text-emerald-200">
                                    <span className="font-semibold">✓ Ruta ta personală.</span> Reducerea de student se aplică.
                                  </div>
                                ) : selfIncluded ? (
                                  <div className="text-xs rounded-lg border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/20 px-3 py-2 text-amber-800 dark:text-amber-200">
                                    <span className="font-semibold">⚠ Tarif întreg.</span> Ruta nu coincide cu traseul personal.
                                  </div>
                                ) : null}
                                {journeyQuote.legs.map((lq, li) => (
                                  <div key={li} className="flex justify-between text-xs text-slate-600 dark:text-slate-400">
                                    <span>Seg. {lq.leg_order} — {lq.departure_station} → {lq.arrival_station}</span>
                                    <span className="font-mono">
                                      {showDiscount && lq.discount_percent > 0 ? (
                                        <>
                                          <span className="line-through text-slate-400 mr-1">{lq.base_price.toFixed(2)}</span>
                                          <span className="text-emerald-600 dark:text-emerald-400">{lq.final_price.toFixed(2)} RON</span>
                                        </>
                                      ) : (
                                        <span>{(selfIncluded ? lq.final_price : lq.base_price).toFixed(2)} RON</span>
                                      )}
                                    </span>
                                  </div>
                                ))}
                                {nPax > 1 && (
                                  <div className="text-xs text-slate-500 dark:text-slate-400 border-t border-slate-200 dark:border-slate-700 pt-1 space-y-0.5">
                                    {journeyPassengers.map((p, i) => (
                                      <div key={i} className="flex justify-between">
                                        <span>
                                          {p.passenger_name === null
                                            ? 'Tu (titular)'
                                            : (p.passenger_name || '').trim() || `Pasager ${i + 1}`}
                                        </span>
                                        <span className="font-mono">
                                          {p.passenger_name === null
                                            ? journeyQuote.total_final.toFixed(2)
                                            : othersPrice.toFixed(2)} RON
                                        </span>
                                      </div>
                                    ))}
                                  </div>
                                )}
                                <div className="border-t border-slate-200 dark:border-slate-700 pt-2 flex justify-between items-baseline">
                                  <span className="font-bold text-slate-900 dark:text-slate-100">
                                    Total{nPax > 1 ? ` (${nPax} bilete)` : ''}:
                                  </span>
                                  <span className="font-bold text-lg font-mono text-emerald-600 dark:text-emerald-400">
                                    {grandTotal.toFixed(2)} RON
                                  </span>
                                </div>
                                {showDiscount && journeyQuote.total_savings > 0 && (
                                  <div className="text-xs text-emerald-600 dark:text-emerald-400 text-right">
                                    Economisești {journeyQuote.total_savings.toFixed(2)} RON ({journeyQuote.discount_percent}% reducere student)
                                  </div>
                                )}
                              </div>
                            )
                          })()}

                          {/* Pasageri: titular + posibil altcineva (max 4) */}
                          <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-3 space-y-2">
                            <div className="flex items-center justify-between">
                              <div className="text-xs font-semibold text-slate-600 dark:text-slate-300">
                                Pasageri ({journeyPassengers.length})
                              </div>
                              {journeyPassengers.length < 4 && (
                                <button
                                  type="button"
                                  onClick={() => setJourneyPassengers(prev => [...prev, { passenger_name: '' }])}
                                  className="text-xs text-emerald-600 dark:text-emerald-400 font-semibold hover:underline"
                                >
                                  + Adaugă pasager
                                </button>
                              )}
                            </div>
                            {journeyPassengers.map((pax, paxIdx) => (
                              <div key={paxIdx} className="space-y-1.5">
                                <div className="flex items-center gap-2">
                                  {/* Toggle pentru fiecare pasager: pentru mine / pentru altcineva */}
                                  <div className="flex-1 flex rounded-lg border border-slate-300 dark:border-slate-600 overflow-hidden text-xs font-semibold">
                                    <button
                                      type="button"
                                      onClick={() => setJourneyPassengers(prev =>
                                        prev.map((p, i) => i === paxIdx ? { passenger_name: null } : p)
                                      )}
                                      className={`flex-1 px-3 py-2 transition ${
                                        pax.passenger_name === null
                                          ? 'bg-emerald-600 text-white'
                                          : 'bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800'
                                      }`}
                                    >
                                      {paxIdx === 0 ? 'Pentru mine' : 'Pentru mine'}
                                    </button>
                                    <button
                                      type="button"
                                      onClick={() => setJourneyPassengers(prev =>
                                        prev.map((p, i) => i === paxIdx ? { passenger_name: '' } : p)
                                      )}
                                      className={`flex-1 px-3 py-2 transition border-l border-slate-300 dark:border-slate-600 ${
                                        pax.passenger_name !== null
                                          ? 'bg-emerald-600 text-white'
                                          : 'bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800'
                                      }`}
                                    >
                                      Pentru altcineva
                                    </button>
                                  </div>
                                  {paxIdx > 0 && (
                                    <button
                                      type="button"
                                      onClick={() => setJourneyPassengers(prev => prev.filter((_, i) => i !== paxIdx))}
                                      className="text-red-400 hover:text-red-600 dark:text-red-500 dark:hover:text-red-400 text-xs font-bold px-1 shrink-0"
                                    >✕</button>
                                  )}
                                </div>
                                {pax.passenger_name !== null && (
                                  <input
                                    type="text"
                                    value={pax.passenger_name || ''}
                                    onChange={(e) => setJourneyPassengers(prev =>
                                      prev.map((p, i) => i === paxIdx ? { passenger_name: e.target.value } : p)
                                    )}
                                    placeholder={`Pasager ${paxIdx + 1} — Nume și prenume *`}
                                    className={`w-full px-3 py-2 rounded-lg border bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 text-sm ${
                                      (pax.passenger_name || '').trim()
                                        ? 'border-slate-300 dark:border-slate-600'
                                        : 'border-red-400 dark:border-red-600'
                                    }`}
                                    maxLength={200}
                                  />
                                )}
                              </div>
                            ))}
                          </div>

                          {journeyError && (
                            <div className="text-xs text-red-600 dark:text-red-400 px-1">{journeyError}</div>
                          )}

                          <button
                            type="button"
                            disabled={journeySubmitting}
                            onClick={handleBuyJourney}
                            className="w-full bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white font-semibold rounded-xl px-4 py-3 transition"
                          >
                            {journeySubmitting ? 'Se procesează...' : (
                              journeyPassengers.length > 1
                                ? `Cumpără ${journeyPassengers.length} bilete cu ${trip.legs.length} segmente`
                                : `Cumpără bilet cu ${trip.legs.length} segmente`
                            )}
                          </button>
                        </div>
                      )}
                    </div>
                  )
                })}
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
          </div>
        )}

        {/* Preview tarif */}
        {selectedTrain && (
          <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 p-4">
            <div className="text-xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-2">Detalii tarif</div>
            {quoting && <div className="text-sm text-slate-500 animate-pulse">Calculez tariful...</div>}
            {!quoting && quote && (() => {
              const n = Math.max(1, selectedSeatIds.length)
              const selfIncluded = passengerConfigs.length === 0 || passengerConfigs.some(c => c.forMe)
              const priceHolder   = Number(quote.price_holder   ?? quote.final_price)
              const priceCompanion = Number(quote.price_companion ?? quote.base_price)
              const companions = n - (selfIncluded ? 1 : 0)
              const displayTotal = selfIncluded
                ? priceHolder + priceCompanion * companions
                : priceCompanion * n
              const showDiscount = quote.discount_percent > 0 && selfIncluded
              return (
              <div className="space-y-2.5 text-sm">
                {/* Banner cu statusul rutei personale */}
                {quote.is_personal_route ? (
                  <div className="rounded-lg border border-emerald-300 dark:border-emerald-700 bg-emerald-50 dark:bg-emerald-900/20 px-3 py-2 text-xs text-emerald-800 dark:text-emerald-200">
                    <span className="font-semibold">✓ Ruta ta personala.</span> {quote.route_reason}
                  </div>
                ) : (
                  <div className="rounded-lg border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/20 px-3 py-2 text-xs text-amber-800 dark:text-amber-200">
                    <span className="font-semibold">⚠ Tarif intreg.</span> {quote.route_reason}
                  </div>
                )}

                <div className="flex justify-between">
                  <span className="text-slate-600 dark:text-slate-400">Distanta:</span>
                  <span className="font-mono">{quote.distance_km?.toFixed?.(1) ?? quote.distance_km} km</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-600 dark:text-slate-400">Tarif normal:</span>
                  <span className="font-mono">{quote.base_price.toFixed(2)} RON</span>
                </div>
                {showDiscount && (
                  <>
                    <div className="flex justify-between text-emerald-600 dark:text-emerald-400">
                      <span>Reducere student {quote.discount_percent}% (titular):</span>
                      <span className="font-mono">-{quote.savings.toFixed(2)} RON</span>
                    </div>
                    {n > 1 && (
                      <div className="text-xs text-slate-500 dark:text-slate-400 italic pl-2">
                        Reducerea se aplica DOAR titularului. Insotitorii platesc tariful intreg.
                      </div>
                    )}
                  </>
                )}
                {!selfIncluded && quote.discount_percent > 0 && (
                  <div className="text-xs text-amber-600 dark:text-amber-400 italic pl-2">
                    Niciun loc nu este marcat ca „pentru mine" — reducerea de student nu se aplica.
                  </div>
                )}
                {n > 1 && (
                  <div className="space-y-1 text-slate-700 dark:text-slate-300">
                    {showDiscount ? (
                      <>
                        <div className="flex justify-between">
                          <span>Tu (titular, cu reducere):</span>
                          <span className="font-mono">{priceHolder.toFixed(2)} RON</span>
                        </div>
                        {companions > 0 && (
                          <div className="flex justify-between">
                            <span>{companions} insotitor{companions === 1 ? '' : 'i'} (tarif intreg):</span>
                            <span className="font-mono">{priceCompanion.toFixed(2)} RON x {companions}</span>
                          </div>
                        )}
                      </>
                    ) : (
                      <div className="flex justify-between">
                        <span>Pret per pasager:</span>
                        <span className="font-mono">{priceCompanion.toFixed(2)} RON x {n}</span>
                      </div>
                    )}
                  </div>
                )}
                <div className="border-t border-slate-200 dark:border-slate-700 mt-2 pt-2 flex justify-between items-baseline">
                  <span className="font-bold text-slate-900 dark:text-slate-100">
                    {n > 1 ? `Total (${n} pasageri):` : 'Platesti:'}
                  </span>
                  <span className="font-bold text-xl text-emerald-600 dark:text-emerald-400 font-mono">
                    {displayTotal.toFixed(2)} RON
                  </span>
                </div>
              </div>
              )
            })()}
          </div>
        )}

        {/* Recomandare abonament (afisata DOAR daca user-ul nu are abonament
            si a cumparat frecvent pe aceasta ruta). */}
        {quote?.subscription_recommendation && !coveringSubscription && (
          <div className="mb-4 p-4 rounded-2xl bg-gradient-to-br from-amber-50 to-orange-50 dark:from-amber-900/30 dark:to-orange-900/20 border-2 border-amber-400 dark:border-amber-600 text-amber-900 dark:text-amber-100">
            <div className="flex items-start gap-3">
              <span className="text-3xl">{"\uD83D\uDCA1"}</span>
              <div className="flex-1">
                <div className="font-bold mb-1">Sfat: economisesti cu abonament</div>
                <div className="text-sm mb-2">
                  {quote.subscription_recommendation.message}
                </div>
                <div className="flex flex-wrap gap-3 text-xs mb-3">
                  <span className="px-2 py-1 rounded-lg bg-amber-200/60 dark:bg-amber-800/40">
                    Bilete platite recent: <strong>{quote.subscription_recommendation.recent_tickets_count}</strong>
                  </span>
                  <span className="px-2 py-1 rounded-lg bg-amber-200/60 dark:bg-amber-800/40">
                    Cost abonament: <strong>{quote.subscription_recommendation.subscription_price.toFixed(0)} RON</strong>
                  </span>
                  <span className="px-2 py-1 rounded-lg bg-emerald-200/60 dark:bg-emerald-800/40 text-emerald-900 dark:text-emerald-100">
                    Economie estimata: <strong>{quote.subscription_recommendation.estimated_saving_ron.toFixed(0)} RON</strong>
                  </span>
                </div>
                <Link
                  to={`/subscriptions?from_station_id=${fromStation?.station_id}&to_station_id=${toStation?.station_id}&suggested=monthly`}
                  className="inline-block px-4 py-2 rounded-xl bg-amber-600 hover:bg-amber-700 text-white text-sm font-semibold"
                >
                  Cumpara abonament lunar in loc
                </Link>
              </div>
            </div>
          </div>
        )}

        {coveringSubscription && (
          <div className="mb-4 p-4 rounded-2xl bg-emerald-50 dark:bg-emerald-900/30 border-2 border-emerald-400 dark:border-emerald-600 text-emerald-900 dark:text-emerald-100">
            <div className="flex items-start gap-3">
              <span className="text-2xl">🎫</span>
              <div className="flex-1">
                <div className="font-bold mb-1">Acoperit de abonament</div>
                <div className="text-sm">
                  Aveti abonament {coveringSubscription.subscription_type === 'monthly' ? 'lunar' : 'anual'} activ pe aceasta ruta (valabil pana pe {coveringSubscription.valid_until}).
                  <strong> Biletul va fi GRATUIT (0 RON)</strong> si va fi inregistrat ca utilizare a abonamentului.
                </div>
              </div>
            </div>
          </div>
        )}

        {selectedTrain && travelDate && fromStation?.station_id && toStation?.station_id && (
          <div className="mt-6 p-4 rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700">
            <h3 className="text-lg font-bold mb-3 text-slate-900 dark:text-slate-100">
              Alege locurile (optional)
            </h3>
            <SeatMap
              trainId={selectedTrain.train_id}
              travelDate={travelDate}
              onSelectionChange={setSelectedSeatDetails}
              maxSeats={4}
            />

            {selectedSeatDetails.length > 0 && (
              <div className="mt-5 pt-4 border-t border-slate-200 dark:border-slate-700">
                <h4 className="text-base font-bold mb-3 text-slate-900 dark:text-slate-100">
                  Pasageri ({selectedSeatDetails.length})
                </h4>
                <div className="space-y-3">
                  {selectedSeatDetails.map((s, idx) => {
                    const cfg = passengerConfigs[idx] || { forMe: false, name: '' }
                    const alreadySelf = passengerConfigs.some((c, i) => c.forMe && i !== idx)
                    const setConfig = (patch) => {
                      setPassengerConfigs(prev => {
                        const next = prev.map((c, i) => i === idx ? { ...c, ...patch } : c)
                        // max 1 "pentru mine"
                        if (patch.forMe) {
                          return next.map((c, i) => i === idx ? c : { ...c, forMe: false })
                        }
                        return next
                      })
                    }
                    return (
                      <div key={s.seat_id} className="rounded-xl border border-slate-200 dark:border-slate-700 p-3 space-y-2">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-mono bg-emerald-100 dark:bg-emerald-900/40 text-emerald-800 dark:text-emerald-200 px-2 py-1 rounded font-semibold">
                            V{s.car_number}-{s.label}
                          </span>
                          {/* Toggle */}
                          <div className="flex rounded-lg border border-slate-300 dark:border-slate-600 overflow-hidden text-xs font-semibold">
                            <button
                              type="button"
                              onClick={() => setConfig({ forMe: true })}
                              disabled={alreadySelf}
                              className={`px-3 py-1.5 transition ${
                                cfg.forMe
                                  ? 'bg-emerald-600 text-white'
                                  : alreadySelf
                                    ? 'bg-slate-100 dark:bg-slate-800 text-slate-400 cursor-not-allowed'
                                    : 'bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800'
                              }`}
                            >
                              Pentru mine
                            </button>
                            <button
                              type="button"
                              onClick={() => setConfig({ forMe: false })}
                              className={`px-3 py-1.5 transition border-l border-slate-300 dark:border-slate-600 ${
                                !cfg.forMe
                                  ? 'bg-emerald-600 text-white'
                                  : 'bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800'
                              }`}
                            >
                              Pentru altcineva
                            </button>
                          </div>
                          {cfg.forMe && (
                            <span className="text-[10px] text-emerald-600 dark:text-emerald-400 font-semibold">
                              reducere automată
                            </span>
                          )}
                        </div>
                        {!cfg.forMe && (
                          <input
                            type="text"
                            value={cfg.name}
                            onChange={(e) => setConfig({ name: e.target.value })}
                            placeholder="Nume si prenume pasager *"
                            className={`w-full px-3 py-2 rounded-lg border bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 text-sm ${
                              (cfg.name || '').trim()
                                ? 'border-slate-300 dark:border-slate-600'
                                : 'border-red-400 dark:border-red-600'
                            }`}
                            maxLength={200}
                          />
                        )}
                      </div>
                    )
                  })}
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
