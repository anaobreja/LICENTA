import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { deleteAccount, exportUserData, getUserProfile, getUserProfilePhotoBlobUrl, getMyCredentials, updateProfile, updateProfilePhoto } from '../services/api'

function Profile({ user, onAccountDeleted }) {
  const navigate = useNavigate()
  const fileInputRef = useRef(null)
  const [form, setForm] = useState({
    first_name: '',
    last_name: '',
    phone: '',
    date_of_birth: '',
  })
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
      await updateProfile({
        first_name: form.first_name.trim(),
        last_name: form.last_name.trim(),
        phone: form.phone.trim() || null,
        date_of_birth: form.date_of_birth.trim() || null,
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
            <label className="block text-sm font-semibold text-slate-700 dark:text-slate-200 mb-1">Prenume</label>
            <input
              className="w-full px-3 py-2 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950"
              value={form.first_name}
              onChange={onChange('first_name')}
              required
              minLength={2}
            />
          </div>
          <div>
            <label className="block text-sm font-semibold text-slate-700 dark:text-slate-200 mb-1">Nume</label>
            <input
              className="w-full px-3 py-2 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950"
              value={form.last_name}
              onChange={onChange('last_name')}
              required
              minLength={2}
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
            <label className="block text-sm font-semibold text-slate-700 dark:text-slate-200 mb-1">Data nasterii</label>
            <input
              type="text"
              placeholder="YYYY-MM-DD"
              className="w-full px-3 py-2 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950"
              value={form.date_of_birth}
              onChange={onChange('date_of_birth')}
            />
          </div>
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
