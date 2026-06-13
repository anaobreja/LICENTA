import { useEffect, useRef, useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  PieChart, Pie, Cell, Sector,
} from 'recharts'
import {
  getIssuerPendingDocuments,
  approveIssuerDocument,
  rejectIssuerDocument,
  getDocumentPhotoBlobUrl,
  getUserProfilePhotoBlobUrl,
} from '../services/api'

const YEAR_COLORS = ['#6366f1','#8b5cf6','#06b6d4','#10b981','#f59e0b','#ef4444']

const STATS_URL = '/api/university/stats'

async function fetchStats() {
  const token = localStorage.getItem('access_token')
  const r = await fetch(STATS_URL, { headers: { Authorization: `Bearer ${token}` } })
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json()
}

function StatCard({ label, value, color = 'text-cyan-400' }) {
  return (
    <div className="rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-5 shadow-sm">
      <div className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-1">{label}</div>
      <div className={`text-4xl font-black ${color}`}>{value}</div>
    </div>
  )
}

const renderActiveShape = (props) => {
  const { cx, cy, innerRadius, outerRadius, startAngle, endAngle, fill, payload, percent, value } = props
  return (
    <g>
      <text x={cx} y={cy - 10} textAnchor="middle" fill="#94a3b8" className="text-xs">{payload.name}</text>
      <text x={cx} y={cy + 14} textAnchor="middle" fill={fill} fontSize={22} fontWeight="bold">{value}</text>
      <text x={cx} y={cy + 34} textAnchor="middle" fill="#94a3b8" fontSize={12}>{(percent * 100).toFixed(0)}%</text>
      <Sector cx={cx} cy={cy} innerRadius={innerRadius} outerRadius={outerRadius + 8} startAngle={startAngle} endAngle={endAngle} fill={fill} />
      <Sector cx={cx} cy={cy} innerRadius={innerRadius - 4} outerRadius={innerRadius - 1} startAngle={startAngle} endAngle={endAngle} fill={fill} />
    </g>
  )
}

function DocProfilePhoto({ userId, hasPhoto }) {
  const [url, setUrl] = useState(null)
  const activeRef = useRef(true)

  useEffect(() => {
    activeRef.current = true
    if (!hasPhoto || !userId) { setUrl(null); return }
    getUserProfilePhotoBlobUrl(userId)
      .then(u => { if (activeRef.current) setUrl(u) })
      .catch(() => {})
    return () => { activeRef.current = false }
  }, [userId, hasPhoto])

  return (
    <div className="w-16 h-16 rounded-full overflow-hidden border-2 border-slate-200 dark:border-slate-600 bg-slate-100 dark:bg-slate-800 flex items-center justify-center shrink-0">
      {url
        ? <img src={url} alt="profil" className="w-full h-full object-cover" />
        : <span className="text-2xl text-slate-400">👤</span>
      }
    </div>
  )
}

