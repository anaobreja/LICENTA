import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { getMyCredentials, getMyDocuments } from '../services/api'

const CRED_LABELS = {
  identity_verified: 'Identitate verificată',
  student_verified:  'Student verificat',
  elev_verified:     'Elev verificat',
}

const STEPS = [
  { label: 'Cont creat',       desc: 'Înregistrat cu succes',            icon: '👤', path: '/profile' },
  { label: 'Documente depuse', desc: 'Cerere trimisă spre verificare',   icon: '📄', path: '/documents' },
  { label: 'Identitate aprobată', desc: 'Agent a verificat documentele', icon: '✅', path: '/documents' },
  { label: 'Card activ',       desc: 'Prezintă QR în tren',              icon: '🪪', path: '/present' },
]

function Stepper({ step }) {
  return (
    <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-700 p-6 shadow-sm mb-6">
      <h2 className="font-bold text-lg mb-5 dark:text-white">Starea identității tale</h2>
      <div className="flex items-start gap-0">
        {STEPS.map((s, i) => {
          const done    = i < step
          const active  = i === step
          const pending = i > step
          return (
            <div key={i} className="flex-1 flex flex-col items-center text-center">
              {/* connector + circle row */}
              <div className="flex items-center w-full">
                <div className={`flex-1 h-1 ${i === 0 ? 'opacity-0' : done ? 'bg-emerald-500' : 'bg-slate-200 dark:bg-slate-700'}`} />
                <Link to={s.path}>
                  <div className={`w-10 h-10 rounded-full flex items-center justify-center text-lg font-bold border-2 transition-all
                    ${done    ? 'bg-emerald-500 border-emerald-500 text-white' : ''}
                    ${active  ? 'bg-white dark:bg-slate-900 border-indigo-500 text-indigo-500 shadow-lg shadow-indigo-200 dark:shadow-indigo-900 ' + (step < 3 ? 'animate-pulse' : '') : ''}
                    ${pending ? 'bg-slate-100 dark:bg-slate-800 border-slate-300 dark:border-slate-600 text-slate-400' : ''}
                  `}>
                    {done ? '✔' : s.icon}
                  </div>
                </Link>
                <div className={`flex-1 h-1 ${i === STEPS.length - 1 ? 'opacity-0' : done && step > i + 1 ? 'bg-emerald-500' : step === i + 1 ? 'bg-emerald-500' : 'bg-slate-200 dark:bg-slate-700'}`} />
              </div>
              {/* labels */}
              <div className={`mt-2 px-1 ${active ? 'text-indigo-600 dark:text-indigo-400' : done ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-400 dark:text-slate-500'}`}>
                <div className="text-xs font-bold">{s.label}</div>
                {active && <div className="text-xs mt-0.5 opacity-75">{s.desc}</div>}
              </div>
            </div>
          )
        })}
      </div>

      {/* Badge stare */}
      <div className="mt-5 flex justify-center">
        {step === 3 && (
          <span className="inline-flex items-center gap-2 bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300 font-bold px-4 py-2 rounded-full text-sm">
            🪪 Identitate digitală activă
          </span>
        )}
        {step === 2 && (
          <span className="inline-flex items-center gap-2 bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 font-bold px-4 py-2 rounded-full text-sm">
            ✅ Aprobat — generează cardul
          </span>
        )}
        {step === 1 && (
          <span className="inline-flex items-center gap-2 bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300 font-bold px-4 py-2 rounded-full text-sm animate-pulse">
            ⏳ În așteptare — agentul verifică
          </span>
        )}
        {step === 0 && (
          <Link to="/documents">
            <span className="inline-flex items-center gap-2 bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 font-bold px-4 py-2 rounded-full text-sm hover:bg-slate-200 dark:hover:bg-slate-700 transition">
              📄 Depune documente →
            </span>
          </Link>
        )}
      </div>
    </div>
  )
}

