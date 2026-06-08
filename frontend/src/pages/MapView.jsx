import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { MapContainer, TileLayer, CircleMarker, Polyline, Popup, useMap } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import {
  getMapStations,
  getMapConnections,
  getMapOperators,
  simulateTrainPosition,
  searchTrains,
} from '../services/api'

// Centrul Romaniei + zoom optim
const ROMANIA_CENTER = [45.9432, 24.9668]
const ROMANIA_ZOOM = 7

function StationMarker({ s, onSelect, isSelected, departureSet, arrivalSet }) {
  const isUni = s.is_university_hub
  const radius = isUni ? Math.min(20, 6 + Math.log10(Math.max(s.student_count || 1, 1)) * 3) : 5
  let color = isUni ? '#3b82f6' : '#64748b'  // blue uni, slate hub
  if (s === departureSet) color = '#10b981'   // green = plecare
  if (s === arrivalSet) color = '#ef4444'     // red = sosire

  return (
    <CircleMarker
      center={[s.latitude, s.longitude]}
      radius={radius}
      pathOptions={{
        color: isSelected ? '#f59e0b' : color,
        fillColor: color,
        fillOpacity: isUni ? 0.7 : 0.5,
        weight: isSelected ? 3 : 1.5,
      }}
      eventHandlers={{
        click: () => onSelect(s),
      }}
    >
      <Popup>
        <div className="text-sm space-y-1 min-w-[200px]">
          <div className="font-bold text-base">{s.name}</div>
          <div className="text-xs text-slate-500">{s.city} · {s.code}</div>
          {isUni && (
            <div className="mt-2 p-2 bg-blue-50 rounded text-xs">
              <div className="font-semibold text-blue-700">
                🎓 {s.universities_count} universități · {(s.student_count || 0).toLocaleString()} studenți
              </div>
              <div className="text-blue-600 mt-1">{s.notes}</div>
            </div>
          )}
          <div className="text-xs text-slate-600 mt-2">
            🚂 <strong>{s.trains_count}</strong> trenuri active deservesc această stație
          </div>
        </div>
      </Popup>
    </CircleMarker>
  )
}

function TrainMarker({ position }) {
  if (!position?.current_lat || !position?.current_lon) return null
  return (
    <CircleMarker
      center={[position.current_lat, position.current_lon]}
      radius={10}
      pathOptions={{
        color: '#dc2626',
        fillColor: '#fbbf24',
        fillOpacity: 0.9,
        weight: 3,
      }}
    >
      <Popup>
        <div className="text-sm space-y-1">
          <div className="font-bold">🚂 {position.train_type?.toUpperCase()} {position.train_number}</div>
          <div className="text-xs text-slate-500">{position.operator}</div>
          <div className="text-xs">
            <strong>Status:</strong> {position.status === 'in_transit' ? 'În deplasare' :
              position.status === 'not_departed' ? 'Nu a plecat încă' :
              position.status === 'arrived' ? 'Sosit la destinație' : position.status}
          </div>
          <div className="text-xs">
            <strong>Acum între:</strong> {position.current_station} → {position.next_station || '(final)'}
          </div>
          <div className="text-xs">
            <strong>Progres segment:</strong> {position.progress_percent}%
          </div>
        </div>
      </Popup>
    </CircleMarker>
  )
}

function FitBounds({ stations }) {
  const map = useMap()
  useEffect(() => {
    if (stations.length === 0) return
    const bounds = stations
      .filter(s => s.latitude && s.longitude)
      .map(s => [s.latitude, s.longitude])
    if (bounds.length > 0) {
      map.fitBounds(bounds, { padding: [40, 40] })
    }
  }, [stations, map])
  return null
}