export default function UniversityAgentDashboard() {
  const [stats, setStats] = useState(null)
  const [docs, setDocs] = useState([])
  const [yearFilter, setYearFilter] = useState('')
  const [activeIndex, setActiveIndex] = useState(0)
  const [workingId, setWorkingId] = useState(null)
  const [rejectDialog, setRejectDialog] = useState({ open: false, id: null, notes: '' })
  const [previewUrl, setPreviewUrl] = useState(null)
  const [previewLabel, setPreviewLabel] = useState('')
  const [error, setError] = useState('')

  const loadAll = async (year = null) => {
    try {
      const [s, d] = await Promise.all([fetchStats(), getIssuerPendingDocuments(year || null)])
      setStats(s)
      setDocs(d || [])
    } catch (e) { setError(e.message) }
  }

  useEffect(() => { loadAll() }, [])

  const onYearChange = (e) => { setYearFilter(e.target.value); loadAll(e.target.value ? +e.target.value : null) }

  const onApprove = async (id) => {
    setWorkingId(id)
    try { await approveIssuerDocument(id, 'Aprobat'); await loadAll(yearFilter ? +yearFilter : null) }
    catch (e) { setError(e.message) }
    finally { setWorkingId(null) }
  }

  const onRejectConfirm = async () => {
    const { id, notes } = rejectDialog
    setWorkingId(id)
    try { await rejectIssuerDocument(id, notes || 'Respins'); setRejectDialog({ open: false, id: null, notes: '' }); await loadAll(yearFilter ? +yearFilter : null) }
    catch (e) { setError(e.message) }
    finally { setWorkingId(null) }
  }

  const showPreview = (url, label) => {
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    setPreviewUrl(url)
    setPreviewLabel(label)
  }

  const onPreviewFront = async (doc) => {
    if (!doc.has_photo) return
    try { showPreview(await getDocumentPhotoBlobUrl(doc.id, 'front'), 'Legitimație — față') }
    catch (e) { setError(e.message) }
  }

  const onPreviewVerso = async (doc) => {
    if (!doc.has_photo_verso) return
    try { showPreview(await getDocumentPhotoBlobUrl(doc.id, 'verso'), 'Legitimație — verso (semnătură)') }
    catch (e) { setError(e.message) }
  }

  const onPreviewProfile = async (doc) => {
    if (!doc.has_profile_photo) return
    try { showPreview(await getUserProfilePhotoBlobUrl(doc.user_id), 'Fotografie profil') }
    catch (e) { setError(e.message) }
  }

  const yearLabel = (y) => y <= 4 ? `Licență ${y}` : `Master ${y - 4}`


  return (
    <div className="container mx-auto px-4 py-8 max-w-6xl">
      <h1 className="text-3xl font-black mb-1 dark:text-white">Dashboard Agent Universitar</h1>
      <p className="text-slate-500 dark:text-slate-400 mb-8">Statistici și cereri în așteptare pentru universitatea ta.</p>

      {error && <div className="bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-200 p-3 rounded-xl mb-4">{error}</div>}

      {/* Stat cards */}
      {stats && (
        <div className="grid grid-cols-3 gap-4 mb-8">
          <StatCard label="În așteptare" value={stats.totals.pending} color="text-amber-400" />
          <StatCard label="Aprobate" value={stats.totals.approved} color="text-emerald-400" />
          <StatCard label="Respinse" value={stats.totals.rejected} color="text-red-400" />
        </div>
      )}

      {/* Charts */}
      {stats && (
        <div className="grid md:grid-cols-2 gap-6 mb-8">

          {/* Pie — distributie pe an */}
          <div className="rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-5 shadow-sm">
            <h2 className="font-bold text-slate-800 dark:text-slate-100 mb-4">Distribuție pe an de studiu</h2>
            {stats.year_distribution.length === 0 ? (
              <p className="text-slate-400 text-sm text-center py-8">Nu există date</p>
            ) : (
              <ResponsiveContainer width="100%" height={240}>
                <PieChart>
                  <Pie
                    activeIndex={activeIndex}
                    activeShape={renderActiveShape}
                    data={stats.year_distribution}
                    cx="50%" cy="50%"
                    innerRadius={60} outerRadius={90}
                    dataKey="value"
                    onMouseEnter={(_, i) => setActiveIndex(i)}
                  >
                    {stats.year_distribution.map((_, i) => (
                      <Cell key={i} fill={YEAR_COLORS[i % YEAR_COLORS.length]} />
                    ))}
                  </Pie>
                </PieChart>
              </ResponsiveContainer>
            )}
          </div>

          {/* Bar — activitate 30 zile */}
          <div className="rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-5 shadow-sm">
            <h2 className="font-bold text-slate-800 dark:text-slate-100 mb-4">Activitate ultimele 30 zile</h2>
            {stats.activity.length === 0 ? (
              <p className="text-slate-400 text-sm text-center py-8">Nu există activitate recentă</p>
            ) : (
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={stats.activity} margin={{ top: 5, right: 10, left: -20, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis dataKey="day" tick={{ fontSize: 10, fill: '#94a3b8' }} />
                  <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} />
                  <Tooltip contentStyle={{ background: '#1e293b', border: 'none', borderRadius: 8, color: '#e2e8f0' }} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Bar dataKey="approved" name="Aprobate" fill="#10b981" radius={[4,4,0,0]} />
                  <Bar dataKey="rejected" name="Respinse" fill="#ef4444" radius={[4,4,0,0]} />
                  <Bar dataKey="pending"  name="Pendente" fill="#f59e0b" radius={[4,4,0,0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      )}

      {/* Cereri pendente */}
      <div className="rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
          <h2 className="font-bold text-xl text-slate-900 dark:text-slate-100">Cereri în așteptare ({docs.length})</h2>
          <div className="flex items-center gap-2">
            <label className="text-sm text-slate-600 dark:text-slate-400">Filtru an:</label>
            <select value={yearFilter} onChange={onYearChange} className="border border-slate-300 dark:border-slate-600 rounded-lg px-3 py-1.5 text-sm dark:bg-slate-800 dark:text-white">
              <option value="">Toți</option>
              {[1,2,3,4,5,6].map(y => <option key={y} value={y}>{yearLabel(y)}</option>)}
            </select>
          </div>
        </div>

        {docs.length === 0 ? (
          <p className="text-slate-400 text-center py-8">Nicio cerere în așteptare.</p>
        ) : (
          <div className="space-y-4">
            {docs.map(doc => (
              <div key={doc.id} className="rounded-xl border border-slate-200 dark:border-slate-700 dark:bg-slate-950 p-4">
                <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
                  <div className="flex items-center gap-3">
                    <DocProfilePhoto userId={doc.user_id} hasPhoto={doc.has_profile_photo} />
                    <div>
                      <div className="font-bold text-slate-900 dark:text-slate-100">{doc.first_name} {doc.last_name}</div>
                      <div className="text-xs text-slate-500 dark:text-slate-400">{doc.email}</div>
                    </div>
                  </div>
                  {doc.year_of_study && (
                    <span className="text-xs font-bold bg-indigo-100 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300 px-3 py-1 rounded-full">
                      {yearLabel(doc.year_of_study)}
                    </span>
                  )}
                </div>

                {/* Date CI */}
                {doc.ci_name && (
                  <div className="rounded-lg bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 px-3 py-2 text-xs grid grid-cols-2 gap-x-4 gap-y-1 mb-3">
                    <div className="text-slate-500">Nume CI: <strong className="text-slate-800 dark:text-slate-200">{doc.ci_name}</strong></div>
                    {doc.ci_number && <div className="text-slate-500">Nr CI: <strong className="text-slate-800 dark:text-slate-200">{doc.ci_number}</strong></div>}
                    {doc.ci_date_of_birth && <div className="text-slate-500">Data nașterii: <strong className="text-slate-800 dark:text-slate-200">{doc.ci_date_of_birth}</strong></div>}
                    {doc.ci_sex && <div className="text-slate-500">Sex: <strong className="text-slate-800 dark:text-slate-200">{doc.ci_sex === 'M' ? 'Masculin' : 'Feminin'}</strong></div>}
                    {doc.ci_address && <div className="text-slate-500 col-span-2">Domiciliu: <strong className="text-slate-800 dark:text-slate-200">{doc.ci_address}</strong></div>}
                  </div>
                )}

                <div className="text-sm text-slate-600 dark:text-slate-400 mb-3">
                  <span>Nr. legitimație: <strong className="text-slate-800 dark:text-slate-200">{doc.document_number_masked}</strong></span>
                  {doc.university_name && <span className="ml-4">Universitate: <strong className="text-slate-800 dark:text-slate-200">{doc.university_name}</strong></span>}
                </div>

                {doc.home_station_name && (
                  <div className="text-sm text-slate-600 dark:text-slate-400 mb-3 p-2 rounded-lg bg-indigo-50 dark:bg-indigo-900/20 border border-indigo-200 dark:border-indigo-800">
                    <span className="font-semibold text-indigo-800 dark:text-indigo-300">Gara de provenienta:</span>{' '}
                    <strong className="text-slate-800 dark:text-slate-200">{doc.home_station_name}</strong>
                    {doc.home_station_city && (
                      <span className="text-xs text-slate-500 dark:text-slate-400 ml-2">({doc.home_station_city})</span>
                    )}
                  </div>
                )}

                <div className="flex flex-wrap gap-2">
                  {doc.has_photo && (
                    <button type="button" onClick={() => onPreviewFront(doc)} className="text-xs bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 px-3 py-1.5 rounded-lg hover:bg-slate-200 dark:hover:bg-slate-700">
                      📷 Față
                    </button>
                  )}
                  {doc.has_photo_verso && (
                    <button type="button" onClick={() => onPreviewVerso(doc)} className="text-xs bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 px-3 py-1.5 rounded-lg hover:bg-slate-200 dark:hover:bg-slate-700">
                      📷 Verso
                    </button>
                  )}
                  <button onClick={() => onApprove(doc.id)} disabled={workingId === doc.id} className="text-xs bg-emerald-600 text-white px-4 py-1.5 rounded-lg hover:bg-emerald-700 disabled:opacity-60 font-semibold">
                    ✔ Aprobă
                  </button>
                  <button onClick={() => setRejectDialog({ open: true, id: doc.id, notes: '' })} disabled={workingId === doc.id} className="text-xs bg-red-600 text-white px-4 py-1.5 rounded-lg hover:bg-red-700 disabled:opacity-60 font-semibold">
                    ✕ Respinge
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Reject dialog */}
      {rejectDialog.open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="bg-white dark:bg-slate-900 rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-700 max-w-md w-full p-5">
            <h3 className="font-bold text-lg mb-3 dark:text-white">Motiv respingere</h3>
            <textarea value={rejectDialog.notes} onChange={e => setRejectDialog(d => ({ ...d, notes: e.target.value }))} rows={3} className="w-full border border-slate-300 dark:border-slate-700 rounded-xl p-3 text-sm dark:bg-slate-950 dark:text-white mb-4" placeholder="Explică motivul..." />
            <div className="flex gap-2 justify-end">
              <button onClick={() => setRejectDialog({ open: false, id: null, notes: '' })} className="px-4 py-2 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 text-sm">Anulează</button>
              <button onClick={onRejectConfirm} className="px-4 py-2 rounded-xl bg-red-600 text-white text-sm font-semibold hover:bg-red-700">Respinge</button>
            </div>
          </div>
        </div>
      )}

      {/* Photo preview */}
      {previewUrl && (
        <div
          className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-black/70 p-4"
          onClick={() => { URL.revokeObjectURL(previewUrl); setPreviewUrl(null); setPreviewLabel('') }}
        >
          {previewLabel && <p className="text-white font-semibold mb-3">{previewLabel}</p>}
          <img src={previewUrl} alt={previewLabel || 'Previzualizare'} className="max-w-lg max-h-[80vh] rounded-2xl shadow-2xl border-4 border-white" onClick={(e) => e.stopPropagation()} />
        </div>
      )}
    </div>
  )
}
