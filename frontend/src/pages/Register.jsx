import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { register } from '../services/api'

function Register() {
  const navigate = useNavigate()
  const [form, setForm] = useState({
    first_name: '',
    last_name: '',
    email: '',
    password: '',
    phone: '',
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const onChange = (e) => {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }))
  }

  const onSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setSuccess('')

    const phone = form.phone.trim()
    if (!phone) {
      setError('Numărul de telefon este obligatoriu.')
      return
    }
    if (phone.length < 8) {
      setError('Numărul de telefon trebuie să aibă cel puțin 8 caractere.')
      return
    }
    if (form.password.length < 8) {
      setError('Parola trebuie să aibă cel puțin 8 caractere.')
      return
    }
    setLoading(true)
    try {
      await register({ ...form, university_name: '' })
      setSuccess('Cont creat cu succes. Te redirectionez catre login...')
      setTimeout(() => navigate('/login'), 1200)
    } catch (err) {
      setError(err?.message || 'Nu am putut crea contul')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-100 px-4 transition-colors duration-300 dark:bg-slate-950">
      <div className="bg-white p-8 rounded-lg shadow-md w-full max-w-lg transition-colors duration-300 dark:bg-slate-900 dark:border dark:border-slate-800">
        <h1 className="text-3xl font-bold mb-2 text-center text-slate-900 dark:text-slate-50">Creează cont</h1>
        <p className="text-sm text-center text-slate-500 dark:text-slate-400 mb-2">
          Completează datele de bază. Poza de profil și documentele se adaugă la primul pas de verificare.
        </p>

        {error && <div className="bg-red-100 text-red-700 p-3 rounded mb-4">{error}</div>}
        {success && <div className="bg-green-100 text-green-700 p-3 rounded mb-4">{success}</div>}

        <form onSubmit={onSubmit} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-gray-700 mb-1 dark:text-slate-200">Prenume</label>
              <input
                name="first_name"
                type="text"
                value={form.first_name}
                onChange={onChange}
                className="w-full px-3 py-2 border rounded-lg dark:bg-slate-950 dark:text-slate-50 dark:border-slate-700"
                required
              />
            </div>
            <div>
              <label className="block text-gray-700 mb-1 dark:text-slate-200">Nume</label>
              <input
                name="last_name"
                type="text"
                value={form.last_name}
                onChange={onChange}
                className="w-full px-3 py-2 border rounded-lg dark:bg-slate-950 dark:text-slate-50 dark:border-slate-700"
                required
              />
            </div>
          </div>

          <div>
            <label className="block text-gray-700 mb-1 dark:text-slate-200">Email</label>
            <input
              name="email"
              type="email"
              value={form.email}
              onChange={onChange}
              className="w-full px-3 py-2 border rounded-lg dark:bg-slate-950 dark:text-slate-50 dark:border-slate-700"
              required
            />
          </div>

          <div>
            <label className="block text-gray-700 mb-1 dark:text-slate-200">Telefon</label>
            <input
              name="phone"
              type="tel"
              placeholder="+407xxxxxxxx"
              value={form.phone}
              onChange={onChange}
              className="w-full px-3 py-2 border rounded-lg dark:bg-slate-950 dark:text-slate-50 dark:border-slate-700"
              required
            />
          </div>

          <div>
            <label className="block text-gray-700 mb-1 dark:text-slate-200">Parolă</label>
            <input
              name="password"
              type="password"
              value={form.password}
              onChange={onChange}
              className="w-full px-3 py-2 border rounded-lg dark:bg-slate-950 dark:text-slate-50 dark:border-slate-700"
              minLength={6}
              required
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-600 text-white py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 dark:bg-cyan-500 dark:hover:bg-cyan-400 dark:text-slate-950 mt-2"
          >
            {loading ? 'Se creează...' : 'Creează cont'}
          </button>
        </form>

        <div className="mt-4 text-sm text-center">
          <span className="text-gray-600 dark:text-slate-300">Ai deja cont? </span>
          <Link to="/login" className="text-blue-600 hover:underline">
            Intră în cont
          </Link>
        </div>
      </div>
    </div>
  )
}

export default Register
