import { useEffect, useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { MapContainer, TileLayer, CircleMarker, Popup, Polyline, useMap } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { getMapStations, getRouteGeometry } from '../services/api'
import { fmtTrainType } from '../utils/trainType'

const ROMANIA_CENTER = [45.9432, 24.9668]
const ROMANIA_ZOOM = 7
const LEG_COLORS = ['#10b981', '#f59e0b', '#8b5cf6']

function FitBounds({ points }) {
  const map = useMap()
  useEffect(() => {
    if (!points?.length) return
    map.fitBounds(points, { padding: [60, 60], maxZoom: 12 })
  }, [points, map])
  return null
}

function PanTo({ coords }) {
  const map = useMap()
  useEffect(() => {
    if (!coords) return
    map.setView(coords, Math.max(map.getZoom(), 11), { animate: true })
  }, [coords, map])
  return null
}

function StationMarker({ s, isFrom, isTo, isStop, isIntermediate, isSearch, onClick }) {
  const isUni = s.is_university_hub
  const isHighlighted = isFrom || isTo || isStop || isIntermediate || isSearch

  const radius = isFrom || isTo ? 10
    : isSearch ? 10
    : isStop ? 7
    : isIntermediate ? 6
    : isUni ? Math.min(14, 5 + Math.log10(Math.max(s.student_count || 1, 1)) * 3)
    : 4

  const color = isFrom ? '#10b981'
    : isTo ? '#ef4444'
    : isSearch ? '#f97316'
    : isStop ? '#f59e0b'
    : isIntermediate ? '#a855f7'
    : isUni ? '#3b82f6'
    : '#94a3b8'

  return (
    <CircleMarker
      center={[s.latitude, s.longitude]}
      radius={radius}
      pathOptions={{
        color: isHighlighted ? '#fff' : color,
        fillColor: color,
        fillOpacity: isHighlighted ? 1 : isUni ? 0.75 : 0.45,
        weight: isHighlighted ? 2.5 : 1,
      }}
      eventHandlers={{ click: () => onClick(s) }}
    >
      <Popup>
        <div className="text-sm min-w-[180px] space-y-1">
          <div className="font-bold">{s.name}</div>
          <div className="text-xs text-slate-500">{s.city} · {s.code}</div>
          {isUni && (
            <div className="mt-1 p-1.5 bg-blue-50 rounded text-xs text-blue-700">
              {s.universities_count} univ. · {(s.student_count || 0).toLocaleString()} studenți
            </div>
          )}
        </div>
      </Popup>
    </CircleMarker>
  )
}

function StationSearchBox({ label, value, onChange, results, focus, onFocus, onBlur, onSelect, onClear, placeholder, accent }) {
  return (
    <div className="relative flex-1 min-w-0">
      <div className="relative">
        <span className={`absolute left-3 top-1/2 -translate-y-1/2 w-2.5 h-2.5 rounded-full ${accent} shrink-0`} />
        <input
          type="text"
          value={value}
          onChange={e => onChange(e.target.value)}
          onFocus={onFocus}
          onBlur={onBlur}
          placeholder={placeholder}
          className="w-full pl-8 pr-7 py-2 text-sm rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
        {value && (
          <button
            onMouseDown={e => { e.preventDefault(); onClear() }}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 text-xs leading-none"
          >✕</button>
        )}
      </div>
      {focus && results.length > 0 && (
        <div className="absolute top-full mt-1 w-full bg-white dark:bg-slate-800 rounded-xl shadow-lg border border-slate-200 dark:border-slate-700 z-[2000] overflow-hidden">
          {results.map(s => (
            <button key={s.station_id} onMouseDown={() => onSelect(s)}
              className="w-full text-left px-4 py-2.5 text-sm hover:bg-slate-50 dark:hover:bg-slate-700 border-b border-slate-100 dark:border-slate-700 last:border-0">
              <div className="font-medium text-slate-900 dark:text-slate-100">{s.name}</div>
              {s.city && <div className="text-xs text-slate-400">{s.city}</div>}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function distKm([la1, lo1], [la2, lo2]) {
  const R = 6371
  const dLat = (la2 - la1) * Math.PI / 180
  const dLon = (lo2 - lo1) * Math.PI / 180
  const a = Math.sin(dLat/2)**2 +
    Math.cos(la1 * Math.PI/180) * Math.cos(la2 * Math.PI/180) * Math.sin(dLon/2)**2
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a))
}

const MAX_JUMP_KM = 200
// Dacă detour-ul A→B→C este >3x mai lung decât direct A→C, B este un spike GPS.
// Pragul 3x permite curbe reale ale traseului (ratio tipic 1.2–1.8) dar elimina
// varfurile cauzate de statii cu GPS incorect (ratio 5–15x).
const MAX_SPIKE_RATIO = 3.0

function filterOutliers(pts) {
  if (pts.length <= 2) return pts
  // Pasul 1: elimina salturile catastrofale (GPS in alta tara).
  let result = [pts[0]]
  for (let i = 1; i < pts.length; i++) {
    if (distKm(result[result.length - 1], pts[i]) <= MAX_JUMP_KM) result.push(pts[i])
  }
  // Pasul 2: elimina spike-urile (A→B→C unde detour >> direct).
  if (result.length > 2) {
    const clean = [result[0]]
    for (let i = 1; i < result.length - 1; i++) {
      const prev = clean[clean.length - 1]
      const curr = result[i]
      const next = result[i + 1]
      const direct = distKm(prev, next)
      if (direct > 0.5 && distKm(prev, curr) + distKm(curr, next) > MAX_SPIKE_RATIO * direct) continue
      clean.push(curr)
    }
    clean.push(result[result.length - 1])
    result = clean
  }
  return result
}

function buildLegLines(route) {
  if (!route?.legs?.length) return []
  return route.legs.map((leg, i) => {
    // Polyline-ul urmeaza sina reala: foloseste TOATE statiile cu GPS de pe leg
    // (inclusiv tehnice de trecere), care vin in `geometry_points`. Fallback la
    // `stops` doar daca backend-ul nu trimite geometry_points (compat. legacy).
    const source = (leg.geometry_points && leg.geometry_points.length)
      ? leg.geometry_points
      : (leg.stops || [])
    const allPts = source
      .filter(s => s.lat != null && s.lon != null)
      .map(s => [s.lat, s.lon])
    const pts = filterOutliers(allPts)
    return { pts, color: LEG_COLORS[i % LEG_COLORS.length] }
  }).filter(l => l.pts.length >= 2)
}

function getKeyStops(route, from, to) {
  if (!route?.legs?.length) return []
  const key = []
  if (from?.latitude && from?.longitude)
    key.push({ ...from, _role: 'from' })
  for (let i = 0; i < route.legs.length - 1; i++) {
    const stops = route.legs[i].stops || []
    const last = stops[stops.length - 1]
    if (last?.lat != null && last?.lon != null)
      key.push({ station_id: last.station_id, name: last.station_name || last.name,
                 latitude: last.lat, longitude: last.lon, _role: 'transfer' })
  }
  if (to?.latitude && to?.longitude)
    key.push({ ...to, _role: 'to' })
  return key
}

export default function MapView() {
  const navigate = useNavigate()
  const userRole = (() => {
    try { return JSON.parse(localStorage.getItem('user') || '{}')?.role }
    catch { return null }
  })()

  const [stations, setStations] = useState([])
  const [loading, setLoading] = useState(true)
  const [showRailLayer, setShowRailLayer] = useState(true)

  const [from, setFrom] = useState(null)
  const [to, setTo] = useState(null)
  const [route, setRoute] = useState(null)
  const [routeLoading, setRouteLoading] = useState(false)
  const [routeError, setRouteError] = useState(null)

  const [fromQ, setFromQ] = useState('')
  const [toQ, setToQ] = useState('')
  const [fromResults, setFromResults] = useState([])
  const [toResults, setToResults] = useState([])
  const [fromFocus, setFromFocus] = useState(false)
  const [toFocus, setToFocus] = useState(false)
  const [panTo, setPanTo] = useState(null)
  const [highlightId, setHighlightId] = useState(null)

  const keyStops = getKeyStops(route, from, to)
  const transferIds = new Set(keyStops.filter(s => s._role === 'transfer').map(s => s.station_id))
  // OPRIRI COMERCIALE pe rută — stațiile unde trenul chiar oprește pentru
  // îmbarcare/debarcare. Sursa autoritativă este flag-ul `is_commercial_stop`
  // populat la import din atributul XML CFR `TipOprire` ("C"=comercial, "N"=nod
  // tehnic). Capetele de leg sunt mereu opriri (origin/terminus tren).
  // Excludem plecarea/sosirea/transferurile ca să nu suprascriem culorile lor.
  const intermediateIds = (() => {
    const ids = new Set()
    if (!route?.legs?.length) return ids
    for (const leg of route.legs) {
      const stops = leg.stops || []
      for (let i = 0; i < stops.length; i++) {
        const stop = stops[i]
        if (!stop?.station_id) continue
        const isLegEndpoint = (i === 0) || (i === stops.length - 1)
        const isCommercial = stop.is_commercial_stop === true
        if (isCommercial || isLegEndpoint) {
          ids.add(stop.station_id)
        }
      }
    }
    if (from?.station_id) ids.delete(from.station_id)
    if (to?.station_id) ids.delete(to.station_id)
    for (const tid of transferIds) ids.delete(tid)
    return ids
  })()
  const legLines = buildLegLines(route)
  const fitPoints = legLines.flatMap(l => l.pts)

  useEffect(() => {
    let alive = true
    setLoading(true)
    getMapStations({})
      .then(data => { if (alive) setStations(data || []) })
      .catch(() => {})
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [])

  useEffect(() => {
    if (!from || !to || from.station_id === to.station_id) {
      setRoute(null); setRouteError(null); return
    }
    let alive = true
    setRouteLoading(true); setRouteError(null)
    getRouteGeometry({ from_station_id: from.station_id, to_station_id: to.station_id })
      .then(g => {
        if (!alive) return
        if (g?.found) setRoute(g)
        else { setRoute(null); setRouteError('Nu există rută între aceste stații.') }
      })
      .catch(() => { if (alive) { setRoute(null); setRouteError('Eroare la calculul rutei.') } })
      .finally(() => { if (alive) setRouteLoading(false) })
    return () => { alive = false }
  }, [from, to])

  // Sincronizare text boxes cu selecția de pe hartă
  useEffect(() => { setFromQ(from?.name || '') }, [from])
  useEffect(() => { setToQ(to?.name || '') }, [to])

  // Autocomplete plecare
  useEffect(() => {
    if (!fromQ.trim() || fromQ.length < 2 || fromQ === from?.name) { setFromResults([]); return }
    const q = fromQ.toLowerCase()
    setFromResults(stations.filter(s => s.name.toLowerCase().includes(q) || (s.city || '').toLowerCase().includes(q)).slice(0, 8))
  }, [fromQ, from, stations])

  // Autocomplete destinație
  useEffect(() => {
    if (!toQ.trim() || toQ.length < 2 || toQ === to?.name) { setToResults([]); return }
    const q = toQ.toLowerCase()
    setToResults(stations.filter(s => s.name.toLowerCase().includes(q) || (s.city || '').toLowerCase().includes(q)).slice(0, 8))
  }, [toQ, to, stations])

  const handleStationClick = (s) => {
    if (!from) { setFrom(s); return }
    if (s.station_id === from.station_id) { setFrom(null); setTo(null); setRoute(null); return }
    if (!to) { setTo(s); return }
    setFrom(s); setTo(null); setRoute(null); setRouteError(null)
  }

  const handleFromSelect = (s) => {
    setFrom(s)
    setFromResults([])
    setPanTo([s.latitude, s.longitude])
    setHighlightId(s.station_id)
    setTimeout(() => setHighlightId(null), 2000)
  }

  const handleToSelect = (s) => {
    setTo(s)
    setToResults([])
    setPanTo([s.latitude, s.longitude])
    setHighlightId(s.station_id)
    setTimeout(() => setHighlightId(null), 2000)
  }

  const handleReset = () => {
    setFrom(null); setTo(null); setRoute(null); setRouteError(null)
    setFromQ(''); setToQ('')
  }

  const fmtDuration = (min) => {
    if (!min) return ''
    const h = Math.floor(min / 60), m = min % 60
    return h > 0 ? `${h}h${m ? ` ${m}m` : ''}` : `${m}m`
  }

  return (
    <div className="flex flex-col bg-slate-100 dark:bg-slate-950 lg:h-[calc(100vh-64px)]">
      {/* Titlu + controale */}
      <div className="px-4 lg:px-6 pt-4 lg:pt-5 pb-3 shrink-0">
        <div className="flex flex-col gap-2 lg:flex-row lg:flex-wrap lg:items-center lg:gap-4">
          <div className="flex items-center justify-between lg:block shrink-0">
            <h1 className="text-lg lg:text-xl font-bold text-slate-900 dark:text-slate-50">Harta rețelei feroviare</h1>
            {/* Controale vizibile doar pe mobil, lângă titlu */}
            <div className="flex items-center gap-3 text-sm lg:hidden">
              <label className="flex items-center gap-1.5 cursor-pointer select-none text-slate-600 dark:text-slate-300">
                <input type="checkbox" checked={showRailLayer} onChange={e => setShowRailLayer(e.target.checked)} className="rounded" />
                <span className="text-xs">CFR</span>
              </label>
              {(from || to) && (
                <button onClick={handleReset} className="text-xs text-red-500 hover:text-red-700 underline">Resetează</button>
              )}
            </div>
          </div>

          {/* Două search boxes: Plecare + Destinație */}
          <div className="flex items-center gap-2 min-w-0 lg:flex-1 lg:max-w-2xl">
            <StationSearchBox
              label="Plecare"
              placeholder="Stație de plecare..."
              value={fromQ}
              onChange={v => { setFromQ(v); if (!v) setFrom(null) }}
              results={fromResults}
              focus={fromFocus}
              onFocus={() => setFromFocus(true)}
              onBlur={() => setTimeout(() => setFromFocus(false), 150)}
              onSelect={handleFromSelect}
              onClear={() => { setFrom(null); setFromQ('') }}
              accent="bg-emerald-500"
            />

            <svg className="w-5 h-5 text-slate-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" />
            </svg>

            <StationSearchBox
              label="Destinație"
              placeholder="Stație de destinație..."
              value={toQ}
              onChange={v => { setToQ(v); if (!v) setTo(null) }}
              results={toResults}
              focus={toFocus}
              onFocus={() => setToFocus(true)}
              onBlur={() => setTimeout(() => setToFocus(false), 150)}
              onSelect={handleToSelect}
              onClear={() => { setTo(null); setToQ('') }}
              accent="bg-red-500"
            />
          </div>

          {/* Controale desktop */}
          <div className="hidden lg:flex items-center gap-4 text-sm shrink-0">
            <label className="flex items-center gap-1.5 cursor-pointer select-none text-slate-600 dark:text-slate-300">
              <input type="checkbox" checked={showRailLayer} onChange={e => setShowRailLayer(e.target.checked)} className="rounded" />
              Căi ferate
            </label>
            {(from || to) && (
              <button onClick={handleReset} className="text-xs text-red-500 hover:text-red-700 underline">Resetează</button>
            )}
          </div>
        </div>
      </div>

      {/* Layout hartă + sidebar */}
      <div className="flex flex-col lg:flex-row gap-3 lg:gap-4 px-4 lg:px-6 pb-4 lg:pb-6 lg:flex-1 lg:min-h-0 lg:overflow-hidden">
        <div className="relative rounded-2xl overflow-hidden shadow-md border border-slate-200 dark:border-slate-700 h-[45vh] min-h-[260px] lg:flex-1 lg:h-auto lg:min-h-[400px]">
          {loading ? (
            <div className="h-full flex items-center justify-center text-slate-500 text-sm">Încărcare stații...</div>
          ) : (
            <MapContainer center={ROMANIA_CENTER} zoom={ROMANIA_ZOOM} style={{ height: '100%', width: '100%' }}>
              <TileLayer
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              />
              {showRailLayer && (
                <TileLayer
                  url="https://{s}.tiles.openrailwaymap.org/standard/{z}/{x}/{y}.png"
                  attribution='&copy; <a href="https://www.openrailwaymap.org/">OpenRailwayMap</a> (CC-BY-SA)'
                  subdomains="abc" minZoom={2} maxZoom={19} opacity={0.7} crossOrigin="anonymous"
                />
              )}

              {fitPoints.length > 0 && <FitBounds points={fitPoints} />}
              {panTo && <PanTo coords={panTo} />}

              {legLines.map((l, i) => (
                <Polyline key={i} positions={l.pts}
                  pathOptions={{ color: l.color, weight: 3, opacity: 0.85 }} />
              ))}

              {stations.map(s => (
                <StationMarker key={s.station_id} s={s}
                  isFrom={from?.station_id === s.station_id}
                  isTo={to?.station_id === s.station_id}
                  isStop={transferIds.has(s.station_id)}
                  isIntermediate={intermediateIds.has(s.station_id)}
                  isSearch={highlightId === s.station_id}
                  onClick={handleStationClick}
                />
              ))}
            </MapContainer>
          )}

          {!from && !loading && (
            <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-[1000] bg-white/90 dark:bg-slate-800/90 backdrop-blur-sm text-xs text-slate-600 dark:text-slate-300 px-3 py-1.5 rounded-full shadow border border-slate-200 dark:border-slate-700 pointer-events-none">
              Caută stații sus sau click pe hartă pentru a selecta
            </div>
          )}
          {from && !to && !loading && (
            <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-[1000] bg-emerald-600/90 backdrop-blur-sm text-xs text-white px-3 py-1.5 rounded-full shadow pointer-events-none">
              {from.name} selectat — alege destinația
            </div>
          )}
        </div>

        {/* SIDEBAR */}
        <div className="w-full lg:w-64 lg:shrink-0 bg-white dark:bg-slate-900 rounded-2xl shadow-md border border-slate-200 dark:border-slate-700 overflow-y-auto flex flex-col">
          <div className="p-4 border-b border-slate-200 dark:border-slate-700">
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-3">Selecție</div>
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-full bg-emerald-500 shrink-0"></span>
                <span className="text-sm text-slate-700 dark:text-slate-200 truncate">
                  {from ? from.name : <span className="text-slate-400 italic">plecare</span>}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-full bg-red-500 shrink-0"></span>
                <span className="text-sm text-slate-700 dark:text-slate-200 truncate">
                  {to ? to.name : <span className="text-slate-400 italic">destinație</span>}
                </span>
              </div>
            </div>
          </div>

          <div className="p-4 flex-1">
            {routeLoading && <div className="text-xs text-slate-400 animate-pulse">Calculez ruta...</div>}
            {!routeLoading && routeError && (
              <div className="text-xs text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 rounded-xl p-3">{routeError}</div>
            )}
            {!routeLoading && route?.found && (
              <div className="space-y-3">
                <div className="flex justify-between text-sm">
                  <span className="text-slate-500">Durată</span>
                  <span className="font-semibold text-slate-900 dark:text-slate-100">{fmtDuration(route.total_duration_min)}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-slate-500">Schimbări</span>
                  <span className="font-semibold text-slate-900 dark:text-slate-100">
                    {route.transfer_count === 0 ? 'Direct' : route.transfer_count === 1 ? '1 schimbare' : `${route.transfer_count} schimbări`}
                  </span>
                </div>
                <div className="mt-3 space-y-3">
                  {route.legs.map((leg, i) => (
                    <div key={i} className="rounded-xl border border-slate-200 dark:border-slate-700 p-3 text-xs space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: LEG_COLORS[i % LEG_COLORS.length] }} />
                        <span className="font-semibold text-slate-800 dark:text-slate-100">{fmtTrainType(leg.train_type)} {leg.train_number}</span>
                      </div>
                      {leg.operator_name && (
                        <div className="pl-4 flex items-center gap-1.5">
                          <svg className="w-3 h-3 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                          </svg>
                          <span className="text-slate-500 dark:text-slate-400 text-[11px]">
                            Operator: <span className="font-medium text-slate-700 dark:text-slate-300">{leg.operator_name}</span>
                          </span>
                        </div>
                      )}
                      <div className="text-slate-600 dark:text-slate-400 pl-4">{leg.from_station} {leg.departure_time?.slice(0,5)}</div>
                      <div className="text-slate-600 dark:text-slate-400 pl-4">→ {leg.to_station} {leg.arrival_time?.slice(0,5)}</div>
                      {leg.distance_km && <div className="text-slate-400 pl-4">{Math.round(leg.distance_km)} km</div>}
                    </div>
                  ))}
                </div>
                {userRole === 'passenger' && (
                  <button
                    onClick={() => navigate('/tickets/buy', { state: { prefillFrom: from, prefillTo: to } })}
                    className="w-full mt-2 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-semibold rounded-xl px-3 py-2.5 transition"
                  >
                    Cumpără bilet
                  </button>
                )}
              </div>
            )}
            {!from && !to && (
              <div className="text-xs text-slate-400 leading-relaxed mt-2">
                <p className="mb-2">Caută stațiile în câmpurile de sus sau click pe hartă.</p>
                <p>Traseul afișat trece prin stațiile reale din mersul CFR 2025–2026.</p>
              </div>
            )}
          </div>

          <div className="p-4 border-t border-slate-200 dark:border-slate-700">
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-2">Legendă</div>
            <div className="space-y-1.5 text-xs text-slate-600 dark:text-slate-300">
              <div className="flex items-center gap-2"><span className="w-3 h-3 rounded-full bg-emerald-500"></span><span>Plecare</span></div>
              <div className="flex items-center gap-2"><span className="w-3 h-3 rounded-full bg-red-500"></span><span>Sosire</span></div>
              <div className="flex items-center gap-2"><span className="w-3 h-3 rounded-full bg-amber-400"></span><span>Punct de schimbare</span></div>
              <div className="flex items-center gap-2"><span className="w-3 h-3 rounded-full bg-purple-500"></span><span>Stație de oprire</span></div>
              <div className="flex items-center gap-2"><span className="w-3 h-3 rounded-full bg-blue-500 opacity-75"></span><span>Centru universitar</span></div>
              <div className="flex items-center gap-2"><span className="w-3 h-3 rounded-full bg-slate-400 opacity-60"></span><span>Stație feroviară</span></div>
              <div className="flex items-center gap-2 mt-1">
                <svg width="20" height="8" className="shrink-0"><line x1="0" y1="4" x2="20" y2="4" stroke="#10b981" strokeWidth="3" opacity="0.85"/></svg>
                <span>Traseu prin stații reale</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
