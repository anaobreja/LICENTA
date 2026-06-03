import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { deleteAccount, exportUserData, getUserProfile, updateProfile } from '../services/api'

function Profile({ user, onAccountDeleted }) {
  const navigate = useNavigate()
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
