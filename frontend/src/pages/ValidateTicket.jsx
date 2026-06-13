import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { validateTicketToken } from '../services/api'

const RESULT_STYLE = {
  valid:        { title: 'BILET VALID',    bg: 'bg-emerald-500', ring: 'ring-emerald-300 dark:ring-emerald-700', icon: '✅' },
  already_used: { title: 'DEJA FOLOSIT',   bg: 'bg-amber-500',   ring: 'ring-amber-300 dark:ring-amber-700',    icon: '⚠️' },
  expired:      { title: 'BILET EXPIRAT',  bg: 'bg-amber-500',   ring: 'ring-amber-300 dark:ring-amber-700',    icon: '⏰' },
  invalid:      { title: 'BILET INVALID',  bg: 'bg-red-500',     ring: 'ring-red-300 dark:ring-red-700',        icon: '❌' },
}

export default function ValidateTicket() {
  const readerId = 'validate-ticket-qr-reader'
  const scannerRef = useRef(null)
  const mountedRef = useRef(true)
  const startingRef = useRef(false)

  const [token, setToken] = useState('')
  const [scanInfo, setScanInfo] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [scanning, setScanning] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [flash, setFlash] = useState(null)

  const stopAndClearScanner = async () => {
    const scanner = scannerRef.current
    if (!scanner) return
    try { await scanner.stop() } catch (_) {}
    try { await scanner.clear() } catch (_) {}
    scannerRef.current = null
  }

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      stopAndClearScanner()
    }
  }, [])

  const validateToken = async (scannedToken) => {
    setToken(scannedToken)
    setScanInfo('QR detectat. Validez biletul...')
    setScanning(false)
    setSubmitting(true)
    setError(null)
    setResult(null)
    try {
      const r = await validateTicketToken(scannedToken.trim(), 'web-validator')
      setResult(r)
      const isValid = r.result === 'valid'
      setFlash({ valid: isValid })
      setTimeout(() => setFlash(null), 2000)
      setScanInfo(isValid ? 'Bilet valid.' : 'Bilet invalid.')
    } catch (err) {
      setError(err.message)
      setScanInfo('')
    } finally {
      setSubmitting(false)
    }
  }

  const startLiveScanner = async () => {
    if (startingRef.current) return
    startingRef.current = true
    setError(null)
    setScanInfo('Pornesc camera...')
    setScanning(true)

    try {
      await stopAndClearScanner()
      const mod = await import('html5-qrcode')
      const Html5Qrcode = mod.default || mod.Html5Qrcode
      if (!mountedRef.current) return

      const scanner = new Html5Qrcode(readerId, {
        experimentalFeatures: { useBarCodeDetectorIfSupported: true },
      })
      scannerRef.current = scanner

      await scanner.start(
        { facingMode: 'environment' },
        { fps: 15, qrbox: { width: 300, height: 300 } },
        async (decodedText) => {
          if (!mountedRef.current) return
          const scannedToken = (decodedText || '').trim()
          if (!scannedToken) return
          await stopAndClearScanner()
          if (!mountedRef.current) return
          await validateToken(scannedToken)
        },
        () => {}
      )

      if (mountedRef.current) {
        setScanInfo('Camera pornită. Arată codul QR al biletului.')
      }
    } catch (err) {
      if (mountedRef.current) {
        const isMobile = /Mobi|Android|iPhone|iPad/.test(navigator.userAgent)
        setError(
          (err?.message) ||
          (isMobile ? 'Nu am putut porni camera. Introdu tokenul manual.' : 'Camera nu este disponibilă.')
        )
        setScanInfo('')
      }
    } finally {
      startingRef.current = false
      if (mountedRef.current) setScanning(false)
    }
  }

  const handleManualSubmit = async (e) => {
    e?.preventDefault?.()
    if (!token.trim()) return
    await validateToken(token.trim())
  }

  const reset = () => {
    setToken('')
    setResult(null)
    setError(null)
    setScanInfo('')
  }

  const style = result ? (RESULT_STYLE[result.result] || RESULT_STYLE.invalid) : null

  return (
    <div className="container mx-auto px-4 py-8 max-w-2xl">
      {/* Flash overlay */}
      {flash && (
        <div className={`fixed inset-0 z-[9999] flex flex-col items-center justify-center ${flash.valid ? 'bg-emerald-500' : 'bg-red-600'}`}>
          <div className="text-white text-9xl font-black mb-6 animate-bounce">
            {flash.valid ? '✔' : '✕'}
          </div>
          <div className="text-white text-4xl font-black tracking-widest">
            {flash.valid ? 'VALID' : 'INVALID'}
          </div>
        </div>
      )}

      <div className="flex items-center justify-between mb-6">
        <h1 className="text-3xl font-bold text-slate-900 dark:text-slate-50">Validare bilet</h1>
        <Link
          to="/verify"
          className="inline-flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-xl px-4 py-2.5 transition shadow-sm"
        >
          <svg className="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V8a2 2 0 00-2-2h-5m-4 0V5a2 2 0 114 0v1m-4 0a2 2 0 104 0m-5 8a2 2 0 100-4 2 2 0 000 4zm0 0c1.306 0 2.417.835 2.83 2M9 14a3.001 3.001 0 00-2.83 2" />
          </svg>
          Verifică identitate
        </Link>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 p-3 rounded-xl mb-4 dark:bg-red-950/40 dark:border-red-800 dark:text-red-200">
          {error}
        </div>
      )}
      {scanInfo && (
        <div className="bg-green-50 border border-green-200 text-green-700 p-3 rounded-xl mb-4 dark:bg-emerald-950/30 dark:border-emerald-800 dark:text-emerald-200">
          {scanInfo}
        </div>
      )}

      {!result && (
        <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-700 p-6 shadow-sm space-y-4">
          <div>
            <label className="block text-sm font-semibold mb-2 text-slate-700 dark:text-slate-200">
              Scanare live (camera spate)
            </label>
            <div
              id={readerId}
              className="w-full mb-4 rounded-xl border border-slate-300 overflow-hidden bg-slate-900 dark:bg-slate-950 min-h-[280px]"
            />
            <div className="flex gap-3">
              <button
                type="button"
                onClick={startLiveScanner}
                disabled={submitting || scanning}
                className="bg-green-600 text-white px-4 py-2 rounded-xl hover:bg-green-700 disabled:opacity-60 text-sm font-semibold transition"
              >
                {scanning ? 'Camera pornește...' : 'Pornește scanarea'}
              </button>
              <button
                type="button"
                onClick={async () => { await stopAndClearScanner(); setScanning(false); setScanInfo('') }}
                className="bg-red-500 text-white px-4 py-2 rounded-xl hover:bg-red-600 text-sm font-semibold transition"
              >
                Oprește
              </button>
            </div>
          </div>

          <form onSubmit={handleManualSubmit} className="space-y-3 border-t border-slate-200 dark:border-slate-700 pt-4">
            <label className="block text-sm font-semibold mb-2 dark:text-slate-100">Token QR bilet</label>
            <input
              className="w-full border border-slate-300 rounded-xl px-3 py-2 mb-4 dark:bg-slate-800 dark:border-slate-600 dark:text-slate-100"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="ticket_..."
            />
            <button
              type="submit"
              disabled={submitting || !token.trim()}
              className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold rounded-xl px-4 py-3 transition"
            >
              {submitting ? 'Se validează…' : 'Validează'}
            </button>
          </form>
        </div>
      )}

      {result && style && (
        <div className={`rounded-2xl shadow-xl ring-4 ${style.ring} overflow-hidden`}>
          <div className={`${style.bg} text-white text-center py-10`}>
            <div className="text-6xl mb-3">{style.icon}</div>
            <div className="text-2xl font-bold tracking-wide">{style.title}</div>
            <div className="text-sm opacity-90 mt-1">{result.message}</div>
          </div>
          <div className="bg-white dark:bg-slate-900 p-6 space-y-3">
            {result.passenger_name && (
              <div>
                <div className="text-xs text-slate-500 dark:text-slate-400">Pasager</div>
                <div className="text-lg font-semibold text-slate-900 dark:text-slate-100">{result.passenger_name}</div>
              </div>
            )}
            {result.ticket_type && (
              <div>
                <div className="text-xs text-slate-500 dark:text-slate-400">Tip bilet / abonament</div>
                <div className="font-semibold text-slate-700 dark:text-slate-200">{result.ticket_type}</div>
              </div>
            )}
            {result.valid_until && (
              <div>
                <div className="text-xs text-slate-500 dark:text-slate-400">Valabil până</div>
                <div className="font-semibold text-slate-700 dark:text-slate-200">{result.valid_until}</div>
              </div>
            )}
            <button
              onClick={reset}
              className="w-full mt-4 bg-blue-600 hover:bg-blue-700 text-white font-semibold rounded-xl px-4 py-3 transition"
            >
              Scanează alt bilet
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
