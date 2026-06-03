import { createContext, useCallback, useContext, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

const ToastCtx = createContext(null)

const ICONS = { success: '✔', error: '✕', info: 'ℹ', warning: '⚠' }
const COLORS = {
  success: 'bg-emerald-600',
  error:   'bg-red-600',
  info:    'bg-blue-600',
  warning: 'bg-amber-500',
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const idRef = useRef(0)

  const toast = useCallback((message, type = 'info', duration = 3500) => {
    const id = ++idRef.current
    const safeMsg = typeof message === 'string' ? message : (message?.message ? String(message.message) : JSON.stringify(message))
    setToasts(p => [...p, { id, message: safeMsg, type }])
    setTimeout(() => setToasts(p => p.filter(t => t.id !== id)), duration)
  }, [])

  return (
    <ToastCtx.Provider value={toast}>
      {children}
      {createPortal(
        <div className="fixed bottom-5 right-5 z-[9999] flex flex-col gap-2 pointer-events-none">
          {toasts.map(t => (
            <div
              key={t.id}
              className={`flex items-center gap-3 ${COLORS[t.type]} text-white text-sm font-semibold px-4 py-3 rounded-xl shadow-xl pointer-events-auto animate-slide-in`}
            >
              <span>{ICONS[t.type]}</span>
              <span>{t.message}</span>
            </div>
          ))}
        </div>,
        document.body
      )}
    </ToastCtx.Provider>
  )
}

export const useToast = () => useContext(ToastCtx)
