import { useEffect, useState } from 'react'
import { getMyCredentials } from '../services/api'

function Credentials() {
  const [credentials, setCredentials] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const activeCredentials = credentials.filter((c) => c.status === 'active')

  useEffect(() => {
    const run = async () => {
      try {
        const data = await getMyCredentials()
        setCredentials(data || [])
      } catch (err) {
        setError(err.message || 'Nu am putut incarca credentialele')
      } finally {
        setLoading(false)
      }
    }
    run()
  }, [])

  return (
    <div className="container mx-auto px-4 py-8 max-w-3xl">
      <h1 className="text-3xl font-bold mb-2 text-slate-900 dark:text-slate-50">Credentiale digitale</h1>
      <p className="text-slate-600 dark:text-slate-300 mb-6">Atribute verificate pe care le poti prezenta la control.</p>

      {error && <div className="bg-red-50 border border-red-200 text-red-700 p-3 rounded-xl mb-4 dark:bg-red-950/40 dark:border-red-800 dark:text-red-200">{error}</div>}

      <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm mb-6 dark:bg-slate-900 dark:border-slate-700">
        <h2 className="text-xl font-bold mb-3 text-slate-900 dark:text-slate-100">Credential activ</h2>
        {loading ? (
          <p className="text-slate-600 dark:text-slate-300">Loading...</p>
        ) : activeCredentials.length === 0 ? (
          <p className="text-slate-600 dark:text-slate-300">Nu ai credential activ momentan.</p>
        ) : (
          <div className="space-y-3">
            {activeCredentials.map((cred) => {
              const validUntil = cred.valid_until ? new Date(cred.valid_until).toLocaleString('ro-RO') : '—'
              const claimValue =
                typeof cred.claim_value === 'boolean' ? (cred.claim_value ? 'DA' : 'NU') : String(cred.claim_value)

              return (
                <div key={cred.id} className="bg-slate-100 dark:bg-slate-950 rounded-xl p-4 border border-slate-300 dark:border-slate-700">
                  <div className="flex items-center justify-between mb-4">
                    <div className="font-semibold text-lg dark:text-slate-100">{cred.credential_type}</div>
                    <div className="text-sm text-slate-600 dark:text-slate-300">Valabil până: <span className="font-medium text-slate-900 dark:text-slate-100">{validUntil}</span></div>
                  </div>

                  <div className="mt-3 space-y-2">
                    <div className="text-sm font-semibold text-slate-700 dark:text-slate-200">Atribute validate:</div>
                    <div className="text-sm">
                      <div className="flex gap-4">
                        <div className="text-slate-600 dark:text-slate-400 font-medium">Valoare:</div>
                        <div className="text-slate-900 dark:text-slate-100 font-medium font-mono">{claimValue}</div>
                      </div>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

export default Credentials
