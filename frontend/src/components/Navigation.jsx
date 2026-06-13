import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { getUserProfilePhotoBlobUrl } from '../services/api'

function Navigation({ user, onLogout }) {
  const navigate = useNavigate()
  const [unread, setUnread] = useState(0)
  const [profilePhotoUrl, setProfilePhotoUrl] = useState(null)
  const [mobileOpen, setMobileOpen] = useState(false)

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
        } else if (r.status === 401) {
          clearInterval(id)
        }
      } catch (_) {}
    }
    fetchUnread()
    const id = setInterval(fetchUnread, 60000)
    const onFocus = () => fetchUnread()
    const onChange = () => fetchUnread()
    window.addEventListener('focus', onFocus)
    window.addEventListener('notifications:changed', onChange)
    return () => {
      clearInterval(id)
      window.removeEventListener('focus', onFocus)
      window.removeEventListener('notifications:changed', onChange)
    }
  }, [user])

  useEffect(() => {
    if (!user?.user_id || !user?.has_profile_photo) {
      setProfilePhotoUrl(null)
      return
    }
    let active = true
    getUserProfilePhotoBlobUrl(user.user_id)
      .then(url => { if (active) setProfilePhotoUrl(url) })
      .catch(() => { if (active) setProfilePhotoUrl(null) })
    return () => { active = false }
  }, [user?.user_id, user?.has_profile_photo])

  const close = () => setMobileOpen(false)

  const NavLinks = ({ mobile }) => (
    <>
      {user?.role === 'passenger' && (
        <>
          <Link to="/dashboard" className="hover:text-blue-200" onClick={close}>Dashboard</Link>
          <Link to="/documents" className="hover:text-blue-200" onClick={close}>Documente</Link>
          <Link to="/notifications" className="hover:text-blue-200 relative" onClick={close}>
            Notificari
            {unread > 0 && (
              <span className="absolute -top-2 -right-3 bg-red-500 text-white text-xs font-bold w-4 h-4 rounded-full flex items-center justify-center leading-none">
                {unread > 9 ? '9+' : unread}
              </span>
            )}
          </Link>
          <Link to="/present" className="hover:text-blue-200" onClick={close}>Card Digital</Link>
          <Link to="/tickets" className="hover:text-blue-200" onClick={close}>Bilete</Link>
          <Link to="/subscriptions" className="hover:text-blue-200" onClick={close}>Abonamente</Link>
          <Link to="/map" className="hover:text-blue-200" onClick={close}>Hartă</Link>
          <Link to="/travel-history" className="hover:text-blue-200" onClick={close}>Istoric calatorii</Link>
        </>
      )}

      {user?.role === 'train_verifier' && (
        <>
          <Link to="/verify" className="hover:text-blue-200" onClick={close}>Verificare card digital</Link>
          <Link to="/map" className="hover:text-blue-200" onClick={close}>Hartă</Link>
          <Link to="/validate-ticket" className="hover:text-blue-200" onClick={close}>Validare bilet</Link>
          <Link to="/travel-history" className="hover:text-blue-200" onClick={close}>Istoric</Link>
        </>
      )}

      {user?.role === 'university_agent' && (
        <>
          <Link to="/agent" className="hover:text-blue-200" onClick={close}>Dashboard Agent</Link>
          <Link to="/map" className="hover:text-blue-200" onClick={close}>Hartă</Link>
        </>
      )}
    </>
  )

  const ProfileBlock = ({ mobile }) => (
    <div className={mobile
      ? 'flex items-center gap-4 flex-wrap pt-3 mt-1 border-t border-blue-500/40 dark:border-slate-700'
      : 'flex gap-3 items-center ml-4 pl-4 border-l border-blue-400 dark:border-slate-700'
    }>
      <Link to="/settings" className="hover:text-blue-200 font-medium" onClick={close}>Settings</Link>
      <Link to="/profile" className="flex items-center gap-2 hover:opacity-80 transition" onClick={close}>
        <div className="w-8 h-8 rounded-full overflow-hidden border-2 border-white/40 bg-blue-400 dark:bg-slate-700 flex items-center justify-center shrink-0">
          {profilePhotoUrl ? (
            <img src={profilePhotoUrl} alt="profil" className="w-full h-full object-cover" />
          ) : (
            <span className="text-sm font-bold text-white leading-none">
              {(user?.first_name?.[0] || '?').toUpperCase()}
            </span>
          )}
        </div>
        <span className="font-medium">{user?.first_name || 'Profil'}</span>
      </Link>
      <button
        onClick={handleLogout}
        className="bg-red-600 hover:bg-red-700 px-3 py-1 rounded-lg font-semibold transition"
      >
        Logout
      </button>
    </div>
  )

  return (
    <nav className="bg-blue-600 text-white shadow-lg dark:bg-slate-900 dark:text-slate-100 border-b border-blue-500/30 dark:border-slate-800">
      <div className="container mx-auto px-4 py-3 md:py-4">
        {/* Top bar: logo + hamburger (mobile) or full nav (desktop) */}
        <div className="flex justify-between items-center">
          <Link to="/dashboard" className="text-xl md:text-2xl font-bold tracking-tight">
            Railway Identity
          </Link>

          {/* Hamburger — mobile only */}
          <button
            className="md:hidden p-2 rounded-lg hover:bg-blue-500/60 dark:hover:bg-slate-700 transition"
            onClick={() => setMobileOpen(o => !o)}
            aria-label="Menu"
          >
            {mobileOpen ? (
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            ) : (
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            )}
          </button>

          {/* Desktop nav */}
          <div className="hidden md:flex flex-wrap gap-4 items-center justify-end">
            <NavLinks />
            <ProfileBlock mobile={false} />
          </div>
        </div>

        {/* Mobile dropdown */}
        {mobileOpen && (
          <div className="md:hidden mt-3 pt-3 pb-1 border-t border-blue-500/40 dark:border-slate-700 flex flex-col gap-3 text-base">
            <NavLinks mobile />
            <ProfileBlock mobile />
          </div>
        )}
      </div>
    </nav>
  )
}

export default Navigation
