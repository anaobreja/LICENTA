import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { checkAuth, deleteAccount, exportUserData, getUserProfile, getUserProfilePhotoBlobUrl, getMyCredentials, getVerificationStatus, searchStations, updateProfile, updateProfilePhoto } from '../services/api'

function Profile({ user, onAccountDeleted, onUserUpdate }) {
  const navigate = useNavigate()
  const fileInputRef = useRef(null)
  const [form, setForm] = useState({
    first_name: '',
    last_name: '',
    phone: '',
    date_of_birth: '',
  })
  // Ruta personala
  const [homeStation, setHomeStation] = useState(null)        // { station_id, name, city, code } | null
  const [universityStation, setUniversityStation] = useState(null)
  const [stationQuery, setStationQuery] = useState('')
  const [stationResults, setStationResults] = useState([])
  const [stationOpen, setStationOpen] = useState(false)
  const [stationLoading, setStationLoading] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [profilePhotoUrl, setProfilePhotoUrl] = useState(null)
  const [photoPreview, setPhotoPreview] = useState(null)
  const [photoFile, setPhotoFile] = useState(null)
  const [photoSaving, setPhotoSaving] = useState(false)
  const [photoLocked, setPhotoLocked] = useState(false)
  const [verificationStatus, setVerificationStatus] = useState(null)

  useEffect(() => {
    const load = async () => {
      setError('')
      try {
        const data = await getUserProfile()
        setForm({
          first_name: data.first_name || '',
          last_name: data.last_name || '',
          phone: data.phone || '',
          date_of_birth: data.date_of_birth || '',
        })
        setHomeStation(data.home_station || null)
        setUniversityStation(data.university_station || null)
        if (data.has_profile_photo && data.user_id) {
          try {
            const url = await getUserProfilePhotoBlobUrl(data.user_id)
            setProfilePhotoUrl(url)
          } catch (_) {}
        }
        try {
          const creds = await getMyCredentials()
          setPhotoLocked(Array.isArray(creds) && creds.some(c => c.status === 'active'))
        } catch (_) {}
        try {
          const vs = await getVerificationStatus()
          setVerificationStatus(vs)
        } catch (_) {}
      } catch (err) {
        setError(err.message || 'Nu am putut incarca profilul')
        if (user) {
          setForm({
            first_name: user.first_name || '',
            last_name: user.last_name || '',
            phone: user.phone || '',
            date_of_birth: user.date_of_birth || '',
          })
        }
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [user])

  const onChange = (field) => (e) => {
    setForm((prev) => ({ ...prev, [field]: e.target.value }))
  }

  // Autocomplete stations
  useEffect(() => {
    if (!stationOpen) return
    let alive = true
    setStationLoading(true)
    const t = setTimeout(() => {
      searchStations(stationQuery, 15)
        .then(r => { if (alive) setStationResults(r || []) })
        .catch(() => { if (alive) setStationResults([]) })
        .finally(() => { if (alive) setStationLoading(false) })
    }, 200)
    return () => { alive = false; clearTimeout(t) }
  }, [stationQuery, stationOpen])

  const selectHomeStation = (s) => {
    setHomeStation({
      station_id: s.station_id,
      name: s.name,
      city: s.city,
      code: s.code,
    })
    setStationQuery('')
    setStationOpen(false)
  }

  const clearHomeStation = () => {
    setHomeStation(null)
  }

  const onPhotoSelect = (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setPhotoFile(file)
    setPhotoPreview(URL.createObjectURL(file))
  }

  const handleSavePhoto = async () => {
    if (!photoFile) return
    setPhotoSaving(true)
    setMessage('')
    setError('')
    try {
      await updateProfilePhoto(photoFile)
      setProfilePhotoUrl(photoPreview)
      setPhotoPreview(null)
      setPhotoFile(null)
      if (fileInputRef.current) fileInputRef.current.value = ''
      setMessage('Poza de profil actualizată.')
    } catch (err) {
      setError(err.message || 'Eroare la salvarea pozei')
    } finally {
      setPhotoSaving(false)
    }
  }

  const handleSave = async (e) => {
    e.preventDefault()
    setMessage('')
    setError('')
    setSaving(true)
    try {
      /* PROFILE_UPDATE_MARKER */ await updateProfile({
        first_name: form.first_name.trim(),
        last_name: form.last_name.trim(),
        phone: form.phone.trim() || null,
        date_of_birth: form.date_of_birth.trim() || null,
        // 0 = sterge selectia, integer > 0 = seteaza statia
        home_station_id: homeStation?.station_id ?? 0,
      })
      setMessage('Profil salvat.')
    } catch (err) {
      setError(err.message || 'Salvare esuata')
    } finally {
      setSaving(false)
    }
  }

  const handleExport = async () => {
    setMessage('')
    setError('')
    setExporting(true)
    try {
      const data = await exportUserData()
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `railway_identity_export_${new Date().toISOString().slice(0, 10)}.json`
      a.click()
      URL.revokeObjectURL(url)
      setMessage('Export descarcat.')
    } catch (err) {
      setError(err.message || 'Export esuat')
    } finally {
      setExporting(false)
    }
  }

  const handleDelete = async () => {
    if (!window.confirm('Sigur vrei sa dezactivezi contul? Vei fi delogat.')) {
      return
    }
    setMessage('')
    setError('')
    setDeleting(true)
    try {
      await deleteAccount()
      localStorage.removeItem('access_token')
      if (typeof onAccountDeleted === 'function') {
        onAccountDeleted()
      }
      navigate('/login', { replace: true })
    } catch (err) {
      setError(err.message || 'Stergere esuata')
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="container mx-auto px-4 py-8 max-w-2xl">
      <h1 className="text-3xl font-bold mb-2">Profil</h1>
      <p className="text-slate-600 dark:text-slate-400 mb-6">
        Actualizeaza datele de contact si exporta datele tale (GDPR).
      </p>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 p-3 rounded-xl mb-4 dark:bg-red-950/40 dark:border-red-800 dark:text-red-200">
          {error}
        </div>
      )}
      {message && (
        <div className="bg-emerald-50 border border-emerald-200 text-emerald-800 p-3 rounded-xl mb-4 dark:bg-emerald-950/40 dark:border-emerald-800 dark:text-emerald-200">
          {message}
        </div>
      )}

      {/* verification-banner: daca userul are identitate verificata, afisez
          un banner cu data expirarii si lista campurilor frozen. */}
      {verificationStatus?.is_verified && (
        <div className="bg-amber-50 dark:bg-amber-950/40 border border-amber-300 dark:border-amber-700 text-amber-900 dark:text-amber-100 p-4 rounded-xl mb-4">
          <div className="flex items-start gap-3">
            <span className="text-2xl">🔒</span>
            <div className="flex-1">
              <div className="font-bold text-sm mb-1">
                Datele tale sunt validate si protejate
              </div>
              <div className="text-xs space-y-0.5">
                <div>
                  Verificarea expira pe <strong>{verificationStatus.expires_at}</strong>
                  {verificationStatus.days_until_expiry !== null && (
                    <span className="ml-1">
                      ({verificationStatus.days_until_expiry} zile ramase, an universitar {verificationStatus.academic_year})
                    </span>
                  )}
                </div>
                <div className="text-amber-700 dark:text-amber-200 mt-1">
                  Pana atunci nu poti modifica: <em>Prenume, Nume, Data nasterii, Statia de domiciliu</em>.
                  Avatar si parola raman editabile.
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {loading ? (
        <p className="text-slate-600 dark:text-slate-300">Se incarca...</p>
      ) : (
        <>
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm mb-4">
          <h2 className="text-base font-semibold text-slate-700 dark:text-slate-200 mb-4">Fotografie de profil</h2>
          <div className="flex items-center gap-5">
            <div className="w-24 h-24 rounded-full overflow-hidden border-2 border-slate-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 flex items-center justify-center shrink-0">
              {(photoPreview || profilePhotoUrl) ? (
                <img
                  src={photoPreview || profilePhotoUrl}
                  alt="Poza profil"
                  className="w-full h-full object-cover"
                />
              ) : (
                <span className="text-4xl text-slate-400">👤</span>
              )}
            </div>
            <div className="flex-1 space-y-2">
              {photoLocked ? (
                <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400 bg-slate-100 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 rounded-xl px-3 py-2">
                  <span>Poza nu mai poate fi modificată după aprobare.</span>
                </div>
              ) : (
                <>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/png,image/jpeg,image/webp"
                    className="hidden"
                    onChange={onPhotoSelect}
                  />
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    className="w-full border border-slate-300 dark:border-slate-600 py-2 rounded-xl text-sm font-semibold hover:bg-slate-50 dark:hover:bg-slate-800"
                  >
                    {profilePhotoUrl ? 'Schimbă poza' : 'Încarcă poza'}
                  </button>
                  {photoFile && (
                    <button
                      type="button"
                      onClick={handleSavePhoto}
                      disabled={photoSaving}
                      className="w-full bg-slate-900 dark:bg-cyan-600 text-white py-2 rounded-xl text-sm font-semibold hover:bg-slate-800 dark:hover:bg-cyan-500 disabled:opacity-60"
                    >
                      {photoSaving ? 'Se salvează...' : 'Salvează poza nouă'}
                    </button>
                  )}
                </>
              )}
            </div>
          </div>
        </div>

        <form onSubmit={handleSave} className="space-y-4 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm">
          <div>
            <label className="block text-sm font-semibold text-slate-700 dark:text-slate-200 mb-1">
              Prenume {verificationStatus?.is_verified && <span title={"Frozen pana la " + verificationStatus.expires_at}>🔒</span>}
            </label>
            <input
              className={"w-full px-3 py-2 rounded-xl border border-slate-300 dark:border-slate-700 " + (verificationStatus?.is_verified ? "bg-slate-100 dark:bg-slate-800 text-slate-500 cursor-not-allowed" : "bg-white dark:bg-slate-950")}
              value={form.first_name}
              onChange={onChange('first_name')}
              required
              minLength={2}
              disabled={!!verificationStatus?.is_verified}
            />
          </div>
          <div>
            <label className="block text-sm font-semibold text-slate-700 dark:text-slate-200 mb-1">
              Nume {verificationStatus?.is_verified && <span title={"Frozen pana la " + verificationStatus.expires_at}>🔒</span>}
            </label>
            <input
              className={"w-full px-3 py-2 rounded-xl border border-slate-300 dark:border-slate-700 " + (verificationStatus?.is_verified ? "bg-slate-100 dark:bg-slate-800 text-slate-500 cursor-not-allowed" : "bg-white dark:bg-slate-950")}
              value={form.last_name}
              onChange={onChange('last_name')}
              required
              minLength={2}
              disabled={!!verificationStatus?.is_verified}
            />
          </div>
          <div>
            <label className="block text-sm font-semibold text-slate-700 dark:text-slate-200 mb-1">Telefon</label>
            <input
              className="w-full px-3 py-2 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950"
              value={form.phone}
              onChange={onChange('phone')}
            />
          </div>
          <div>
            <label className="block text-sm font-semibold text-slate-700 dark:text-slate-200 mb-1">
              Data nasterii {verificationStatus?.is_verified && <span title={"Frozen pana la " + verificationStatus.expires_at}>🔒</span>}
            </label>
            <input
              type="text"
              placeholder="YYYY-MM-DD"
              className={"w-full px-3 py-2 rounded-xl border border-slate-300 dark:border-slate-700 " + (verificationStatus?.is_verified ? "bg-slate-100 dark:bg-slate-800 text-slate-500 cursor-not-allowed" : "bg-white dark:bg-slate-950")}
              value={form.date_of_birth}
              onChange={onChange('date_of_birth')}
              disabled={!!verificationStatus?.is_verified}
            />
          </div>

          {user?.role === 'passenger' && (
            <>
            {/* Ruta personala (pentru reducerea studenteasca) */}
            <div className="border-t border-slate-200 dark:border-slate-700 pt-5">
              <h2 className="text-base font-semibold text-slate-700 dark:text-slate-200 mb-1">
                Ruta ta personala {verificationStatus?.is_verified && <span title={"Frozen pana la " + verificationStatus.expires_at}>🔒</span>}
              </h2>
              <p className="text-xs text-slate-500 dark:text-slate-400 mb-4">
                Reducerea de student (OUG 11/2024) se aplica pe ruta intre <strong>statia de domiciliu</strong> si <strong>statia universitatii</strong>. Pe alte rute se cumpara cu tarif intreg.
              </p>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="relative">
                  <label className="block text-sm font-semibold text-slate-700 dark:text-slate-200 mb-1">Statia de domiciliu</label>
                  {homeStation ? (
                    <div className="flex items-center justify-between gap-2 px-3 py-2 rounded-xl border border-emerald-300 dark:border-emerald-700 bg-emerald-50 dark:bg-emerald-900/20">
                      <div className="min-w-0">
                        <div className="text-sm font-semibold truncate text-emerald-900 dark:text-emerald-200">{homeStation.name}</div>
                        <div className="text-xs text-emerald-700 dark:text-emerald-300 truncate">{homeStation.city} · {homeStation.code}</div>
                      </div>
                      <button type="button" onClick={clearHomeStation}
                        className="text-xs text-emerald-700 dark:text-emerald-300 hover:underline shrink-0">
                        Schimba
                      </button>
                    </div>
                  ) : (
                    <>
                      <input
                        type="text"
                        value={stationQuery}
                        onChange={(e) => { setStationQuery(e.target.value); setStationOpen(true) }}
                        onFocus={() => setStationOpen(true)}
                        onBlur={() => setTimeout(() => setStationOpen(false), 180)}
                        placeholder="Caut stația (Iași, Cluj, Constanța, ...)"
                        className="w-full px-3 py-2 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950"
                        autoComplete="off"
                      />
                      {stationOpen && (
                        <div className="absolute z-10 mt-1 w-full bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl shadow-lg max-h-64 overflow-auto">
                          {stationLoading && <div className="p-3 text-xs text-slate-500">Caut...</div>}
                          {!stationLoading && stationResults.length === 0 && (
                            <div className="p-3 text-xs text-slate-500">Niciun rezultat</div>
                          )}
                          {stationResults.map((st) => (
                            <button
                              key={st.station_id}
                              type="button"
                              onMouseDown={(e) => { e.preventDefault(); selectHomeStation(st) }}
                              className="w-full text-left px-3 py-2 hover:bg-slate-100 dark:hover:bg-slate-700 text-sm"
                            >
                              <div className="font-semibold text-slate-900 dark:text-slate-100">{st.name}</div>
                              <div className="text-xs text-slate-500 dark:text-slate-400">{st.city} · {st.code}</div>
                            </button>
                          ))}
                        </div>
                      )}
                    </>
                  )}
                </div>

                <div>
                  <label className="block text-sm font-semibold text-slate-700 dark:text-slate-200 mb-1">Statia universitatii</label>
                  {universityStation ? (
                    <div className="px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800">
                      <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">{universityStation.name}</div>
                      <div className="text-xs text-slate-500 dark:text-slate-400">Setata automat de agentul universitar</div>
                    </div>
                  ) : (
                    <div className="px-3 py-2 rounded-xl border border-dashed border-slate-300 dark:border-slate-700 text-xs text-slate-500 dark:text-slate-400">
                      Nu este inca asociata o statie pentru universitatea ta.
                    </div>
                  )}
                </div>
              </div>
            </div>
            </>
          )}

          <button
            type="submit"
            disabled={saving}
            className="w-full bg-slate-900 text-white py-2 rounded-xl font-semibold hover:bg-slate-800 disabled:opacity-60 dark:bg-cyan-600 dark:hover:bg-cyan-500"
          >
            {saving ? 'Se salveaza...' : 'Salveaza profilul'}
          </button>
        </form>
        </>
      )}

      <div className="mt-8 space-y-3">
        <button
          type="button"
          onClick={handleExport}
          disabled={exporting}
          className="w-full border border-slate-300 dark:border-slate-700 py-2 rounded-xl font-semibold hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-60"
        >
          {exporting ? 'Se genereaza exportul...' : 'Export date (JSON)'}
        </button>
        <button
          type="button"
          onClick={handleDelete}
          disabled={deleting}
          className="w-full bg-red-600 text-white py-2 rounded-xl font-semibold hover:bg-red-700 disabled:opacity-60"
        >
          {deleting ? 'Se proceseaza...' : 'Dezactiveaza contul'}
        </button>
      </div>
    </div>
  )
}

export default Profile