export default function MapView() {
  const navigate = useNavigate()
  // Doar passenger poate cumpara bilete - ascundem butonul pentru alte roluri
  const currentUserRole = (() => {
    try {
      const u = JSON.parse(localStorage.getItem('user') || '{}')
      return u?.role || null
    } catch { return null }
  })()
  const canBuyTickets = currentUserRole === 'passenger'
  const [stations, setStations] = useState([])
  const [connections, setConnections] = useState([])
  const [operators, setOperators] = useState([])
  const [loading, setLoading] = useState(true)
  const [filterOperator, setFilterOperator] = useState('')
  const [onlyUniversity, setOnlyUniversity] = useState(true)
  const [selected, setSelected] = useState(null)
  const [departure, setDeparture] = useState(null)
  const [arrival, setArrival] = useState(null)
  const [trainsBetween, setTrainsBetween] = useState([])
  const [animatedTrain, setAnimatedTrain] = useState(null)
  const [trainPosition, setTrainPosition] = useState(null)
  const animationTimerRef = useRef(null)

  // Initial load
  useEffect(() => {
    let alive = true
    setLoading(true)
    Promise.all([
      getMapStations({ only_university: onlyUniversity, operator_id: filterOperator || null }),
      getMapConnections({ min_trains: 1, only_university: onlyUniversity, operator_id: filterOperator || null }),
      getMapOperators(),
    ])
      .then(([s, c, o]) => {
        if (!alive) return
        setStations(s || [])
        setConnections(c || [])
        setOperators(o || [])
      })
      .catch(err => console.error('Map load error:', err))
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [onlyUniversity, filterOperator])

  // Cand userul selecteaza plecare + sosire, caut trenurile directe
  useEffect(() => {
    if (!departure || !arrival || departure.station_id === arrival.station_id) {
      setTrainsBetween([])
      return
    }
    let alive = true
    searchTrains(departure.station_id, arrival.station_id)
      .then(r => { if (alive) setTrainsBetween(r || []) })
      .catch(() => { if (alive) setTrainsBetween([]) })
    return () => { alive = false }
  }, [departure, arrival])

  // Animatie pozitie tren la 5 secunde
  useEffect(() => {
    if (!animatedTrain) {
      setTrainPosition(null)
      if (animationTimerRef.current) clearInterval(animationTimerRef.current)
      return
    }
    const tick = () => {
      simulateTrainPosition(animatedTrain.train_id)
        .then(p => setTrainPosition(p))
        .catch(() => {})
    }
    tick()
    animationTimerRef.current = setInterval(tick, 5000)
    return () => clearInterval(animationTimerRef.current)
  }, [animatedTrain])

  const handleStationClick = (s) => {
    setSelected(s)
    if (!departure) {
      setDeparture(s)
    } else if (!arrival && s.station_id !== departure.station_id) {
      setArrival(s)
    } else {
      // reset
      setDeparture(s)
      setArrival(null)
      setTrainsBetween([])
      setAnimatedTrain(null)
    }
  }

  const handleBuyTicket = () => {
    if (!departure || !arrival) return
    // Trecem prin location state catre BuyTicket
    navigate('/tickets/buy', {
      state: {
        prefillFrom: departure,
        prefillTo: arrival,
      },
    })
  }

  return (
    <div className="container mx-auto px-4 py-6 max-w-7xl">
      <div className="mb-4">
        <h1 className="text-3xl font-bold text-slate-900 dark:text-slate-50 mb-2">
          Harta centrelor universitare
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          {stations.length} stații (din 1818) cu coordonate GPS · {connections.length} conexiuni directe
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-4">
        {/* HARTA */}
        <div className="rounded-2xl overflow-hidden border border-slate-200 dark:border-slate-700 shadow-sm bg-white dark:bg-slate-900" style={{ height: '70vh', minHeight: 500 }}>
          {loading ? (
            <div className="h-full flex items-center justify-center text-slate-500">
              Încărcare hartă...
            </div>
          ) : (
            <MapContainer center={ROMANIA_CENTER} zoom={ROMANIA_ZOOM} style={{ height: '100%', width: '100%' }}>
              <TileLayer
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              />
              <FitBounds stations={stations} />

              {/* Conexiuni — linii subtiri intre statii */}
              {connections.map((c, i) => {
                const opacity = Math.min(0.6, 0.1 + c.trains_count / 100)
                const weight = Math.min(4, 1 + c.trains_count / 30)
                return (
                  <Polyline
                    key={`${c.from_id}-${c.to_id}-${i}`}
                    positions={[[c.from_lat, c.from_lon], [c.to_lat, c.to_lon]]}
                    pathOptions={{ color: '#3b82f6', opacity, weight }}
                  />
                )
              })}

              {/* Pin-uri statii */}
              {stations.map(s => (
                <StationMarker
                  key={s.station_id}
                  s={s}
                  onSelect={handleStationClick}
                  isSelected={selected?.station_id === s.station_id}
                  departureSet={departure}
                  arrivalSet={arrival}
                />
              ))}

              {/* Pin animat tren */}
              <TrainMarker position={trainPosition} />
            </MapContainer>
          )}
        </div>

        {/* SIDEBAR */}
        <div className="space-y-4">
          {/* Filtre */}
          <div className="rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 p-4 shadow-sm">
            <h2 className="font-bold text-sm uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-3">Filtre</h2>
            <label className="flex items-center gap-2 text-sm mb-3 cursor-pointer">
              <input
                type="checkbox"
                checked={onlyUniversity}
                onChange={(e) => setOnlyUniversity(e.target.checked)}
                className="rounded"
              />
              <span className="text-slate-700 dark:text-slate-200">Doar centre universitare</span>
            </label>
            <label className="block text-xs font-semibold text-slate-600 dark:text-slate-300 mb-1">Operator</label>
            <select
              value={filterOperator}
              onChange={(e) => setFilterOperator(e.target.value)}
              className="w-full text-sm rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-2 py-1.5"
            >
              <option value="">Toți operatorii</option>
              {operators.map(op => (
                <option key={op.operator_id} value={op.operator_id}>
                  {op.name} ({op.trains_count} trenuri)
                </option>
              ))}
            </select>
          </div>

          {/* Selecție călătorie */}
          <div className="rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 p-4 shadow-sm">
            <h2 className="font-bold text-sm uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-3">Călătorie</h2>
            <div className="space-y-2 text-sm">
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-full bg-emerald-500"></span>
                <span className="text-slate-600 dark:text-slate-400 text-xs">Plecare:</span>
                <span className="font-semibold text-slate-900 dark:text-slate-100 truncate">
                  {departure?.name || '— click pe hartă —'}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-full bg-red-500"></span>
                <span className="text-slate-600 dark:text-slate-400 text-xs">Sosire:</span>
                <span className="font-semibold text-slate-900 dark:text-slate-100 truncate">
                  {arrival?.name || '— click pe hartă —'}
                </span>
              </div>
              {(departure || arrival) && (
                <button
                  onClick={() => { setDeparture(null); setArrival(null); setSelected(null); setTrainsBetween([]); setAnimatedTrain(null) }}
                  className="text-xs text-slate-500 hover:text-slate-700 dark:hover:text-slate-200 underline"
                >
                  Reset selecție
                </button>
              )}
            </div>
            {departure && arrival && canBuyTickets && (
              <button
                onClick={handleBuyTicket}
                className="w-full mt-3 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-semibold rounded-xl px-3 py-2 transition"
              >
                💳 Cumpără bilet pentru această rută
              </button>
            )}
          </div>

          {/* Trenuri pe ruta */}
          {trainsBetween.length > 0 && (
            <div className="rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 p-4 shadow-sm">
              <h2 className="font-bold text-sm uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-3">
                {trainsBetween.length} trenuri directe
              </h2>
              <div className="space-y-1 max-h-64 overflow-y-auto">
                {trainsBetween.slice(0, 15).map(t => (
                  <button
                    key={t.train_id}
                    onClick={() => setAnimatedTrain(t)}
                    className={`w-full text-left text-xs p-2 rounded-lg border transition ${
                      animatedTrain?.train_id === t.train_id
                        ? 'border-amber-400 bg-amber-50 dark:bg-amber-900/20'
                        : 'border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800'
                    }`}
                  >
                    <div className="font-semibold text-slate-900 dark:text-slate-100">
                      {t.train_type?.toUpperCase()} {t.train_number}
                    </div>
                    <div className="text-slate-500 dark:text-slate-400">
                      {t.departure_time?.slice(0,5)} → {t.arrival_time?.slice(0,5)} · {t.operator_name}
                    </div>
                  </button>
                ))}
              </div>
              {animatedTrain && (
                <p className="text-xs text-amber-700 dark:text-amber-400 mt-2">
                  📡 Pozitia trenului se actualizează la 5 secunde
                </p>
              )}
            </div>
          )}

          {/* Legendă */}
          <div className="rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 p-4 shadow-sm">
            <h2 className="font-bold text-sm uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-3">Legendă</h2>
            <div className="space-y-1.5 text-xs">
              <div className="flex items-center gap-2">
                <span className="w-4 h-4 rounded-full bg-blue-500 opacity-70"></span>
                <span className="text-slate-700 dark:text-slate-300">Centru universitar (mărime = nr. studenți)</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-full bg-slate-500 opacity-50"></span>
                <span className="text-slate-700 dark:text-slate-300">Hub feroviar</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-full bg-emerald-500"></span>
                <span className="text-slate-700 dark:text-slate-300">Plecare selectată</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-full bg-red-500"></span>
                <span className="text-slate-700 dark:text-slate-300">Sosire selectată</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-full bg-amber-400 border-2 border-red-600"></span>
                <span className="text-slate-700 dark:text-slate-300">Tren în deplasare (simulat)</span>
              </div>
            </div>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-3 italic">
              Pozițiile trenurilor sunt simulate prin interpolare pe orarul oficial.
              Sursă: feed GTFS static CFR (data.gov.ro). În producție: GTFS-Realtime.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
