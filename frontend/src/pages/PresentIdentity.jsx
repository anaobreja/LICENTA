import { useCallback, useEffect, useRef, useState } from 'react'
import { generatePresentation, getMyCard } from '../services/api'

const TTL = 180

function CountdownRing({ secondsLeft, total = TTL }) {
  const R = 54
  const CIRCUMFERENCE = 2 * Math.PI * R
  const dashOffset = CIRCUMFERENCE * (1 - secondsLeft / total)
  const color = secondsLeft > 60 ? '#10b981' : secondsLeft > 20 ? '#f59e0b' : '#ef4444'
  return (
    <svg width="130" height="130" className="absolute inset-0 -rotate-90">
      <circle cx="65" cy="65" r={R} fill="none" stroke="#1e293b" strokeWidth="8" />
      <circle cx="65" cy="65" r={R} fill="none" stroke={color} strokeWidth="8"
        strokeDasharray={CIRCUMFERENCE} strokeDashoffset={dashOffset} strokeLinecap="round"
        style={{ transition: 'stroke-dashoffset 1s linear, stroke 0.5s' }} />
    </svg>
  )
}

export default function PresentIdentity() {
  const [cardData, setCardData] = useState(null)
  const [presentation, setPresentation] = useState(null)
  const [secondsLeft, setSecondsLeft] = useState(TTL)
  const [error, setError] = useState('')
  const [loadingCard, setLoadingCard] = useState(true)
  const [loading, setLoading] = useState(false)
  const [fullscreen, setFullscreen] = useState(false)
  const timerRef = useRef(null)

  useEffect(() => {
    getMyCard()
      .then(setCardData)
      .catch(e => setError(e.message || 'Cardul digital nu este inca emis'))
      .finally(() => setLoadingCard(false))
  }, [])

  // Protecție anti-buclă: dacă expires_at vine în trecut (bug de TZ),
  // NU regenerăm automat — afișăm eroare în loc să spamăm backend-ul.
  // Pentru auto-regenerare, păstrăm un "lock" pe durata cererii.
  const generatingRef = useRef(false)
  const lastGenAtRef = useRef(0)

  const startCountdown = (expiresAt) => {
    if (timerRef.current) clearInterval(timerRef.current)

    // Parsare robustă: dacă serverul a trimis fără sufix de TZ (bug vechi),
    // tratăm ca UTC. JavaScript altfel l-ar interpreta ca ora locală.
    const expiresMs = (() => {
      const raw = String(expiresAt)
      const hasTimezone = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(raw)
      const normalized = hasTimezone ? raw : raw + 'Z'
      return new Date(normalized).getTime()
    })()

    // Sanity check: dacă expires_at este în trecut sau prea aproape,
    // nu mai pornim timer — semnal că ceva e greșit cu serverul/clock-ul.
    const initialLeft = Math.round((expiresMs - Date.now()) / 1000)
    if (!Number.isFinite(initialLeft) || initialLeft <= 0) {
      setSecondsLeft(0)
      setError(
        'Token-ul generat are deja data de expirare in trecut. ' +
        'Verifica ceasul sistemului sau reincarca pagina.'
      )
      return
    }

    const tick = () => {
      const left = Math.max(0, Math.round((expiresMs - Date.now()) / 1000))
      setSecondsLeft(left)
      if (left === 0) {
        clearInterval(timerRef.current)
        timerRef.current = null
        // Auto-regenerare doar dacă nu am cerut deja una recent
        // (protecție în plus contra buclei chiar dacă alte protecții pică).
        const now = Date.now()
        if (now - lastGenAtRef.current > 2000) {
          generate()
        }
      }
    }
    tick()
    timerRef.current = setInterval(tick, 1000)
  }

  const generate = async () => {
    // Lock: refuzăm concurrent calls (cauza principală a buclei infinite)
    if (generatingRef.current) return
    generatingRef.current = true
    lastGenAtRef.current = Date.now()

    setLoading(true); setError('')
    try {
      const data = await generatePresentation({ ttl_seconds: TTL })
      setPresentation(data); setSecondsLeft(TTL); startCountdown(data.expires_at)
    } catch (e) {
      if (e.message?.includes('401') || e.message?.includes('Unauthorized')) {
        setError('Sesiunea a expirat. Te rugăm să te autentifici din nou.')
        if (timerRef.current) clearInterval(timerRef.current)
      } else {
        setError(e.message || 'Nu am putut genera prezentarea')
      }
    }
    finally {
      setLoading(false)
      generatingRef.current = false
    }
  }

  useEffect(() => () => { if (timerRef.current) clearInterval(timerRef.current) }, [])

  const ringColor = secondsLeft > 60 ? 'text-emerald-400' : secondsLeft > 20 ? 'text-amber-400' : 'text-red-400'

  return (
    <div className="container mx-auto px-4 py-8 max-w-3xl">
      <h1 className="text-3xl font-bold mb-2 dark:text-slate-100">Cardul meu digital Rail</h1>
      <p className="text-slate-600 dark:text-slate-300 mb-6">Card digital de acreditare, cu token dinamic pentru verificare rapida.</p>

      {error && <div className="bg-red-50 border border-red-200 text-red-700 p-3 rounded-xl mb-4 dark:bg-red-950/40 dark:border-red-800 dark:text-red-200">{error}</div>}

      {loadingCard ? (
        <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm mb-6 dark:bg-slate-900 dark:border-slate-700 dark:text-slate-200">Se incarca datele cardului...</div>
      ) : cardData?.card ? (
        <div className="mb-6 rounded-3xl p-6 text-white shadow-2xl bg-gradient-to-br from-slate-900 via-sky-900 to-cyan-800">
          <div className="flex justify-between items-start">
            <div>
              <p className="text-xs uppercase tracking-[0.25em] text-cyan-200">Card Digital Rail</p>
              <p className="text-2xl font-extrabold mt-2">{cardData.card.holder_name}</p>
            </div>
            <span className="px-3 py-1 rounded-full bg-white/20 text-xs font-semibold">{cardData.card.status.toUpperCase()}</span>
          </div>
          <p className="font-mono tracking-widest mt-8 text-lg">{cardData.card.card_identifier}</p>
          <div className="mt-4 grid md:grid-cols-2 gap-3 text-sm">
            <p><span className="text-cyan-200">Emitent:</span> {cardData.card.issuer_name}</p>
            <p><span className="text-cyan-200">Valabil pana la:</span> {String(cardData.card.valid_until).slice(0,10)}</p>
          </div>
          <p className="mt-4 text-sm text-cyan-100">Atribute active: {cardData.claims.map(c => c.credential_type).join(', ') || 'none'}</p>
        </div>
      ) : null}

      <button
        onClick={generate}
        disabled={loading || !cardData?.card}
        className="bg-slate-900 dark:bg-cyan-600 text-white px-4 py-2 rounded-xl hover:bg-slate-800 dark:hover:bg-cyan-500 disabled:opacity-60"
      >
        {loading ? 'Se genereaza...' : 'Genereaza token dinamic'}
      </button>

      {presentation && (
        <div className="mt-6 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-2xl p-5 shadow-sm">
          <h2 className="text-xl font-bold dark:text-slate-100 mb-3">Token prezentare activ</h2>
          <div className="font-mono text-sm break-all bg-slate-100 dark:bg-slate-950 dark:text-slate-100 rounded-lg p-3 mb-4">{presentation.token_value}</div>

          {presentation.qr_data_url && (
            <div className="flex flex-col items-center gap-5">
              {/* QR — tap pentru fullscreen */}
              <button
                type="button"
                onClick={() => setFullscreen(true)}
                className="focus:outline-none group"
              >
                <div className="bg-white p-3 rounded-2xl shadow group-hover:shadow-xl transition">
                  <img src={presentation.qr_data_url} alt="QR prezentare" className="w-52 h-52 rounded-xl" />
                </div>
                <span className="block text-center text-xs text-slate-400 mt-1">⛶ tap = fullscreen</span>
              </button>

              {/* Modal fullscreen */}
              {fullscreen && (
                <div
                  className="fixed inset-0 z-50 bg-black flex flex-col items-center justify-center cursor-pointer"
                  onClick={() => setFullscreen(false)}
                >
                  <img src={presentation.qr_data_url} alt="QR fullscreen" className="w-80 h-80 rounded-2xl" />
                  <div className={`mt-6 text-5xl font-black tabular-nums ${ringColor}`}>
                    {String(Math.floor(secondsLeft / 60)).padStart(2,'0')}:{String(secondsLeft % 60).padStart(2,'0')}
                  </div>
                  <p className="text-slate-400 text-sm mt-3">Apasă oriunde pentru a închide</p>
                </div>
              )}

              {/* Countdown ring + timer separat */}
              <div className="flex flex-col items-center gap-1">
                <div className="relative flex items-center justify-center" style={{ width: 130, height: 130 }}>
                  <CountdownRing secondsLeft={secondsLeft} />
                  <span className={`text-3xl font-black tabular-nums ${ringColor}`}>
                    {String(Math.floor(secondsLeft / 60)).padStart(2,'0')}:{String(secondsLeft % 60).padStart(2,'0')}
                  </span>
                </div>
                <span className="text-xs text-slate-400">
                  {secondsLeft === 0 ? 'Se regenerează...' : 'se regenerează automat la expirare'}
                </span>
              </div>
            </div>
          )}

          <div className="mt-4 text-sm text-slate-600 dark:text-slate-300">
            <p>Expira la: {new Date(presentation.expires_at).toLocaleString('ro-RO', { year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit', second:'2-digit', hour12:false })}</p>
            <p>Status: {presentation.status}</p>
          </div>
        </div>
      )}
    </div>
  )
}