export default function Dashboard({ user }) {
  const [documents, setDocuments] = useState([])
  const [credentials, setCredentials] = useState([])
  const [loading, setLoading] = useState(true)
  const intervalRef = useRef(null)

  const fetchData = async () => {
    try {
      const [docData, credData] = await Promise.all([getMyDocuments(), getMyCredentials()])
      setDocuments(docData || [])
      setCredentials(credData || [])
    } catch (_) {}
    finally { setLoading(false) }
  }

  useEffect(() => {
    fetchData()
  }, [])

  const pendingDocs   = documents.filter(d => d.status === 'pending')
  const approvedDocs  = documents.filter(d => d.status === 'approved')
  const activeCreds   = credentials.filter(c => c.status === 'active')
  const expiredCreds  = credentials.filter(c => c.status === 'expired')

  // Determina pasul curent
  const step = activeCreds.length > 0 ? 3
    : approvedDocs.length > 0         ? 2
    : pendingDocs.length > 0          ? 1
    : 0

  // Auto-refresh la 30s când e pending
  useEffect(() => {
    if (step === 1) {
      intervalRef.current = setInterval(fetchData, 30000)
    }
    return () => clearInterval(intervalRef.current)
  }, [step])

  if (loading) return (
    <div className="container mx-auto px-4 py-8">
      <div className="h-8 bg-slate-200 dark:bg-slate-800 rounded-xl w-48 mb-6 animate-pulse" />
      <div className="h-40 bg-slate-100 dark:bg-slate-900 rounded-2xl animate-pulse mb-6" />
      <div className="h-32 bg-slate-100 dark:bg-slate-900 rounded-2xl animate-pulse" />
    </div>
  )

  return (
    <div className="container mx-auto px-4 py-8 max-w-2xl">
      <h1 className="text-3xl font-bold mb-6 text-slate-900 dark:text-slate-50">Salut, {user?.first_name}!</h1>

      <Stepper step={step} />

      {/* Credentiale */}
      <div className="bg-white dark:bg-slate-900 rounded-2xl shadow border border-slate-200 dark:border-slate-700 p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold dark:text-slate-100">Credențialele tale</h2>
          {step === 1 && (
            <button onClick={fetchData} className="text-xs text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 border border-slate-200 dark:border-slate-700 rounded-lg px-2 py-1">
              ↻ Refresh
            </button>
          )}
        </div>

        {activeCreds.length === 0 && expiredCreds.length === 0 ? (
          <p className="text-slate-500 dark:text-slate-400 text-sm">
            Nu ai credențiale active.{' '}
            <Link to="/documents" className="text-blue-600 dark:text-cyan-400 underline">Depune documente</Link>{' '}
            pentru a fi verificat.
          </p>
        ) : (
          <div className="space-y-3">
            {activeCreds.map(cred => (
              <div key={cred.id} className="flex items-center justify-between rounded-xl border border-emerald-200 dark:border-emerald-800 px-4 py-3">
                <div className="flex items-center gap-3">
                  <span className="text-emerald-500 text-xl">✔</span>
                  <div>
                    <div className="font-semibold text-slate-900 dark:text-slate-100">{CRED_LABELS[cred.credential_type] || cred.credential_type}</div>
                    <div className="text-xs text-slate-500 dark:text-slate-400">
                      Valabil până: {cred.valid_until ? new Date(cred.valid_until).toLocaleDateString('ro-RO', { day:'2-digit', month:'long', year:'numeric' }) : '—'}
                    </div>
                  </div>
                </div>
                <span className="text-xs font-semibold bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300 px-2 py-1 rounded-full">Activ</span>
              </div>
            ))}
            {expiredCreds.map(cred => (
              <div key={cred.id} className="flex items-center justify-between rounded-xl border border-slate-200 dark:border-slate-700 px-4 py-3 opacity-60">
                <div className="flex items-center gap-3">
                  <span className="text-slate-400 text-xl">✕</span>
                  <div>
                    <div className="font-semibold text-slate-700 dark:text-slate-300">{CRED_LABELS[cred.credential_type] || cred.credential_type}</div>
                    <div className="text-xs text-slate-400 dark:text-slate-500">
                      Expirat la: {cred.valid_until ? new Date(cred.valid_until).toLocaleDateString('ro-RO', { day:'2-digit', month:'long', year:'numeric' }) : '—'}
                    </div>
                  </div>
                </div>
                <span className="text-xs font-semibold bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 px-2 py-1 rounded-full">Expirat</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
