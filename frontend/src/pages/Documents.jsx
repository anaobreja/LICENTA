import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getMyDocuments, submitIdentityValidationRequest, getDocumentPhotoBlobUrl, extractIdData, getUserProfile, getUserProfilePhotoBlobUrl, getMyCredentials, updateProfile } from '../services/api'
import StationCombobox from '../components/StationCombobox.jsx'
import { useToast } from '../components/Toast.jsx'
import { UNIVERSITATI } from '../constants/universities'

// Componenta pentru thumbnail document - incarca blob URL cu auth header
function DocumentThumbnail({ docId, side = 'front', alt, className, onError }) {
  const [src, setSrc] = useState(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let blobUrl = null
    let cancelled = false
    getDocumentPhotoBlobUrl(docId, side)
      .then((url) => {
        if (cancelled) {
          if (url) try { URL.revokeObjectURL(url) } catch (_) {}
          return
        }
        blobUrl = url
        setSrc(url)
      })
      .catch(() => {
        if (!cancelled) {
          setFailed(true)
          if (onError) onError()
        }
      })
    return () => {
      cancelled = true
      if (blobUrl) try { URL.revokeObjectURL(blobUrl) } catch (_) {}
    }
  }, [docId, side])

  if (failed || !src) {
    return (
      <div className={(className || '') + ' bg-slate-700 flex items-center justify-center text-xs text-slate-400'}>
        {failed ? 'N/A' : '...'}
      </div>
    )
  }
  return <img src={src} alt={alt} className={className} />
}


