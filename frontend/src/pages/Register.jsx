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
    setLoading(true)

    try {
      await register(form)
      setSuccess('Cont creat cu succes. Te redirectionez catre login...')
      setTimeout(() => navigate('/login'), 1200)
    } catch (err) {
      const backendMessage = err?.message || 'Nu am putut crea contul'
      setError(backendMessage)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-100 px-4 transition-colors duration-300 dark:bg-slate-950">
      <div className="bg-white p-8 rounded-lg shadow-md w-full max-w-md transition-colors duration-300 dark:bg-slate-900 dark:border dark:border-slate-800">
        <h1 className="text-3xl font-bold mb-6 text-center text-slate-900 dark:text-slate-50">Creeaza Cont</h1>

        {error && <div className="bg-red-100 text-red-700 p-3 rounded mb-4">{error}</div>}
        {success && <div className="bg-green-100 text-green-700 p-3 rounded mb-4">{success}</div>}

        <form onSubmit={onSubmit}>
          <div className="mb-3">
            <label className="block text-gray-700 mb-1 dark:text-slate-200">Prenume</label>
            <input
              name="first_name"
              type="text"
              value={form.first_name}
              onChange={onChange}
              className="w-full px-3 py-2 border rounded-lg bg-white text-slate-900 dark:bg-slate-950 dark:text-slate-50 dark:border-slate-700"
              required
            />
          </div>

          <div className="mb-3">
            <label className="block text-gray-700 mb-1 dark:text-slate-200">Nume</label>
            <input
              name="last_name"
              type="text"
              value={form.last_name}
              onChange={onChange}
              className="w-full px-3 py-2 border rounded-lg bg-white text-slate-900 dark:bg-slate-950 dark:text-slate-50 dark:border-slate-700"
              required
            />
          </div>

          <div className="mb-3">
            <label className="block text-gray-700 mb-1 dark:text-slate-200">Email</label>
            <input
              name="email"
              type="email"
              value={form.email}
              onChange={onChange}
              className="w-full px-3 py-2 border rounded-lg bg-white text-slate-900 dark:bg-slate-950 dark:text-slate-50 dark:border-slate-700"
              required
            />
          </div>

          <div className="mb-5">
            <label className="block text-gray-700 mb-1 dark:text-slate-200">Parola</label>
            <input
              name="password"
              type="password"
              value={form.password}
              onChange={onChange}
              className="w-full px-3 py-2 border rounded-lg bg-white text-slate-900 dark:bg-slate-950 dark:text-slate-50 dark:border-slate-700"
              minLength={6}
              required
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-600 text-white py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 dark:bg-cyan-500 dark:hover:bg-cyan-400 dark:text-slate-950"
          >
            {loading ? 'Se creeaza...' : 'Creeaza cont'}
          </button>
        </form>

        <div className="mt-4 text-sm text-center">
          <span className="text-gray-600 dark:text-slate-300">Ai deja cont? </span>
          <Link to="/login" className="text-blue-600 hover:underline">
            Intra in cont
          </Link>
        </div>
      </div>
    </div>
  )
}

export default Register
