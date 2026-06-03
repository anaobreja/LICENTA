import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { disableMFA, getUserProfile, setupMFA, verifyMFA } from '../services/api'

function Settings({ user, theme, onThemeChange }) {
  const [saved, setSaved] = useState(false)
  const [mfaEnabled, setMfaEnabled] = useState(false)
  const [mfaQr, setMfaQr] = useState('')
  const [mfaSecret, setMfaSecret] = useState('')
  const [mfaCode, setMfaCode] = useState('')
  const [mfaBusy, setMfaBusy] = useState(false)
  const [mfaMsg, setMfaMsg] = useState('')
  const [mfaErr, setMfaErr] = useState('')
  const [disablePwd, setDisablePwd] = useState('')

  const applyTheme = (nextTheme) => {
    onThemeChange(nextTheme)
    setSaved(true)

    window.clearTimeout(applyTheme.timeoutId)
    applyTheme.timeoutId = window.setTimeout(() => setSaved(false), 1200)
  }

  const refreshMfa = async () => {
    try {
      const data = await getUserProfile()
      setMfaEnabled(Boolean(data.mfa_enabled))
    } catch (_) {
      setMfaEnabled(Boolean(user?.mfa_enabled))
    }
  }

  useEffect(() => {
    refreshMfa()
  }, [user])

  const onSetupMfa = async () => {
    setMfaMsg('')
    setMfaErr('')
    setMfaBusy(true)
    try {
      const res = await setupMFA()
      setMfaQr(res.qr_data_url || '')
      setMfaSecret(res.secret_base32 || '')
      setMfaMsg(res.message || 'Scaneaza QR-ul, apoi confirma cu un cod din aplicatie.')
    } catch (e) {
      setMfaErr(e.message || 'Setup MFA a esuat')
    } finally {
      setMfaBusy(false)
    }
  }

  const onVerifyMfa = async (e) => {
    e.preventDefault()
    setMfaMsg('')
    setMfaErr('')
    setMfaBusy(true)
    try {
      await verifyMFA(mfaCode.trim())
      setMfaCode('')
      setMfaQr('')
      setMfaSecret('')
      setMfaMsg('MFA activat cu succes.')
      await refreshMfa()
    } catch (e) {
      setMfaErr(e.message || 'Cod invalid')
    } finally {
      setMfaBusy(false)
    }
  }

  const onDisableMfa = async (e) => {
    e.preventDefault()
    setMfaMsg('')
    setMfaErr('')
    setMfaBusy(true)
    try {
      await disableMFA(disablePwd)
      setDisablePwd('')
      setMfaMsg('MFA dezactivat.')
      await refreshMfa()
    } catch (e) {
      setMfaErr(e.message || 'Nu s-a putut dezactiva MFA')
    } finally {
      setMfaBusy(false)
    }
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="max-w-4xl mx-auto space-y-6">
        <div className="rounded-3xl p-8 bg-gradient-to-r from-slate-900 via-slate-800 to-cyan-700 text-white shadow-2xl">
          <p className="text-sm uppercase tracking-[0.25em] text-cyan-100">Preferences</p>
          <h1 className="mt-2 text-4xl font-black">Settings</h1>
          <p className="mt-3 max-w-2xl text-white/80">
            Configureaza interfata aplicatiei si alege modul de afisare preferat pentru sesiunea curenta.
          </p>
        </div>

        <div className="grid gap-6 md:grid-cols-[1.2fr_0.8fr]">
          <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-lg transition-colors duration-300 dark:border-slate-800 dark:bg-slate-900">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-2xl font-bold text-slate-900 dark:text-slate-50">Theme</h2>
                <p className="mt-1 text-slate-600 dark:text-slate-300">
                  Schimba intre light si dark mode. Preferinta este salvata local.
                </p>
              </div>
              <span className="rounded-full bg-cyan-100 px-3 py-1 text-sm font-semibold text-cyan-900 dark:bg-cyan-500/15 dark:text-cyan-200">
                {theme === 'dark' ? 'Dark' : 'Light'}
              </span>
            </div>

            <div className="mt-6 grid gap-4 sm:grid-cols-2">
              <button
                type="button"
                onClick={() => applyTheme('light')}
                className={`rounded-2xl border p-4 text-left transition ${
                  theme === 'light'
                    ? 'border-cyan-500 bg-cyan-50 ring-2 ring-cyan-200 dark:bg-cyan-500/10'
                    : 'border-slate-200 bg-slate-50 hover:bg-slate-100 dark:border-slate-800 dark:bg-slate-950 dark:hover:bg-slate-800'
                }`}
              >
                <div className="text-lg font-bold text-slate-900 dark:text-slate-50">Light mode</div>
                <div className="mt-1 text-sm text-slate-600 dark:text-slate-300">
                  Fundal deschis, contrast bun pentru utilizare pe timp de zi.
                </div>
              </button>

              <button
                type="button"
                onClick={() => applyTheme('dark')}
                className={`rounded-2xl border p-4 text-left transition ${
                  theme === 'dark'
                    ? 'border-cyan-500 bg-slate-950 ring-2 ring-cyan-200'
                    : 'border-slate-200 bg-slate-50 hover:bg-slate-100 dark:border-slate-800 dark:bg-slate-950 dark:hover:bg-slate-800'
                }`}
              >
                <div className="text-lg font-bold text-slate-900 dark:text-slate-50">Dark mode</div>
                <div className="mt-1 text-sm text-slate-600 dark:text-slate-300">
                  Fundal inchis, mai confortabil pentru ecrane si camere slab iluminate.
                </div>
              </button>
            </div>

            <div className="mt-6 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => applyTheme(theme === 'dark' ? 'light' : 'dark')}
                className="rounded-xl bg-slate-900 px-4 py-2 font-semibold text-white transition hover:bg-slate-800 dark:bg-cyan-500 dark:text-slate-950 dark:hover:bg-cyan-400"
              >
                Toggle theme
              </button>
              <Link
                to="/dashboard"
                className="rounded-xl border border-slate-300 px-4 py-2 font-semibold text-slate-700 transition hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
              >
                Back to dashboard
              </Link>
            </div>

            {saved && (
              <div className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-emerald-800 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-200">
                Settings saved.
              </div>
            )}
          </section>

          <aside className="rounded-3xl border border-slate-200 bg-white p-6 shadow-lg transition-colors duration-300 dark:border-slate-800 dark:bg-slate-900">
            <h2 className="text-2xl font-bold text-slate-900 dark:text-slate-50">Account preview</h2>
            <div className="mt-4 rounded-2xl bg-slate-50 p-4 dark:bg-slate-950">
              <div className="text-sm uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400">Signed in as</div>
              <div className="mt-2 text-xl font-bold text-slate-900 dark:text-slate-50">
                {user?.first_name || 'User'} {user?.last_name || ''}
              </div>
              <div className="text-sm text-slate-600 dark:text-slate-300">{user?.email || 'No email available'}</div>
              <div className="mt-4 inline-flex rounded-full bg-cyan-100 px-3 py-1 text-sm font-semibold text-cyan-900 dark:bg-cyan-500/15 dark:text-cyan-200">
                Role: {user?.role || 'unknown'}
              </div>
              <div className="mt-2 text-sm text-slate-600 dark:text-slate-300">
                MFA: <span className="font-semibold">{mfaEnabled ? 'activ' : 'inactiv'}</span>
              </div>
            </div>

            {/* Informative notes removed per user request */}
          </aside>
        </div>

        <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-lg transition-colors duration-300 dark:border-slate-800 dark:bg-slate-900">
          <h2 className="text-2xl font-bold text-slate-900 dark:text-slate-50">Autentificare in doua etape (TOTP)</h2>
          <p className="mt-1 text-slate-600 dark:text-slate-300">
            Activeaza MFA pentru a cere un cod din Google Authenticator / Microsoft Authenticator la login.
          </p>

          {mfaErr && (
            <div className="mt-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-red-800 dark:border-red-800 dark:bg-red-950/40 dark:text-red-200">
              {mfaErr}
            </div>
          )}
          {mfaMsg && (
            <div className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200">
              {mfaMsg}
            </div>
          )}

          {!mfaEnabled ? (
            <div className="mt-6 space-y-4">
              <button
                type="button"
                disabled={mfaBusy}
                onClick={onSetupMfa}
                className="rounded-xl bg-slate-900 px-4 py-2 font-semibold text-white hover:bg-slate-800 disabled:opacity-60 dark:bg-cyan-600 dark:hover:bg-cyan-500"
              >
                {mfaBusy ? 'Se incarca...' : 'Genereaza secret MFA (QR)'}
              </button>

              {mfaQr && (
                <div className="space-y-3">
                  <img src={mfaQr} alt="MFA QR" className="w-48 h-48 rounded-xl border border-slate-200 dark:border-slate-700" />
                  {mfaSecret && (
                    <p className="text-xs font-mono break-all text-slate-600 dark:text-slate-400">
                      Secret (manual): {mfaSecret}
                    </p>
                  )}
                  <form onSubmit={onVerifyMfa} className="flex flex-wrap gap-2 items-end">
                    <div>
                      <label className="block text-sm font-semibold text-slate-700 dark:text-slate-200 mb-1">
                        Cod din aplicatie
                      </label>
                      <input
                        value={mfaCode}
                        onChange={(e) => setMfaCode(e.target.value)}
                        className="px-3 py-2 rounded-xl border border-slate-300 font-mono dark:bg-slate-950 dark:border-slate-700"
                        placeholder="000000"
                        maxLength={12}
                      />
                    </div>
                    <button
                      type="submit"
                      disabled={mfaBusy || mfaCode.trim().length < 6}
                      className="rounded-xl bg-emerald-600 px-4 py-2 font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
                    >
                      Confirma MFA
                    </button>
                  </form>
                </div>
              )}
            </div>
          ) : (
            <form onSubmit={onDisableMfa} className="mt-6 space-y-3 max-w-md">
              <p className="text-sm text-slate-600 dark:text-slate-300">MFA este activ. Introdu parola pentru a-l dezactiva.</p>
              <input
                type="password"
                value={disablePwd}
                onChange={(e) => setDisablePwd(e.target.value)}
                className="w-full px-3 py-2 rounded-xl border border-slate-300 dark:bg-slate-950 dark:border-slate-700"
                placeholder="Parola contului"
              />
              <button
                type="submit"
                disabled={mfaBusy || !disablePwd}
                className="rounded-xl bg-red-600 px-4 py-2 font-semibold text-white hover:bg-red-700 disabled:opacity-50"
              >
                Dezactiveaza MFA
              </button>
            </form>
          )}
        </section>
      </div>
    </div>
  )
}

export default Settings