function Documents() {
  const toast = useToast()
  const [documents, setDocuments] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  // Câmpuri CI — editabile, completate din scan MRZ sau din cererea existentă
  const [ciNumber, setCiNumber] = useState('')
  const [ciName, setCiName] = useState('')
  const [ciDob, setCiDob] = useState('')
  const [ciSex, setCiSex] = useState('')
  const [ciAddress, setCiAddress] = useState('')
  const [extracting, setExtracting] = useState(false)
  const [scanned, setScanned] = useState(false)
  // Legitimatie
  const [legitimationType, setLegitimationType] = useState('student_card')
  const [legitimationNumberMasked, setLegitimationNumberMasked] = useState('')
  const [legitimationPhotoFront, setLegitimationPhotoFront] = useState(null)
  const [legitimationPhotoVerso, setLegitimationPhotoVerso] = useState(null)
  const [profilePhoto, setProfilePhoto] = useState(null)
  const [universityName, setUniversityName] = useState('')
  const [homeStation, setHomeStation] = useState(null)
  const [yearOfStudy, setYearOfStudy] = useState('')
  const [viewingImage, setViewingImage] = useState(null)
  const [currentProfilePhotoUrl, setCurrentProfilePhotoUrl] = useState(null)
  const [photoLocked, setPhotoLocked] = useState(false)
  const [myCredentials, setMyCredentials] = useState([])

  const loadState = async () => {
    try {
      const [documentsData, profileData, creds] = await Promise.all([
        getMyDocuments(),
        getUserProfile(),
        getMyCredentials().catch(() => []),
      ])
      setDocuments(documentsData || [])
      // Gara de domiciliu vine din profil (setata user in /profile, sincronizata
      // automat de backend la cumparare). Daca lipseste, userul trebuie sa o seteze.
      if (profileData?.home_station?.station_id) {
        setHomeStation({
          station_id: profileData.home_station.station_id,
          name: profileData.home_station.name || '',
          city: profileData.home_station.city || '',
          code: profileData.home_station.code || '',
        })
      } else {
        setHomeStation(null)
      }
      setMyCredentials(Array.isArray(creds) ? creds : [])
      setPhotoLocked(Array.isArray(creds) && creds.some(c => c.status === 'active'))
      if (profileData?.has_profile_photo && profileData?.user_id) {
        try {
          const url = await getUserProfilePhotoBlobUrl(profileData.user_id)
          setCurrentProfilePhotoUrl(url)
        } catch (_) {}
      }
    } catch (err) {
      setError(err.message || 'Nu am putut incarca documentele')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadState()
  }, [])

  const pendingDocuments = documents.filter((doc) => doc.status === 'pending')
  const approvedDocuments = documents.filter((doc) => doc.status === 'approved')
  const hasPendingRequest = pendingDocuments.length > 0
  const isRenewal = approvedDocuments.length > 0
  const activeCreds = myCredentials.filter(c => c.status === 'active')
  const renewalOpen = isRenewal && (
    activeCreds.length === 0 ||
    activeCreds.some(c => {
      const expiry = new Date(c.valid_until)
      const daysLeft = (expiry - new Date()) / (1000 * 60 * 60 * 24)
      return daysLeft <= 60
    })
  )
  const renewalBlockedUntil = isRenewal && !renewalOpen && activeCreds.length > 0
    ? (() => {
        const expiry = new Date(Math.min(...activeCreds.map(c => new Date(c.valid_until))))
        return new Date(expiry.getFullYear(), 7, 1) // 1 august
      })()
    : null

  // Pre-completează formularul
  useEffect(() => {
    const source = pendingDocuments[0] || approvedDocuments[0]
    if (!source) return
    if (source.ci_number !== undefined) setCiNumber(source.ci_number || '')
    if (source.ci_name !== undefined) setCiName(source.ci_name || '')
    if (source.ci_date_of_birth !== undefined) setCiDob(source.ci_date_of_birth || '')
    if (source.ci_sex !== undefined) setCiSex(source.ci_sex || '')
    if (source.ci_address !== undefined) setCiAddress(source.ci_address || '')
    if (source.university_name) setUniversityName(source.university_name)
    if (source.home_station_id && source.home_station_name) {
      setHomeStation({
        station_id: source.home_station_id,
        name: source.home_station_name,
        city: source.home_station_city || '',
        code: source.home_station_code || '',
      })
    }
    // La reînnoire nu pre-completăm nr. legitimație (e nouă) sau anul (avansează)
    if (!isRenewal) {
      if (source.document_number_masked) setLegitimationNumberMasked(source.document_number_masked)
      if (source.year_of_study) setYearOfStudy(String(source.year_of_study))
    }
  }, [documents])

  const formatDate = (iso) => {
    if (!iso) return '—'
    try { return new Date(iso).toLocaleDateString('ro-RO', { day: '2-digit', month: 'long', year: 'numeric' }) }
    catch { return iso }
  }

  const getDocumentTypeLabel = (type) => {
    const labels = {
      identity_card: 'Carte de identitate',
      student_card: 'Legitimatie student',
      elev_card: 'Carnet de elev',
    }
    return labels[type] || type
  }

  const resetForm = () => {
    setCiNumber(''); setCiName(''); setCiDob(''); setCiSex(''); setCiAddress(''); setScanned(false)
    setLegitimationType('student_card')
    setLegitimationNumberMasked('')
    setLegitimationPhotoFront(null)
    setLegitimationPhotoVerso(null)
    setProfilePhoto(null)
    setUniversityName('')
    setHomeStation(null)
    setYearOfStudy('')
  }

  const onSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setSuccess('')

    if (!ciNumber.trim() && !hasPendingRequest) {
      setError('Scanează buletinul sau completează manual datele CI.')
      return
    }
    if (!legitimationNumberMasked.trim()) {
      setError('Completează numărul legitimației.')
      return
    }
    const needNewPhotos = !hasPendingRequest
    if (needNewPhotos && (!legitimationPhotoFront || !legitimationPhotoVerso)) {
      setError('Încarcă ambele poze ale legitimației: față și verso (verso = semnătură).')
      return
    }
    if (hasPendingRequest && !legitimationPhotoFront && !legitimationPhotoVerso) {
      const pending = pendingDocuments[0]
      if (!pending?.has_photo || !pending?.has_photo_verso) {
        setError('Cererea existentă nu are ambele poze. Reîncarcă fața și verso-ul.')
        return
      }
    }
    if (legitimationType === 'student_card') {
      if (!universityName.trim()) {
        setError('Selectează universitatea.')
        return
      }
      if (!yearOfStudy) {
        setError('Selectează anul de studiu.')
        return
      }
      if (!homeStation?.station_id) {
        setError('Selecteaza gara ta de provenienta (necesara pentru ruta personala student).')
        return
      }
    }

    try {
      const result = await submitIdentityValidationRequest({
        legitimation_type: legitimationType,
        legitimation_number_masked: legitimationNumberMasked,
        legitimation_photo_front: legitimationPhotoFront,
        legitimation_photo_verso: legitimationPhotoVerso,
        profile_photo: profilePhoto,
        university_name: legitimationType === 'student_card' ? universityName.trim() : '',
        year_of_study: legitimationType === 'student_card' ? parseInt(yearOfStudy, 10) : 0,
        ci_number: ciNumber,
        ci_name: ciName,
        ci_date_of_birth: ciDob,
        ci_sex: ciSex,
        ci_address: ciAddress,
        home_station_id: homeStation?.station_id || '',
      })

      resetForm()
      setSuccess(result.message || 'Cererea a fost trimisă cu succes.')
      toast(String(result.message || 'Cererea a fost trimisă cu succes.'), 'success')
      await loadState()
    } catch (err) {
      const msg = typeof err?.message === 'string' ? err.message : 'Eroare la trimiterea cererii'
      setError(msg)
      toast(msg, 'error')
    }
  }

  const formDisabled = isRenewal ? !renewalOpen : false

  const handleViewImage = async (doc, side = 'front') => {
    try {
      const url = await getDocumentPhotoBlobUrl(doc.id, side)
      setViewingImage({ ...doc, photoBlobUrl: url, _customLabel: side === 'verso' ? 'Document verso' : 'Document fata' })
    } catch (e) {
      setMsg({ type: 'error', text: 'Nu am putut incarca poza ' + side + ': ' + e.message })
    }
  }

  return (
    <div className="container mx-auto px-4 py-8 max-w-3xl">
      <h1 className="text-3xl font-bold mb-2 dark:text-white">Documente sursă</h1>
      <p className="text-slate-600 dark:text-slate-400 mb-6">
        {isRenewal
          ? 'Reînnoire anuală — încarcă noua legitimație vizată pentru anul universitar curent.'
          : 'Prima înregistrare — completează datele din CI, adaugă poza de profil și legitimația student.'}
      </p>

      {error && <div className="bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-200 p-3 rounded-xl mb-4">{error}</div>}
      {success && <div className="bg-green-50 dark:bg-green-950 border border-green-200 dark:border-green-800 text-green-700 dark:text-green-200 p-3 rounded-xl mb-4">{success}</div>}

      {renewalBlockedUntil && (
        <div className="flex items-center gap-3 bg-slate-100 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 rounded-xl p-4 mb-6">
          <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          <div>
            <div className="font-semibold text-slate-700 dark:text-slate-300">Reînnoire indisponibilă momentan</div>
            <p className="text-sm mt-0.5">
              Legitimațiile sunt valabile până în septembrie {renewalBlockedUntil.getFullYear()}. Reînnoirea va fi disponibilă din{' '}
              <strong>1 august {renewalBlockedUntil.getFullYear()}</strong>.
            </p>
          </div>
        </div>
      )}

      {!formDisabled && hasPendingRequest && (
        <div className="bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 rounded-xl p-4 mb-6">
          <div className="flex items-start gap-3">
            <div className="text-blue-600 dark:text-blue-400 text-lg">ℹ️</div>
            <div>
              <div className="font-semibold text-blue-900 dark:text-blue-200">Ai o cerere deschisa</div>
              <p className="text-sm text-blue-800 dark:text-blue-300 mt-1">
                Poti modifica cererea in asteptare si o poti retrimite.
              </p>
            </div>
          </div>
        </div>
      )}

      {!formDisabled && <form onSubmit={onSubmit} className="bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-700 rounded-2xl p-5 mb-6 shadow-sm">

        {/* Reînnoire: arată date CI din dosar aprobat — read-only */}
        {isRenewal ? (
          <div className="mb-5 rounded-xl bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 p-4">
            <div className="flex items-center gap-2 mb-3">
              <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4 text-slate-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
              <span className="text-sm font-semibold text-slate-600 dark:text-slate-400">Date identitate verificate (din înregistrarea inițială)</span>
            </div>
            <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm text-slate-700 dark:text-slate-300">
              <div>Nume: <strong>{ciName || '—'}</strong></div>
              <div>Nr. CI: <strong>{ciNumber || '—'}</strong></div>
              <div>Data nașterii: <strong>{ciDob || '—'}</strong></div>
              <div>Sex: <strong>{ciSex === 'M' ? 'Masculin' : ciSex === 'F' ? 'Feminin' : '—'}</strong></div>
              {ciAddress && <div className="col-span-2">Domiciliu: <strong>{ciAddress}</strong></div>}
            </div>
            {currentProfilePhotoUrl && (
              <div className="flex items-center gap-3 mt-3 pt-3 border-t border-slate-200 dark:border-slate-700">
                <img src={currentProfilePhotoUrl} alt="Profil" className="w-12 h-12 rounded-full object-cover border-2 border-slate-200 dark:border-slate-600" />
                <span className="text-sm text-slate-500 dark:text-slate-400">Fotografie de profil verificată</span>
              </div>
            )}
          </div>
        ) : (
          <>
            <h3 className="font-bold text-lg mb-3 dark:text-white">1) Carte de identitate — scanare automată</h3>

        {/* Input ascuns pentru cameră */}
        <input
          id="id-camera-input"
          type="file"
          accept="image/png,image/jpeg,image/webp"
          capture="environment"
          className="hidden"
          onChange={async (e) => {
            const file = e.target.files?.[0] || null
            if (!file) return
            setExtracting(true)
            try {
              const res = await extractIdData(file)
              if (res.success && res.data) {
                const d = res.data
                setCiNumber(d.document_number || '')
                setCiName(`${d.surname || ''} ${d.given_names || ''}`.trim())
                setCiDob(d.date_of_birth || '')
                setCiSex(d.sex || '')
                setScanned(true)
              } else {
                setError(res.message || 'Nu s-au putut extrage datele. Încearcă cu o imagine mai clară.')
              }
            } catch (err) {
              setError(err.message)
            } finally {
              setExtracting(false)
              e.target.value = ''
            }
          }}
        />

        {/* Buton scanare + câmpuri editabile */}
        <div className="mb-6 space-y-3">
          <button
            type="button"
            disabled={extracting}
            onClick={() => document.getElementById('id-camera-input').click()}
            className="w-full flex items-center justify-center gap-2 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white font-bold px-4 py-3 rounded-xl transition text-base"
          >
            {extracting
              ? <><span className="animate-spin inline-block">⟳</span> Se analizează CI... (poate dura 10–30 secunde)</>
              : scanned ? <>📷 Rescansează CI</> : <>📷 Scanează CI — extrage date automat</>}
          </button>

          {scanned && <p className="text-xs text-indigo-600 dark:text-indigo-400 text-center">Date extrase automat din MRZ — poți corecta manual dacă e nevoie.</p>}

          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <label className="block text-xs font-semibold mb-1 text-slate-600 dark:text-slate-400">Nume complet (din CI) <span className="text-red-500">*</span></label>
              <input
                className="w-full border border-slate-300 dark:border-slate-600 rounded-xl px-3 py-2 text-sm dark:bg-slate-900 dark:text-white"
                placeholder="ex: Popescu Alexandru"
                value={ciName}
                onChange={(e) => setCiName(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-xs font-semibold mb-1 text-slate-600 dark:text-slate-400">Serie și număr CI <span className="text-red-500">*</span></label>
              <input
                className="w-full border border-slate-300 dark:border-slate-600 rounded-xl px-3 py-2 text-sm dark:bg-slate-900 dark:text-white"
                placeholder="ex: XZ969111"
                value={ciNumber}
                onChange={(e) => setCiNumber(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-xs font-semibold mb-1 text-slate-600 dark:text-slate-400">Data nașterii <span className="text-red-500">*</span></label>
              <input
                type="date"
                className="w-full border border-slate-300 dark:border-slate-600 rounded-xl px-3 py-2 text-sm dark:bg-slate-900 dark:text-white"
                value={ciDob}
                onChange={(e) => setCiDob(e.target.value)}
              />
              {ciDob && (() => {
                const dob = new Date(ciDob)
                const today = new Date()
                const age = today.getFullYear() - dob.getFullYear() - ((today.getMonth() + 1 < dob.getMonth() + 1 || (today.getMonth() === dob.getMonth() && today.getDate() < dob.getDate())) ? 1 : 0)
                return age >= 30 ? (
                  <p className="text-xs text-red-600 dark:text-red-400 mt-1 font-semibold">
                    Vârsta ({age} ani) depășește limita de 30 de ani — nu poți beneficia de reducerea CFR.
                  </p>
                ) : null
              })()}
            </div>
            <div>
              <label className="block text-xs font-semibold mb-1 text-slate-600 dark:text-slate-400">Sex <span className="text-red-500">*</span></label>
              <select
                className="w-full border border-slate-300 dark:border-slate-600 rounded-xl px-3 py-2 text-sm dark:bg-slate-900 dark:text-white"
                value={ciSex}
                onChange={(e) => setCiSex(e.target.value)}
              >
                <option value="">— selectează —</option>
                <option value="M">Masculin</option>
                <option value="F">Feminin</option>
              </select>
            </div>
            <div className="md:col-span-2">
              <label className="block text-xs font-semibold mb-1 text-slate-600 dark:text-slate-400">
                Domiciliu (din CI) <span className="text-red-500">*</span>
              </label>
              <input
                className="w-full border border-slate-300 dark:border-slate-600 rounded-xl px-3 py-2 text-sm dark:bg-slate-900 dark:text-white"
                placeholder="ex: Str. Florilor nr. 5, Cluj-Napoca, jud. Cluj"
                value={ciAddress}
                onChange={(e) => setCiAddress(e.target.value)}
              />
              <p className="text-xs text-slate-400 mt-1">Necesar pentru verificarea dreptului la reducere pe ruta domiciliu–universitate.</p>
            </div>
          </div>
        </div>

          </>
        )}

        <h3 className="font-bold text-lg mb-3 dark:text-white">
          {isRenewal ? '1) Legitimație — reînnoire anuală' : '2) Legitimatie (alege una)'}
        </h3>

        {legitimationType === 'student_card' && (
          <div className="space-y-3 mb-4">
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <label className="block text-sm font-semibold mb-2 dark:text-white">Universitate <span className="text-red-500">*</span></label>
                <select
                  className="w-full border border-slate-300 dark:border-slate-600 rounded-xl px-3 py-2 dark:bg-slate-900 dark:text-white"
                  value={universityName === '' || UNIVERSITATI.includes(universityName) ? universityName : 'Alta universitate'}
                  onChange={(e) => {
                    if (e.target.value === 'Alta universitate') {
                      setUniversityName('Alta universitate')
                    } else {
                      setUniversityName(e.target.value)
                    }
                  }}
                  disabled={formDisabled}
                  required
                >
                  <option value="">Selectează universitatea</option>
                  {UNIVERSITATI.map((u) => (
                    <option key={u} value={u}>{u}</option>
                  ))}
                </select>
                {universityName === 'Alta universitate' && (
                  <input
                    className="w-full mt-2 border border-slate-300 dark:border-slate-600 rounded-xl px-3 py-2 dark:bg-slate-900 dark:text-white"
                    placeholder="Numele universității tale"
                    onChange={(e) => setUniversityName(e.target.value)}
                    required
                    autoFocus
                  />
                )}
              </div>
              <div>
                <label className="block text-sm font-semibold mb-2 dark:text-white">An de studiu <span className="text-red-500">*</span></label>
                <select
                  className="w-full border border-slate-300 dark:border-slate-600 rounded-xl px-3 py-2 dark:bg-slate-900 dark:text-white"
                  value={yearOfStudy}
                  onChange={(e) => setYearOfStudy(e.target.value)}
                  disabled={formDisabled}
                  required
                >
                  <option value="">Selectează anul</option>
                  <option value="1">Licență 1</option>
                  <option value="2">Licență 2</option>
                  <option value="3">Licență 3</option>
                  <option value="4">Licență 4</option>
                  <option value="5">Master 1</option>
                  <option value="6">Master 2</option>
                </select>
              </div>
            </div>
            <div className="mt-3">
              <label className="block text-sm font-semibold mb-2 dark:text-white">
                Gara de provenienta (pentru ruta personala) <span className="text-red-500">*</span>
              </label>
              {homeStation?.station_id ? (
                <div className="flex items-center justify-between gap-3 px-3 py-2 rounded-xl border-2 border-emerald-300 dark:border-emerald-700 bg-emerald-50 dark:bg-emerald-900/20">
                  <div className="min-w-0">
                    <div className="text-sm font-semibold truncate text-emerald-900 dark:text-emerald-200">
                      {homeStation.name}
                    </div>
                    <div className="text-xs text-emerald-700 dark:text-emerald-300 truncate">
                      {homeStation.city} {homeStation.code ? `— ${homeStation.code}` : ''}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setHomeStation(null)}
                    className="text-xs font-semibold text-emerald-700 dark:text-emerald-300 hover:underline shrink-0"
                  >
                    Schimbă
                  </button>
                </div>
              ) : (
                <div className="space-y-1.5">
                  <StationCombobox
                    placeholder="Caută gara de domiciliu..."
                    value={homeStation}
                    onChange={async (s) => {
                      setHomeStation(s)
                      if (s?.station_id) {
                        try { await updateProfile({ home_station_id: s.station_id }) } catch (_) {}
                      }
                    }}
                  />
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    Alege gara <strong>din județul tău</strong>, cât mai aproape de adresa din CI.
                  </p>
                </div>
              )}
            </div>
          </div>
        )}

        <div className="mb-4">
          <label className="block text-sm font-semibold mb-2 dark:text-white">Număr legitimație (mascat) <span className="text-red-500">*</span></label>
          <input
            className="w-full border border-slate-300 dark:border-slate-600 rounded-xl px-3 py-2 dark:bg-slate-900 dark:text-white"
            placeholder="ex: ST******"
            value={legitimationNumberMasked}
            onChange={(e) => setLegitimationNumberMasked(e.target.value)}
            disabled={formDisabled}
            required
          />
        </div>

        <div className="grid gap-4 md:grid-cols-2 mb-4">
          <div>
            <label className="block text-sm font-semibold mb-2 dark:text-white">
              Legitimație — față <span className="text-red-500">*</span>
            </label>
            <input
              className="w-full border border-slate-300 dark:border-slate-600 rounded-xl px-3 py-2 file:mr-3 file:rounded-lg file:border-0 file:bg-slate-100 dark:file:bg-slate-800 file:px-3 file:py-1 dark:bg-slate-900 dark:text-white"
              type="file"
              accept="image/png,image/jpeg,image/webp"
              disabled={formDisabled}
              onChange={(e) => setLegitimationPhotoFront(e.target.files?.[0] || null)}
            />
          </div>
          <div>
            <label className="block text-sm font-semibold mb-2 dark:text-white">
              Legitimație — verso (semnătură) <span className="text-red-500">*</span>
            </label>
            <input
              className="w-full border border-slate-300 dark:border-slate-600 rounded-xl px-3 py-2 file:mr-3 file:rounded-lg file:border-0 file:bg-slate-100 dark:file:bg-slate-800 file:px-3 file:py-1 dark:bg-slate-900 dark:text-white"
              type="file"
              accept="image/png,image/jpeg,image/webp"
              disabled={formDisabled}
              onChange={(e) => setLegitimationPhotoVerso(e.target.files?.[0] || null)}
            />
          </div>
        </div>

        {!isRenewal && (
          <div className="mb-2">
            <label className="block text-sm font-semibold mb-2 dark:text-white">
              Fotografie de profil <span className="text-red-500">*</span>
            </label>
            <div className="flex items-center gap-3 mb-2">
              {currentProfilePhotoUrl && (
                <img
                  src={currentProfilePhotoUrl}
                  alt="Poza profil curentă"
                  className="w-14 h-14 rounded-full object-cover border-2 border-slate-200 dark:border-slate-600 shrink-0"
                />
              )}
              <div className="flex-1">
                <input
                  className="w-full border border-slate-300 dark:border-slate-600 rounded-xl px-3 py-2 file:mr-3 file:rounded-lg file:border-0 file:bg-slate-100 dark:file:bg-slate-800 file:px-3 file:py-1 dark:bg-slate-900 dark:text-white"
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  onChange={(e) => setProfilePhoto(e.target.files?.[0] || null)}
                />
                <p className="text-xs text-slate-500 mt-1">Va fi verificată de agentul universitar și afișată agentului de tren.</p>
              </div>
            </div>
          </div>
        )}

        <button
          className="mt-6 bg-slate-900 dark:bg-blue-600 text-white px-4 py-2 rounded-xl hover:bg-slate-800 dark:hover:bg-blue-700 disabled:bg-slate-400 dark:disabled:bg-slate-600 disabled:cursor-not-allowed"
          disabled={formDisabled}
        >
          {hasPendingRequest ? 'Modifică și retrimite' : 'Trimite pentru validare'}
        </button>
      </form>}

      <div className="bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-700 rounded-2xl p-5 shadow-sm mb-6">
        <h2 className="text-xl font-bold mb-2 dark:text-white">Documentele mele</h2>
        <p className="text-slate-600 dark:text-slate-400 mb-4 text-sm">
          {formDisabled ? 'Identitatea ta a fost verificată și aprobată.' : 'Cererea ta curentă — poți modifica oricând înainte de aprobare.'}
        </p>
        {loading ? (
          <p className="text-slate-600 dark:text-slate-400">Se incarca...</p>
        ) : documents.length === 0 ? (
          <p className="text-slate-600 dark:text-slate-400">Nu ai documente adaugate inca.</p>
        ) : (
          <div className="space-y-4">
            {approvedDocuments.length > 0 && (
              <div className="border border-emerald-200 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-950/40 rounded-xl p-4">
                <div className="flex items-center gap-2 mb-3">
                  <span className="inline-block bg-emerald-500 text-white text-xs font-bold px-2 py-1 rounded">APROBAT</span>
                  <span className="text-sm font-semibold text-emerald-800 dark:text-emerald-300">Cerere aprobată — identitate verificată</span>
                </div>
                <div className="space-y-2">
                  {approvedDocuments.map((doc) => (
                    <div key={doc.id} className="bg-white dark:bg-slate-900 border border-emerald-100 dark:border-emerald-900 rounded-lg p-4 space-y-3 text-sm">
                      <div>
                        <div className="text-xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-1">Carte de identitate</div>
                        <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-slate-800 dark:text-slate-200">
                          <div>Nume: <strong>{doc.ci_name || '—'}</strong></div>
                          <div>Serie/Nr: <strong>{doc.ci_number || '—'}</strong></div>
                          <div>Data nașterii: <strong>{doc.ci_date_of_birth || '—'}</strong></div>
                          <div>Sex: <strong>{doc.ci_sex === 'M' ? 'Masculin' : doc.ci_sex === 'F' ? 'Feminin' : '—'}</strong></div>
                          {doc.ci_address && <div className="col-span-2">Domiciliu: <strong>{doc.ci_address}</strong></div>}
                        </div>
                      </div>
                      <div className="border-t border-emerald-100 dark:border-emerald-900" />
                      <div>
                        <div className="text-xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-1">Legitimație student</div>
                        <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-slate-800 dark:text-slate-200">
                          <div>Nr. legitimație: <strong>{doc.document_number_masked || '—'}</strong></div>
                          {doc.year_of_study && (
                            <div>An: <strong>{doc.year_of_study <= 4 ? `Licență ${doc.year_of_study}` : `Master ${doc.year_of_study - 4}`}</strong></div>
                          )}
                          {doc.university_name && (
                            <div className="col-span-2">Universitate: <strong>{doc.university_name}</strong></div>
                          )}
                          {(doc.home_station_name || doc.home_station_id) && (
                            <div className="col-span-2 mt-1 pt-1 border-t border-blue-100 dark:border-blue-900">
                              Gara de proveniență:{' '}
                              <strong>{doc.home_station_name || `Stație ID ${doc.home_station_id}`}</strong>
                              {doc.home_station_city && doc.home_station_city !== doc.home_station_name && (
                                <span className="text-xs text-slate-500 dark:text-slate-400 ml-1">({doc.home_station_city})</span>
                              )}
                              {doc.home_station_code && (
                                <span className="text-xs text-slate-400 dark:text-slate-500 ml-1">· {doc.home_station_code}</span>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                      {/* Thumbnails: profil + fata + verso legitimatie */}
                      <div className="border-t border-emerald-100 dark:border-emerald-900" />
                      <div className="flex flex-wrap gap-3 items-end pt-1">
                        {currentProfilePhotoUrl && (
                          <button
                            type="button"
                            onClick={() => setViewingImage({ ...doc, _customImage: currentProfilePhotoUrl, _customLabel: 'Poza profil' })}
                            className="group flex flex-col items-center gap-1"
                            title="Click pentru zoom"
                          >
                            <img
                              src={currentProfilePhotoUrl}
                              alt="Poza profil"
                              className="w-20 h-20 rounded-full border-2 border-emerald-700 object-cover group-hover:border-emerald-300 transition"
                            />
                            <span className="text-xs text-emerald-700 dark:text-emerald-300">Profil</span>
                          </button>
                        )}
                        {(doc.has_front_image || doc.has_photo || doc.document_image_path) && (
                          <button
                            type="button"
                            onClick={() => handleViewImage(doc, 'front')}
                            className="group flex flex-col items-center gap-1"
                            title="Click pentru zoom"
                          >
                            <DocumentThumbnail
                              docId={doc.id}
                              side="front"
                              alt="Document fata"
                              className="w-20 h-20 rounded-lg border-2 border-emerald-700 object-cover group-hover:border-emerald-300 transition"
                            />
                            <span className="text-xs text-emerald-700 dark:text-emerald-300">
                              {doc.document_type === 'student_card' || doc.document_type === 'student_id'
                                ? 'Legit. fata'
                                : doc.document_type === 'passport' ? 'Pasaport' : 'CI fata'}
                            </span>
                          </button>
                        )}
                        {(doc.has_verso_image || doc.has_photo_verso || doc.document_image_path_verso) && (
                          <button
                            type="button"
                            onClick={() => handleViewImage(doc, 'verso')}
                            className="group flex flex-col items-center gap-1"
                            title="Click pentru zoom"
                          >
                            <DocumentThumbnail
                              docId={doc.id}
                              side="verso"
                              alt="Document verso"
                              className="w-20 h-20 rounded-lg border-2 border-emerald-700 object-cover group-hover:border-emerald-300 transition"
                            />
                            <span className="text-xs text-emerald-700 dark:text-emerald-300">
                              {doc.document_type === 'student_card' || doc.document_type === 'student_id'
                                ? 'Legit. verso' : 'CI verso'}
                            </span>
                          </button>
                        )}
                      </div>

                      {myCredentials.filter(c => c.status === 'active').length > 0 && (
                        <>
                          <div className="border-t border-emerald-100 dark:border-emerald-900" />
                          <div>
                            <div className="text-xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-1">Valabilitate credențiale</div>
                            <div className="space-y-1">
                              {myCredentials.filter(c => c.status === 'active').map(c => (
                                <div key={c.id} className="flex items-center justify-end text-sm">
                                  <span className="font-semibold text-emerald-700 dark:text-emerald-400">
                                    până la {formatDate(c.valid_until)}
                                  </span>
                                </div>
                              ))}
                            </div>
                          </div>
                        </>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {pendingDocuments.length > 0 && (
              <div className="border border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-950 rounded-xl p-4">
                <h3 className="font-semibold text-blue-900 dark:text-blue-200 mb-3 text-sm">📋 CEREREA ACTUALA</h3>
                <div className="space-y-2">
                  {pendingDocuments.map((doc) => (
                    <div key={doc.id} className="bg-white dark:bg-slate-900 border border-blue-100 dark:border-blue-800 rounded-lg p-4 space-y-3 text-sm">

                      {/* Carte de identitate */}
                      <div>
                        <div className="text-xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-1">Carte de identitate</div>
                        <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-slate-800 dark:text-slate-200">
                          <div>Nume: <strong>{doc.ci_name || '—'}</strong></div>
                          <div>Serie/Nr: <strong>{doc.ci_number || '—'}</strong></div>
                          <div>Data nașterii: <strong>{doc.ci_date_of_birth || '—'}</strong></div>
                          <div>Sex: <strong>{doc.ci_sex === 'M' ? 'Masculin' : doc.ci_sex === 'F' ? 'Feminin' : '—'}</strong></div>
                          {doc.ci_address && <div className="col-span-2">Domiciliu: <strong>{doc.ci_address}</strong></div>}
                        </div>
                      </div>

                      <div className="border-t border-blue-100 dark:border-blue-900" />

                      {/* Legitimație student */}
                      <div>
                        <div className="text-xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-1">Legitimație student</div>
                        <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-slate-800 dark:text-slate-200">
                          <div>Nr. legitimație: <strong>{doc.document_number_masked || '—'}</strong></div>
                          {doc.year_of_study && (
                            <div>An: <strong>{doc.year_of_study <= 4 ? `Licență ${doc.year_of_study}` : `Master ${doc.year_of_study - 4}`}</strong></div>
                          )}
                          {doc.university_name && (
                            <div className="col-span-2">Universitate: <strong>{doc.university_name}</strong></div>
                          )}
                          {(doc.home_station_name || doc.home_station_id) && (
                            <div className="col-span-2 mt-1 pt-1 border-t border-blue-100 dark:border-blue-900">
                              Gara de proveniență:{' '}
                              <strong>{doc.home_station_name || `Stație ID ${doc.home_station_id}`}</strong>
                              {doc.home_station_city && doc.home_station_city !== doc.home_station_name && (
                                <span className="text-xs text-slate-500 dark:text-slate-400 ml-1">({doc.home_station_city})</span>
                              )}
                              {doc.home_station_code && (
                                <span className="text-xs text-slate-400 dark:text-slate-500 ml-1">· {doc.home_station_code}</span>
                              )}
                            </div>
                          )}
                        </div>
                      </div>

                      <div className="space-y-3 pt-1">
                          <div className="flex items-center justify-between">
                            <span className="inline-block bg-blue-200 dark:bg-blue-800 dark:text-blue-200 text-blue-800 text-xs font-semibold px-2 py-1 rounded">{doc.status?.toUpperCase() || 'PENDING'}</span>
                          </div>
                          <div className="flex flex-wrap gap-3 items-end">
                            {currentProfilePhotoUrl && (
                              <button
                                type="button"
                                onClick={() => setViewingImage({ ...doc, _customImage: currentProfilePhotoUrl, _customLabel: 'Poza profil' })}
                                className="group flex flex-col items-center gap-1"
                                title="Click pentru zoom"
                              >
                                <img
                                  src={currentProfilePhotoUrl}
                                  alt="Poza profil"
                                  className="w-20 h-20 rounded-full border-2 border-blue-700 object-cover group-hover:border-blue-300 transition"
                                />
                                <span className="text-xs text-blue-200 dark:text-blue-300">Profil</span>
                              </button>
                            )}
                            {(doc.has_front_image || doc.has_photo || doc.document_image_path) && (
                              <button
                                type="button"
                                onClick={() => handleViewImage(doc, 'front')}
                                className="group flex flex-col items-center gap-1"
                                title="Click pentru zoom"
                              >
                                <DocumentThumbnail
                                  docId={doc.id}
                                  side="front"
                                  alt="Document fata"
                                  className="w-20 h-20 rounded-lg border-2 border-blue-700 object-cover group-hover:border-blue-300 transition"
                                />
                                <span className="text-xs text-blue-200 dark:text-blue-300">
                                  {doc.document_type === 'student_card' || doc.document_type === 'student_id'
                                    ? 'Legit. fata'
                                    : doc.document_type === 'passport' ? 'Pasaport' : 'CI fata'}
                                </span>
                              </button>
                            )}
                            {(doc.has_verso_image || doc.has_photo_verso || doc.document_image_path_verso) && (
                              <button
                                type="button"
                                onClick={() => handleViewImage(doc, 'verso')}
                                className="group flex flex-col items-center gap-1"
                                title="Click pentru zoom"
                              >
                                <DocumentThumbnail
                                  docId={doc.id}
                                  side="verso"
                                  alt="Document verso"
                                  className="w-20 h-20 rounded-lg border-2 border-blue-700 object-cover group-hover:border-blue-300 transition"
                                />
                                <span className="text-xs text-blue-200 dark:text-blue-300">
                                  {doc.document_type === 'student_card' || doc.document_type === 'student_id'
                                    ? 'Legit. verso' : 'CI verso'}
                                </span>
                              </button>
                            )}
                          </div>
                        </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {viewingImage && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
            <div className="bg-white dark:bg-slate-950 rounded-2xl max-w-2xl w-full max-h-96 overflow-auto">
              <div className="p-4 border-b border-slate-200 dark:border-slate-700 flex justify-between items-center">
                <h3 className="text-lg font-bold dark:text-white">{viewingImage._customLabel || getDocumentTypeLabel(viewingImage.document_type)}</h3>
                <button
                  onClick={() => {
                    if (viewingImage?.photoBlobUrl) {
                      try { URL.revokeObjectURL(viewingImage.photoBlobUrl) } catch (_) {}
                    }
                    setViewingImage(null)
                  }}
                  className="text-2xl text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-400"
                >
                  ✕
                </button>
              </div>
              <div className="p-4 flex justify-center">
                <img
                  src={viewingImage._customImage || viewingImage.photoBlobUrl || viewingImage.document_image_path}
                  alt={getDocumentTypeLabel(viewingImage.document_type)}
                  className="max-w-full max-h-80 rounded-lg"
                />
              </div>
            </div>
          </div>
        )}
    </div>
  )
}

export default Documents

