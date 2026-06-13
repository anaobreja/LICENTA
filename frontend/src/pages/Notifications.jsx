import { useEffect, useState } from 'react'
import { getMyNotifications, markNotificationRead } from '../services/api'

function Notifications() {
  const [notifications, setNotifications] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const loadNotifications = async () => {
    try {
      const data = await getMyNotifications()
      setNotifications(data || [])
    } catch (err) {
      setError(err.message || 'Nu am putut incarca notificarile')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadNotifications()
  }, [])

  const formatDateTime = (value) => {
    if (!value) {
      return '-'
    }
    const date = new Date(value)
    return date.toLocaleString('ro-RO')
  }

  const handleMarkRead = async (id) => {
    setError('')
    try {
      await markNotificationRead(id)
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, is_read: 1 } : n))
      )
      // Anunta restul aplicatiei (in special badge-ul din navbar) ca s-a
      // schimbat starea notificarilor, ca sa actualizeze contorul imediat,
      // fara sa astepte intervalul de 60s sau focus pe fereastra.
      window.dispatchEvent(new Event('notifications:changed'))
    } catch (err) {
      setError(err.message || 'Nu am putut marca notificarea')
    }
  }

  return (
    <div className="container mx-auto px-4 py-8 max-w-4xl">
      <h1 className="text-3xl font-bold mb-2 text-slate-900 dark:text-slate-50">Notificari</h1>
      <p className="text-slate-600 dark:text-slate-300 mb-6">Aici primesti notificari atunci cand cererea ta este aprobata sau respinsa.</p>

      {error && <div className="bg-red-50 border border-red-200 text-red-700 p-3 rounded-xl mb-4 dark:bg-red-950/40 dark:border-red-800 dark:text-red-200">{error}</div>}

      <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm dark:bg-slate-900 dark:border-slate-700">
        <h2 className="text-xl font-bold mb-3 text-slate-900 dark:text-slate-100">Lista notificari</h2>

        {loading ? (
          <p className="text-slate-600 dark:text-slate-300">Se incarca...</p>
        ) : notifications.length === 0 ? (
          <p className="text-slate-600 dark:text-slate-300">Nu ai notificari in aceasta categorie.</p>
        ) : (
          <div className="space-y-3">
            {notifications.map((item) => (
              <div
                key={item.id}
                className={`border rounded-xl p-4 ${
                  item.is_read ? 'border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800' : 'border-cyan-300 bg-cyan-50/40 dark:border-cyan-700 dark:bg-cyan-900/20'
                }`}
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="font-semibold text-slate-900 dark:text-slate-100">{item.title}</div>
                  {!item.is_read ? (
                    <button
                      type="button"
                      onClick={() => handleMarkRead(item.id)}
                      className="text-sm font-semibold text-cyan-800 dark:text-cyan-400 hover:underline"
                    >
                      Marcheaza citita
                    </button>
                  ) : (
                    <span className="text-xs text-slate-500 dark:text-slate-400">Citita</span>
                  )}
                </div>
                <p className="text-sm text-slate-700 dark:text-slate-200 mt-2">{item.message}</p>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-2">{formatDateTime(item.created_at)}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export default Notifications
