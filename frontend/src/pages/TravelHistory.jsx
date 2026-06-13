import { useEffect, useState } from 'react'
import { getValidationsHistory, getMyTravelStats } from '../services/api'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell,
} from 'recharts'

const RESULT_BADGE = {
  valid:        { label: 'Valid',       cls: 'bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300' },
  invalid:      { label: 'Invalid',     cls: 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300' },
  expired:      { label: 'Expirat',     cls: 'bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300' },
  already_used: { label: 'Re-folosit',  cls: 'bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400' },
}

const fmtDateTime = (iso) => {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('ro-RO', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch { return iso }
}

const TRAIN_COLORS = ['#6366f1', '#8b5cf6', '#06b6d4', '#10b981', '#f59e0b']

const ACHIEVEMENT_ICONS = {
  trophy: '🏆', star: '⭐', medal: '🥇', road: '🛤️',
  globe: '🌍', leaf: '🌱', wallet: '💰',
}

function StatCard({ label, value, unit, accent = 'indigo', sub }) {
  const palette = {
    indigo: 'from-indigo-500 to-violet-600',
    emerald: 'from-emerald-500 to-teal-600',
    amber: 'from-amber-500 to-orange-600',
    sky: 'from-sky-500 to-blue-600',
  }[accent] || 'from-slate-500 to-slate-700'
  return (
    <div className="rounded-2xl p-4 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700">
      <div className={`text-xs uppercase tracking-wide bg-gradient-to-r ${palette} bg-clip-text text-transparent font-semibold`}>
        {label}
      </div>
      <div className="mt-1 flex items-baseline gap-1">
        <span className="text-2xl font-bold text-slate-900 dark:text-slate-100">{value}</span>
        {unit && <span className="text-sm text-slate-500 dark:text-slate-400">{unit}</span>}
      </div>
      {sub && <div className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{sub}</div>}
    </div>
  )
}

export default function TravelHistory({ user }) {
  const [rows, setRows] = useState([])
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const isConductor = user?.role === 'train_verifier'

  useEffect(() => {
    let alive = true
    const promises = [getValidationsHistory(100)]
    if (!isConductor) {
      promises.push(getMyTravelStats().catch(() => null))
    }
    Promise.all(promises)
      .then(([validations, statsData]) => {
        if (!alive) return
        setRows(validations || [])
        if (!isConductor && statsData) setStats(statsData)
      })
      .catch((e) => { if (alive) setError(e.message) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [isConductor])

  return (
    <div className="container mx-auto px-4 py-8 max-w-3xl">
      <h1 className="text-3xl font-bold mb-2 text-slate-900 dark:text-slate-50">Istoric călătorii</h1>
      <p className="text-sm text-slate-500 dark:text-slate-400 mb-6">
        {isConductor
          ? 'Validările pe care le-ai efectuat ca controlor de tren.'
          : 'Validările biletelor tale în trenuri.'}
      </p>

      {error && (
        <div className="mb-4 rounded-xl border border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300 px-4 py-3 text-sm">
          {error}
        </div>
      )}

      {/* DASHBOARD pentru passenger - statistici personale.
          Apare DOAR daca exista cel putin o calatorie VALIDATA de conductor
          (ticket_status='used'). Biletele cumparate dar inca neutilizate
          ('active') nu intra in stats - vor aparea banner-ul separat de mai jos. */}
      {!isConductor && stats && stats.completed_trips > 0 && (
        <div className="mb-8 space-y-4">
          {/* Banner explicativ: calatoriile validate vs bilete cumparate */}
          {stats.upcoming_trips > 0 && (
            <div className="rounded-xl px-4 py-3 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 text-amber-900 dark:text-amber-200 text-sm">
              <span className="font-semibold">i</span> Ai{' '}
              <strong>{stats.upcoming_trips} bilet{stats.upcoming_trips === 1 ? '' : 'e'} in asteptare</strong>
              {' '}(cumparate dar inca nevalidat{stats.upcoming_trips === 1 ? '' : 'e'} de conductor).
              Statisticile de mai jos arata doar calatoriile <strong>efectiv facute</strong> (QR scanat in tren).
            </div>
          )}

          {/* KPI cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatCard label="Calatorii efectuate" value={stats.completed_trips} unit="" accent="indigo"
                      sub={`din ${stats.total_trips} bilete cumparate`} />
            <StatCard label="Km parcursi" value={stats.total_km.toLocaleString('ro-RO')} unit="km" accent="sky" />
            <StatCard label="Economisit" value={stats.total_saved_ron.toFixed(0)} unit="RON" accent="emerald"
                      sub={`platit ${stats.total_spent_ron.toFixed(0)} RON`} />
            <StatCard label="CO2 economisit" value={stats.co2_saved_kg.toFixed(0)} unit="kg" accent="amber"
                      sub={`= ${stats.trees_equivalent} copaci/an`} />
          </div>

          {/* Graficuri side-by-side */}
          <div className="grid md:grid-cols-2 gap-4">
            {/* Monthly */}
            <div className="rounded-2xl p-4 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700">
              <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200 mb-3">
                Calatorii / luna
              </h3>
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={stats.monthly}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#94a3b8" opacity={0.2} />
                  <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                  <Tooltip
                    contentStyle={{ borderRadius: 8, fontSize: 12 }}
                    formatter={(v) => [`${v} calatorii`, '']}
                  />
                  <Bar dataKey="count" fill="#6366f1" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* Top trains */}
            <div className="rounded-2xl p-4 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700">
              <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200 mb-3">
                Top trenuri folosite
              </h3>
              {stats.top_trains.length === 0 ? (
                <div className="text-xs text-slate-400 py-8 text-center">Niciun tren inca.</div>
              ) : (
                <ResponsiveContainer width="100%" height={180}>
                  <PieChart>
                    <Pie
                      data={stats.top_trains}
                      dataKey="count"
                      nameKey="train_number"
                      cx="50%" cy="50%"
                      innerRadius={40} outerRadius={70}
                      label={({ train_number, count }) => `${train_number} (${count})`}
                    >
                      {stats.top_trains.map((_, i) => (
                        <Cell key={i} fill={TRAIN_COLORS[i % TRAIN_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>

          {/* Achievements */}
          {stats.achievements && stats.achievements.length > 0 && (
            <div className="rounded-2xl p-4 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700">
              <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200 mb-3">
                Realizari ({stats.achievements.length})
              </h3>
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
                {stats.achievements.map((a) => (
                  <div key={a.code}
                       className="flex items-start gap-2 p-2 rounded-xl bg-gradient-to-br from-indigo-50 to-violet-50 dark:from-indigo-900/30 dark:to-violet-900/20 border border-indigo-200 dark:border-indigo-800">
                    <span className="text-2xl leading-none">
                      {ACHIEVEMENT_ICONS[a.icon] || '🎖️'}
                    </span>
                    <div className="min-w-0">
                      <div className="text-xs font-semibold text-slate-900 dark:text-slate-100 truncate">
                        {a.label}
                      </div>
                      <div className="text-[10px] text-slate-500 dark:text-slate-400 leading-tight">
                        {a.description}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="border-t border-slate-200 dark:border-slate-700 pt-4 mt-6">
            <h2 className="text-lg font-semibold text-slate-700 dark:text-slate-200 mb-1">
              Validari biletele
            </h2>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Istoric scanari QR de catre conductor.
            </p>
          </div>
        </div>
      )}

      {/* Stare goala dashboard pentru passenger fara bilete */}
      {!isConductor && stats && stats.total_trips === 0 && (
        <div className="mb-6 p-4 rounded-2xl border border-dashed border-slate-300 dark:border-slate-700 text-sm text-slate-500 dark:text-slate-400 text-center">
          Inca nu ai calatorii. Cumpara primul bilet ca sa vezi statisticile tale.
        </div>
      )}

      {/* Stare: are bilete cumparate dar 0 validate de conductor (toate upcoming) */}
      {!isConductor && stats && stats.total_trips > 0 && stats.completed_trips === 0 && (
        <div className="mb-6 p-4 rounded-2xl border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-950/40 text-sm text-amber-900 dark:text-amber-200">
          <div className="font-semibold mb-1">Inca nu ai calatorii validate</div>
          <div>
            Ai {stats.total_trips} călători{stats.total_trips === 1 ? 'e' : 'i'} activ{stats.total_trips === 1 ? 'ă' : 'e'} sau folosit{stats.total_trips === 1 ? 'ă' : 'e'}, dar
            niciuna nu a fost încă <strong>validat{stats.total_trips === 1 ? 'ă' : 'e'} de conductor în tren</strong>.
            Statisticile (km, CO2, achievements) apar dupa prima validare.
          </div>
        </div>
      )}

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-20 bg-slate-100 dark:bg-slate-900 rounded-xl animate-pulse" />
          ))}
        </div>
      ) : rows.length === 0 ? (
        <div className="text-center py-12 rounded-2xl border border-dashed border-slate-300 dark:border-slate-700">
          <p className="text-slate-500 dark:text-slate-400">Nu există validări încă.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {rows.map((v) => {
            const badge = RESULT_BADGE[v.validation_result] || { label: v.validation_result, cls: 'bg-slate-200 text-slate-700' }
            const counterparty = isConductor
              ? `${v.passenger_first_name || ''} ${v.passenger_last_name || ''}`.trim() || 'Pasager necunoscut'
              : `${v.conductor_first_name || ''} ${v.conductor_last_name || ''}`.trim() || 'Controlor necunoscut'
            return (
              <div
                key={v.validation_id}
                className="rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 px-4 py-3 flex items-center justify-between gap-3"
              >
                <div className="min-w-0">
                  <div className="text-sm font-semibold text-slate-900 dark:text-slate-100 truncate">
                    {isConductor ? '👤' : '🚂'} {counterparty}
                  </div>
                  <div className="text-xs text-slate-500 dark:text-slate-400">
                    {fmtDateTime(v.validation_time)}
                    {v.source_type && <> · {v.source_type}</>}
                    {v.device_id && <> · {v.device_id}</>}
                  </div>
                </div>
                <span className={`text-xs font-semibold px-2 py-1 rounded-full whitespace-nowrap ${badge.cls}`}>
                  {badge.label}
                </span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
