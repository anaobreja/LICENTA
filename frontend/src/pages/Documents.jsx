import { useEffect, useState } from 'react'
import { getMyDocuments, submitIdentityValidationRequest, getDocumentPhotoBlobUrl, extractIdData } from '../services/api'
import { useToast } from '../components/Toast.jsx'

const UNIVERSITATI = [
  'Universitatea Politehnica București (UPB)',
  'Academia de Studii Economice din București (ASE)',
  'Universitatea din București (UniBuc)',
  'Universitatea Babeș-Bolyai Cluj-Napoca (UBB)',
  'Universitatea Tehnică din Cluj-Napoca (UTCN)',
  'Universitatea de Vest din Timișoara (UVT)',
  'Universitatea Politehnica Timișoara (UPT)',
  'Universitatea Alexandru Ioan Cuza din Iași (UAIC)',
  'Universitatea Tehnică „Gheorghe Asachi" din Iași (TUIASI)',
  'Universitatea Transilvania din Brașov',
  'Universitatea din Craiova',
  'Universitatea Ovidius din Constanța',
  'Universitatea Ștefan cel Mare din Suceava',
  'Universitatea din Pitești',
  'Universitatea Dunărea de Jos din Galați',
  'Universitatea „Lucian Blaga" din Sibiu',
  'Universitatea de Medicină și Farmacie „Carol Davila" București',
  'Universitatea de Medicină și Farmacie Cluj-Napoca',
  'Universitatea de Medicină și Farmacie din Iași',
  'Universitatea de Arhitectură și Urbanism „Ion Mincu" București',
  'Academia Națională de Arte București',
  'Universitatea Națională de Arte din București',
  'Universitatea Națională de Muzică București',
  'Universitatea din Petroșani',
  'Universitatea „Valahia" din Târgoviște',
  'Universitatea „Aurel Vlaicu" din Arad',
  'Universitatea „Eftimie Murgu" din Reșița',
  'Universitatea „1 Decembrie 1918" din Alba Iulia',
  'Alta universitate',
]

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
  const [extracting, setExtracting] = useState(false)
  const [scanned, setScanned] = useState(false)
  // Legitimatie
  const [legitimationType, setLegitimationType] = useState('student_card')
  const [legitimationNumberMasked, setLegitimationNumberMasked] = useState('')
  const [legitimationPhoto, setLegitimationPhoto] = useState(null)
  const [universityName, setUniversityName] = useState('')
  const [yearOfStudy, setYearOfStudy] = useState('')
  const [viewingImage, setViewingImage] = useState(null)

  const loadState = async () => {
    try {
      const documentsData = await getMyDocuments()
      setDocuments(documentsData || [])
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
  const hasPendingRequest = pendingDocuments.length > 0

  // Pre-completează formularul din cererea pending existentă
  useEffect(() => {
    if (pendingDocuments.length > 0) {
      const doc = pendingDocuments[0]
      if (doc.ci_number !== undefined) setCiNumber(doc.ci_number || '')
      if (doc.ci_name !== undefined) setCiName(doc.ci_name || '')
      if (doc.ci_date_of_birth !== undefined) setCiDob(doc.ci_date_of_birth || '')
      if (doc.ci_sex !== undefined) setCiSex(doc.ci_sex || '')
      if (doc.document_number_masked) setLegitimationNumberMasked(doc.document_number_masked)
      if (doc.university_name) setUniversityName(doc.university_name)
      if (doc.year_of_study) setYearOfStudy(String(doc.year_of_study))
    }
  }, [documents])

  const getDocumentTypeLabel = (type) => {
    const labels = {
      identity_card: 'Carte de identitate',
      student_card: 'Legitimatie student',
      elev_card: 'Carnet de elev',
    }
    return labels[type] || type
  }

  const resetForm = () => {
    setCiNumber(''); setCiName(''); setCiDob(''); setCiSex(''); setScanned(false)
    setLegitimationType('student_card')
    setLegitimationNumberMasked('')
    setLegitimationPhoto(null)
    setUniversityName('')
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
    if (!legitimationPhoto && !hasPendingRequest) {
      setError('Încarcă poza legitimației.')
      return
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
    }

    try {
      const result = await submitIdentityValidationRequest({
        legitimation_type: legitimationType,
        legitimation_number_masked: legitimationNumberMasked,
        legitimation_photo: legitimationPhoto,
        university_name: legitimationType === 'student_card' ? universityName.trim() : '',
        year_of_study: legitimationType === 'student_card' ? parseInt(yearOfStudy, 10) : 0,
        ci_number: ciNumber,
        ci_name: ciName,
        ci_date_of_birth: ciDob,
        ci_sex: ciSex,
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

  const formDisabled = false

  const handleViewImage = async (doc) => {
    try {
      const blobUrl = await getDocumentPhotoBlobUrl(doc.id)
      setViewingImage({ ...doc, photoBlobUrl: blobUrl })
    } catch (err) {
      console.error('Could not load image', err)
      // Fallback: open modal with original path
      setViewingImage(doc)
    }
  }

  return (
    <div className="container mx-auto px-4 py-8 max-w-3xl">
      <h1 className="text-3xl font-bold mb-2 dark:text-white">Documente sursă</h1>
      <p className="text-slate-600 dark:text-slate-400 mb-6">
        Scanează CI-ul și încarcă legitimația de student pentru verificare.
      </p>

      {error && <div className="bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-200 p-3 rounded-xl mb-4">{error}</div>}
      {success && <div className="bg-green-50 dark:bg-green-950 border border-green-200 dark:border-green-800 text-green-700 dark:text-green-200 p-3 rounded-xl mb-4">{success}</div>}

      {hasPendingRequest && (
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

      <form onSubmit={onSubmit} className="bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-700 rounded-2xl p-5 mb-6 shadow-sm">
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
              ? <><span className="animate-spin inline-block">⟳</span> Se analizează CI... (prima rulare descarcă ~800MB)</>
              : scanned ? <>📷 Rescansează CI</> : <>📷 Scanează CI — extrage date automat</>}
          </button>

          {scanned && <p className="text-xs text-indigo-600 dark:text-indigo-400 text-center">Date extrase automat din MRZ — poți corecta manual dacă e nevoie.</p>}

          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <label className="block text-xs font-semibold mb-1 text-slate-600 dark:text-slate-400">Nume complet (din CI)</label>
              <input
                className="w-full border border-slate-300 dark:border-slate-600 rounded-xl px-3 py-2 text-sm dark:bg-slate-900 dark:text-white"
                placeholder="ex: Popescu Alexandru"
                value={ciName}
                onChange={(e) => setCiName(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-xs font-semibold mb-1 text-slate-600 dark:text-slate-400">Serie și număr CI</label>
              <input
                className="w-full border border-slate-300 dark:border-slate-600 rounded-xl px-3 py-2 text-sm dark:bg-slate-900 dark:text-white"
                placeholder="ex: XZ969111"
                value={ciNumber}
                onChange={(e) => setCiNumber(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-xs font-semibold mb-1 text-slate-600 dark:text-slate-400">Data nașterii</label>
              <input
                type="date"
                className="w-full border border-slate-300 dark:border-slate-600 rounded-xl px-3 py-2 text-sm dark:bg-slate-900 dark:text-white"
                value={ciDob}
                onChange={(e) => setCiDob(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-xs font-semibold mb-1 text-slate-600 dark:text-slate-400">Sex</label>
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
          </div>
        </div>

        <h3 className="font-bold text-lg mb-3 dark:text-white">2) Legitimatie (alege una)</h3>

        {legitimationType === 'student_card' && (
          <div className="space-y-3 mb-4">
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <label className="block text-sm font-semibold mb-2 dark:text-white">Universitate</label>
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
                <label className="block text-sm font-semibold mb-2 dark:text-white">An de studiu</label>
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
          </div>
        )}

        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <label className="block text-sm font-semibold mb-2 dark:text-white">Numar legitimatie (mascat)</label>
            <input
              className="w-full border border-slate-300 dark:border-slate-600 rounded-xl px-3 py-2 disabled:bg-slate-100 dark:bg-slate-900 dark:text-white dark:disabled:bg-slate-800"
              placeholder={legitimationType === 'student_card' ? 'ex: ST******' : 'ex: EL******'}
              value={legitimationNumberMasked}
              onChange={(e) => setLegitimationNumberMasked(e.target.value)}
              disabled={formDisabled}
              required
            />
          </div>
          <div>
            <label className="block text-sm font-semibold mb-2 dark:text-white">Poză legitimație (JPG, PNG, WEBP, max 5MB)</label>
            <input
              className="w-full border border-slate-300 dark:border-slate-600 rounded-xl px-3 py-2 file:mr-3 file:rounded-lg file:border-0 file:bg-slate-100 dark:file:bg-slate-800 file:px-3 file:py-1 disabled:bg-slate-100 dark:bg-slate-900 dark:text-white dark:disabled:bg-slate-800"
              type="file"
              accept="image/png,image/jpeg,image/webp"
              disabled={formDisabled}
              onChange={(e) => setLegitimationPhoto(e.target.files?.[0] || null)}
            />
          </div>
        </div>

        <button
          className="mt-6 bg-slate-900 dark:bg-blue-600 text-white px-4 py-2 rounded-xl hover:bg-slate-800 dark:hover:bg-blue-700 disabled:bg-slate-400 dark:disabled:bg-slate-600"
          disabled={formDisabled}
        >
          {hasPendingRequest ? 'Modifica si retrimite' : 'Trimite pentru validare'}
        </button>
      </form>

      <div className="bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-700 rounded-2xl p-5 shadow-sm mb-6">
        <h2 className="text-xl font-bold mb-2 dark:text-white">Documentele mele</h2>
        <p className="text-slate-600 dark:text-slate-400 mb-4 text-sm">Cererea ta curentă — poți modifica oricând înainte de aprobare.</p>
        {loading ? (
          <p className="text-slate-600 dark:text-slate-400">Se incarca...</p>
        ) : documents.length === 0 ? (
          <p className="text-slate-600 dark:text-slate-400">Nu ai documente adaugate inca.</p>
        ) : (
          <div className="space-y-4">
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
                        </div>
                      </div>

                      <div className="flex items-center justify-between pt-1">
                        <span className="inline-block bg-blue-200 dark:bg-blue-800 dark:text-blue-200 text-blue-800 text-xs font-semibold px-2 py-1 rounded">PENDING</span>
                        {doc.document_image_path && (
                          <button
                            onClick={() => handleViewImage(doc)}
                            className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
                          >
                            📷 Vezi poza legitimației
                          </button>
                        )}
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
                <h3 className="text-lg font-bold dark:text-white">{getDocumentTypeLabel(viewingImage.document_type)}</h3>
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
                  src={viewingImage.photoBlobUrl || viewingImage.document_image_path}
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

