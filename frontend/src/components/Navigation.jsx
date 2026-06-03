import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

function Navigation({ user, onLogout }) {
  const navigate = useNavigate()
  const [unread, setUnread] = useState(0)

  const handleLogout = () => {
    onLogout()
    navigate('/login')
  }

  useEffect(() => {
    if (!user || user.role !== 'passenger') return
    const fetchUnread = async () => {
      try {
        const token = localStorage.getItem('access_token')
        const r = await fetch('/api/notifications/me', { headers: { Authorization: `Bearer ${token}` } })
        if (r.ok) {
          const data = await r.json()
          setUnread(data.filter(n => !n.is_read).length)
        }
      } catch (_) {}
    }
    fetchUnread()
    const id = setInterval(fetchUnread, 60000)
    const onFocus = () => fetchUnread()
    window.addEventListener('focus', onFocus)
    return () => { clearInterval(id); window.removeEventListener('focus', onFocus) }
  }, [user])

  return (
    <nav className="bg-blue-600 text-white shadow-lg dark:bg-slate-900 dark:text-slate-100 border-b border-blue-500/30 dark:border-slate-800">
      <div className="container mx-auto px-4 py-4 flex justify-between items-center gap-4">
        <div>
          <Link to="/dashboard" className="text-2xl font-bold tracking-tight">
            Railway Identity
          </Link>
        </div>

        <div className="flex flex-wrap gap-4 items-center justify-end">
          {user?.role === 'passenger' && (
            <>
              <Link to="/dashboard" className="hover:text-blue-200">Dashboard</Link>
              <Link to="/documents" className="hover:text-blue-200">Documente</Link>
              <Link to="/notifications" className="hover:text-blue-200 relative">
                Notificari
                {unread > 0 && (
                  <span className="absolute -top-2 -right-3 bg-red-500 text-white text-xs font-bold w-4 h-4 rounded-full flex items-center justify-center leading-none">
                    {unread > 9 ? '9+' : unread}
                  </span>
                )}
              </Link>
              <Link to="/credentials" className="hover:text-blue-200">Credentiale</Link>
              <Link to="/present" className="hover:text-blue-200">Card Digital</Link>
            </>
          )}

          {user?.role === 'train_verifier' && (
            <Link to="/verify" className="hover:text-blue-200">Verificare card digital</Link>
          )}

          {user?.role === 'issuer_verifier' && (
            <Link to="/issuer" className="hover:text-blue-200">Issuer</Link>
          )}

          {user?.role === 'university_agent' && (
            <Link to="/agent" className="hover:text-blue-200">Dashboard Agent</Link>
          )}

          <div className="flex gap-3 items-center ml-2 pl-0 md:ml-4 md:pl-4 md:border-l border-blue-400 dark:border-slate-700">
            <Link to="/settings" className="hover:text-blue-200 font-medium">
              Settings
            </Link>
            <Link to="/profile" className="hover:text-blue-200 font-medium">
              {user?.first_name || 'Profile'}
            </Link>
            <button
              onClick={handleLogout}
              className="bg-red-600 hover:bg-red-700 px-3 py-1 rounded-lg font-semibold transition"
            >
              Logout
            </button>
          </div>
        </div>
      </div>
    </nav>
  )
}

export default Navigation

