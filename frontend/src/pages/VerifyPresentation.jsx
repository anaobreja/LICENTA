import { useEffect, useRef, useState } from 'react'
import {
  verifyPresentation,
  getDocumentPhotoBlobUrl,
  getUserProfilePhotoBlobUrl,
  verifyOfflineToken,
  getVerificationKey,
} from '../services/api'

function VerifyPresentation() {
  const readerId = 'verify-qr-reader'
  const scannerRef = useRef(null)
  const mountedRef = useRef(true)
  const startingRef = useRef(false)
  const [token, setToken] = useState('')
  const [scanInfo, setScanInfo] = useState('')
  const [result, setResult] = useState(null)
  const [identityPhotoUrl, setIdentityPhotoUrl] = useState(null)
  const [profilePhotoUrl, setProfilePhotoUrl] = useState(null)
  const [validationTime, setValidationTime] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [scanning, setScanning] = useState(false)
  const [flash, setFlash] = useState(null) // { valid: bool }
  // Mod offline: verificam tokenul local cu cheia publica Ed25519.
  // Default OFF (modul online ramine comportamentul existent).
  const [offlineMode, setOfflineMode] = useState(() => {
    try { return localStorage.getItem('rdc_offline_mode') === '1' } catch { return false }
  })
  const [keyInfo, setKeyInfo] = useState(null) // { kid, fetched_at }
  const [refreshingKey, setRefreshingKey] = useState(false)

  const stopAndClearScanner = async () => {
    const scanner = scannerRef.current
    if (!scanner) {
      return
    }

    try {
      await scanner.stop()
    } catch (_) {
      // Scanner may already be stopped.
    }

    try {
      await scanner.clear()
    } catch (_) {
      // Ignore clear failures when scanner did not fully initialize.
    }

    scannerRef.current = null
  }

  const verifyScannedToken = async (scannedToken) => {
    setToken(scannedToken)
    setScanInfo('QR detectat din camera. Verific automat...')
    setScanning(false)

    try {
      setLoading(true)
      setResult(null)
      const data = await verifyPresentation({ token: scannedToken })
      setResult(data)
        // If backend returned identity document id, fetch the photo
        if (data?.identity_document_id) {
          try {
            const blobUrl = await getDocumentPhotoBlobUrl(data.identity_document_id, 'front')
            setIdentityPhotoUrl(blobUrl)
          } catch (err) {
            console.warn('Could not load legitimatie photo', err)
            setIdentityPhotoUrl(null)
          }
        } else {
          setIdentityPhotoUrl(null)
        }
        if (data?.holder?.user_id) {
          try {
            setProfilePhotoUrl(await getUserProfilePhotoBlobUrl(data.holder.user_id))
          } catch {
            setProfilePhotoUrl(null)
          }
        } else {
          setProfilePhotoUrl(null)
        }
      setValidationTime(new Date().toLocaleString('ro-RO'))
      setError('')
      setScanInfo('QR validat cu succes.')
      setFlash({ valid: data.result === 'valid' })
      setTimeout(() => setFlash(null), 2000)
    } catch (err) {
      setError(err.message || 'Nu am putut verifica tokenul')
    } finally {
      setLoading(false)
    }
  }

  const startLiveScanner = async () => {
    if (startingRef.current) {
      return
    }

    startingRef.current = true
    setError('')
    setScanInfo('Pornesc camera pentru scanare QR...')
    setScanning(true)

    try {
      await stopAndClearScanner()

      const mod = await import('html5-qrcode')
      const Html5Qrcode = mod.default || mod.Html5Qrcode

      if (!mountedRef.current) {
        return
      }

      const scanner = new Html5Qrcode(readerId)
      scannerRef.current = scanner

      await scanner.start(
        { facingMode: 'environment' },
        { fps: 10, qrbox: { width: 220, height: 220 } },
        async (decodedText) => {
          if (!mountedRef.current) {
            return
          }

          const scannedToken = (decodedText || '').trim()
          if (!scannedToken) {
            return
          }

          await stopAndClearScanner()
          if (!mountedRef.current) {
            return
          }
          if (offlineMode) {
            await verifyOfflineScanned(scannedToken)
          } else {
            await verifyScannedToken(scannedToken)
          }
        },
        () => {
          // Ignore per-frame decode failures while camera is searching.
        }
      )

      if (mountedRef.current) {
        setScanInfo('Camera este pornita. Arata codul QR in cadru.')
      }
    } catch (err) {
      if (mountedRef.current) {
        const isMobile = typeof navigator !== 'undefined' && /Mobi|Android|iPhone|iPad/.test(navigator.userAgent)
        setError(
          (err && err.message) ||
            (isMobile
              ? 'Nu am putut porni camera live. Introdu tokenul manual.'
              : 'S-a încercat deschiderea camerei, însă nu este posibilă citirea QR-ului.')
        )
        setScanInfo('')
      }
    } finally {
      startingRef.current = false
      if (mountedRef.current) {
        setScanning(false)
      }
    }
  }

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      stopAndClearScanner()
    }
  }, [])

  // Persistam preferinta + pre-incarcam cheia publica daca activam offline
  useEffect(() => {
    try { localStorage.setItem('rdc_offline_mode', offlineMode ? '1' : '0') } catch {}
    if (offlineMode && !keyInfo) {
      getVerificationKey()
        .then((k) => setKeyInfo({ kid: k.kid, fetched_at: k.fetched_at }))
        .catch(() => {})
    }
  }, [offlineMode, keyInfo])

  const refreshKey = async () => {
    setRefreshingKey(true)
    try {
      const k = await getVerificationKey({ force: true })
      setKeyInfo({ kid: k.kid, fetched_at: k.fetched_at })
    } catch (e) {
      setError('Nu am putut actualiza cheia publica: ' + (e.message || e))
    } finally {
      setRefreshingKey(false)
    }
  }

  // Verificare LOCALA: folosita atit din scanner cit si din form manual cind
  // offlineMode = true. NU apeleaza server-ul.
  const verifyOfflineScanned = async (scannedToken) => {
    setToken(scannedToken)
    setScanInfo('QR detectat. Verific local cu cheia publica...')
    setScanning(false)
    setLoading(true)
    setResult(null)
    setIdentityPhotoUrl(null)
    setProfilePhotoUrl(null)
    try {
      const res = await verifyOfflineToken(scannedToken)
      if (res.valid) {
        // Construim un "rezultat" compatibil cu UI-ul existent pentru afisaj
        const p = res.payload
        setResult({
          result: 'valid',
          notes: 'Verificare OFFLINE. Semnatura Ed25519 validata local.',
          mode: 'offline',
          card: { card_identifier: `card-${p.card}`, issuer_name: p.issuer },
          holder: {
            user_id: p.sub,
            first_name: p.holder.split(' ')[0] || '',
            last_name: p.holder.split(' ').slice(1).join(' ') || '',
          },
          claims: (p.claims || []).map((t) => ({
            credential_type: t,
            claim_value: '(detaliile complete nu sunt incluse offline)',
            valid_until: p.exp,
          })),
        })
        setFlash({ valid: true })
      } else {
        setResult({
          result: 'invalid',
          notes: res.reason,
          mode: 'offline',
          card: { card_identifier: '-', issuer_name: '-' },
          holder: { first_name: '-', last_name: '' },
          claims: [],
        })
        setFlash({ valid: false })
      }
      setValidationTime(new Date().toLocaleString('ro-RO'))
      setTimeout(() => setFlash(null), 2000)
    } catch (e) {
      setError(e.message || 'Eroare la verificare offline')
    } finally {
      setLoading(false)
    }
  }

  const onVerify = async (e) => {
    e.preventDefault()
    setError('')
    setResult(null)
    if (offlineMode) {
      return verifyOfflineScanned(token)
    }
    setLoading(true)
    try {
      const data = await verifyPresentation({ token })
      setResult(data)
      if (data?.identity_document_id) {
        try {
          const blobUrl = await getDocumentPhotoBlobUrl(data.identity_document_id)
          setIdentityPhotoUrl(blobUrl)
        } catch (_) {
          setIdentityPhotoUrl(null)
        }
      } else {
        setIdentityPhotoUrl(null)
      }
      setValidationTime(new Date().toLocaleString('ro-RO'))
      setFlash({ valid: data.result === 'valid' })
      setTimeout(() => setFlash(null), 2000)
    } catch (err) {
      setError(err.message || 'Nu am putut verifica tokenul')
      setFlash({ valid: false })
      setTimeout(() => setFlash(null), 2000)
    } finally {
      setLoading(false)
    }
  }

  const onRestartLiveScan = async () => {
    setResult(null)
    setError('')
    setToken('')
    setScanInfo('Repornesc camera...')
    await startLiveScanner()
  }

  return (
    <div className="container mx-auto px-4 py-8 max-w-3xl">
      {/* Overlay VERDE / ROȘU */}
      {flash && (
        <div className={`fixed inset-0 z-[9999] flex flex-col items-center justify-center transition-opacity
          ${flash.valid ? 'bg-emerald-500' : 'bg-red-600'}`}
        >
          <div className="text-white text-9xl font-black mb-6 animate-bounce">
            {flash.valid ? '✔' : '✕'}
          </div>
          <div className="text-white text-4xl font-black tracking-widest">
            {flash.valid ? 'VALID' : 'INVALID'}
          </div>
        </div>
      )}

      <h1 className="text-3xl font-bold mb-2 dark:text-slate-100">Verificare Rail Digital Card</h1>
      <p className="text-slate-600 dark:text-slate-300 mb-6">Validare rapida direct din camera telefonului, cu fallback pe poza/manual.</p>

      {/* Comutator mod online / offline + status cheie publica */}
      <div className={`mb-4 rounded-2xl border p-4 ${offlineMode
        ? 'bg-amber-50 border-amber-300 dark:bg-amber-950/30 dark:border-amber-700'
        : 'bg-slate-50 border-slate-200 dark:bg-slate-900 dark:border-slate-700'}`}>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className={`inline-block w-2.5 h-2.5 rounded-full ${offlineMode ? 'bg-amber-500' : 'bg-emerald-500'}`} />
              <span className="font-semibold text-slate-900 dark:text-slate-100">
                {offlineMode ? 'Mod OFFLINE (verificare locala)' : 'Mod ONLINE (verificare prin server)'}
              </span>
            </div>
            <p className="text-xs mt-1 text-slate-600 dark:text-slate-300">
              {offlineMode
                ? 'Tokenul este verificat local cu cheia publica Ed25519. Util in tunele sau zone fara semnal. Nu se poate marca tokenul ca folosit (anti-replay).'
                : 'Token-ul este trimis serverului pentru validare. Implicit; ofera verificare anti-replay si revocare in timp real.'}
            </p>
            {offlineMode && keyInfo && (
              <p className="text-[11px] mt-2 font-mono text-amber-800 dark:text-amber-200">
                kid: {keyInfo.kid} · descarcata: {new Date(keyInfo.fetched_at).toLocaleString('ro-RO')}
              </p>
            )}
          </div>
          <div className="flex flex-col gap-2 shrink-0">
            <label className="inline-flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={offlineMode}
                onChange={(e) => setOfflineMode(e.target.checked)}
                className="sr-only peer"
              />
              <span className="relative w-11 h-6 bg-slate-300 dark:bg-slate-600 rounded-full peer-checked:bg-amber-500 transition">
                <span className="absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform peer-checked:translate-x-5" />
              </span>
              <span className="text-xs font-semibold text-slate-700 dark:text-slate-200">Offline</span>
            </label>
            {offlineMode && (
              <button
                type="button"
                onClick={refreshKey}
                disabled={refreshingKey}
                className="text-xs px-3 py-1 rounded-lg border border-amber-400 text-amber-700 hover:bg-amber-100 dark:hover:bg-amber-900/30 disabled:opacity-60"
              >
                {refreshingKey ? 'Actualizez...' : 'Reactualizeaza cheia'}
              </button>
            )}
          </div>
        </div>
      </div>

      {error && <div className="bg-red-50 border border-red-200 text-red-700 p-3 rounded-xl mb-4 dark:bg-red-950/40 dark:border-red-800 dark:text-red-200">{error}</div>}
      {scanInfo && <div className="bg-green-50 border border-green-200 text-green-700 p-3 rounded-xl mb-4 dark:bg-emerald-950/30 dark:border-emerald-800 dark:text-emerald-200">{scanInfo}</div>}

      <form onSubmit={onVerify} className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm dark:bg-slate-900 dark:border-slate-700">
        <label className="block text-sm font-semibold mb-2 dark:text-slate-100">Scanare live (camera spate)</label>
        <div
          id={readerId}
          className="w-full mb-4 rounded-xl border border-slate-300 overflow-hidden bg-slate-900 dark:bg-slate-950 min-h-[400px]"
        />

        <div className="mb-4 flex gap-3">
          <button
            type="button"
            onClick={startLiveScanner}
            className="bg-green-600 text-white px-4 py-2 rounded-xl hover:bg-green-700 disabled:opacity-60"
            disabled={loading || scanning}
          >
            {scanning ? 'Camera porneste...' : 'Pornește scanarea live'}
          </button>

          <button
            type="button"
            onClick={async () => {
              await stopAndClearScanner()
              setScanning(false)
              setScanInfo('')
            }}
            className="bg-red-500 text-white px-4 py-2 rounded-xl hover:bg-red-600"
          >
            Oprește scanner
          </button>
        </div>

        <label className="block text-sm font-semibold mb-2 dark:text-slate-100">Token dinamic card</label>
        <input
          className="w-full border border-slate-300 rounded-xl px-3 py-2 mb-4 dark:bg-slate-800 dark:border-slate-600 dark:text-slate-100"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder="card_..."
          required
        />
        <button className="bg-slate-900 text-white px-4 py-2 rounded-xl hover:bg-slate-800" disabled={loading || scanning}>
          {scanning ? 'Scanez poza...' : loading ? 'Verific...' : 'Verifica'}
        </button>
      </form>

      {result && (
        <div className="mt-6 bg-white border border-slate-200 rounded-2xl p-5 shadow-sm dark:bg-slate-900 dark:border-slate-700">
          <h2 className="text-xl font-bold mb-2 text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <span>Rezultat: {result.result}</span>
            {result.mode === 'offline' && (
              <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200">
                OFFLINE
              </span>
            )}
          </h2>
          {validationTime && (
            <div className="text-sm text-slate-600 dark:text-slate-300 mb-2">Data validării: {validationTime}</div>
          )}
          <p className="text-slate-700 dark:text-slate-300 mb-3">{result.notes}</p>
          <div className="text-sm dark:text-slate-300">
            <p><span className="font-semibold dark:text-slate-100">Card:</span> {result.card.card_identifier}</p>
            <p><span className="font-semibold dark:text-slate-100">Emitent:</span> {result.card.issuer_name}</p>
            <p><span className="font-semibold dark:text-slate-100">Pasager:</span> {result.holder.first_name} {result.holder.last_name}</p>
            {result.holder.date_of_birth && (
              <p><span className="font-semibold dark:text-slate-100">Data nașterii:</span> {result.holder.date_of_birth}</p>
            )}
            {result.holder.address && (
              <p><span className="font-semibold dark:text-slate-100">Domiciliu:</span> {result.holder.address}</p>
            )}
            <p className="mt-3 font-semibold text-slate-900 dark:text-slate-100">Atribute validate</p>
            <ul className="mt-2 space-y-1">
              {result.claims.map((c) => (
                <li key={`${c.credential_type}-${c.valid_until}`} className="flex gap-2">
                  <span className="font-semibold min-w-[160px] text-slate-900 dark:text-slate-100">{c.credential_type}</span>
                  <span>{c.claim_value}</span>
                </li>
              ))}
            </ul>
          </div>
          {(profilePhotoUrl || identityPhotoUrl) && (
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              {profilePhotoUrl && (
                <div>
                  <h3 className="font-semibold dark:text-slate-100 mb-2">Fotografie profil</h3>
                  <img src={profilePhotoUrl} alt="Profil pasager" className="max-w-full rounded-lg border border-slate-200 dark:border-slate-700" />
                </div>
              )}
              {identityPhotoUrl && (
                <div>
                  <h3 className="font-semibold dark:text-slate-100 mb-2">Legitimație — față</h3>
                  <img src={identityPhotoUrl} alt="Legitimație față" className="max-w-full rounded-lg border border-slate-200 dark:border-slate-700" />
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default VerifyPresentation
