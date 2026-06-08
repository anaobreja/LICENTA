/**
 * API Service - Handles all backend communication
 */

// Compatibilitate cu medii non-Vite (Node test runners) — in productie
// `import.meta.env` este injectat de Vite la build time.
const API_BASE_URL = (import.meta.env && import.meta.env.VITE_API_URL) || '/api'

// Helper function to get authorization header
const getAuthHeader = () => {
  const token = localStorage.getItem('access_token')
  if (!token) {
    return {}
  }
  return {
    'Authorization': `Bearer ${token}`
  }
}

// Generic fetch wrapper
async function apiCall(endpoint, options = {}) {
  const url = `${API_BASE_URL}${endpoint}`
  const headers = {
    'Content-Type': 'application/json',
    ...getAuthHeader(),
    ...options.headers
  }

  try {
    const response = await fetch(url, {
      ...options,
      headers
    })

    if (!response.ok) {
      let errorMessage = `HTTP ${response.status}`
      try {
        const errorData = await response.json()
        if (errorData?.detail) {
          errorMessage = errorData.detail
        }
      } catch (_) {
        // Ignore JSON parse errors and keep generic message.
      }
      throw new Error(errorMessage)
    }

    const data = await response.json()
    return data
  } catch (error) {
    const isNetworkFailure = error instanceof TypeError && error.message === 'Failed to fetch'
    const enhancedError = isNetworkFailure
      ? new Error(
          `Failed to fetch ${url}. Check that the backend is running on http://localhost:8000 and that the Vite proxy target is correct.`
        )
      : error

    console.error('API Error:', enhancedError)
    throw enhancedError
  }
}

// Auth API calls
export const checkAuth = async () => {
  const token = localStorage.getItem('access_token')
  if (!token) {
    return null
  }

  try {
    return await apiCall('/users/me')
  } catch (_) {
    return null
  }
}

export const login = (email, password, totpCode) =>
  apiCall('/auth/login', {
    method: 'POST',
    body: JSON.stringify({
      email,
      password,
      ...(totpCode ? { totp_code: totpCode } : {}),
    }),
  })

export const register = async ({
  first_name,
  last_name,
  email,
  password,
  phone,
  university_name,
}) => {
  const url = `${API_BASE_URL}/auth/register`
  const formData = new FormData()
  formData.append('first_name', first_name)
  formData.append('last_name', last_name)
  formData.append('email', email)
  formData.append('password', password)
  formData.append('phone', phone)
  formData.append('university_name', university_name)

  const response = await fetch(url, { method: 'POST', body: formData })
  if (!response.ok) {
    let errorMessage = `Eroare ${response.status}`
    try {
      const errorData = await response.json()
      if (errorData?.detail) {
        if (typeof errorData.detail === 'string') {
          errorMessage = errorData.detail
        } else if (Array.isArray(errorData.detail)) {
          // Pydantic 422 — formatez fiecare eroare ca "Camp: mesaj"
          const fieldLabels = {
            email: 'Email', password: 'Parola', phone: 'Telefon',
            first_name: 'Prenume', last_name: 'Nume',
            university_name: 'Universitate',
          }
          errorMessage = errorData.detail.map(err => {
            const field = err.loc?.[err.loc.length - 1] || ''
            const label = fieldLabels[field] || field
            const msg = err.msg || 'Valoare invalida'
            // Traducere mesaje uzuale
            const friendly = msg
              .replace(/String should have at least (\d+) characters/, 'minim $1 caractere')
              .replace(/String should have at most (\d+) characters/, 'maxim $1 caractere')
              .replace(/value is not a valid email address.*/, 'email invalid')
              .replace(/field required/i, 'camp obligatoriu')
            return label ? `${label}: ${friendly}` : friendly
          }).join('. ')
        } else {
          errorMessage = JSON.stringify(errorData.detail)
        }
      }
    } catch (_) { /* ignore */ }
    throw new Error(errorMessage)
  }
  return response.json()
}

export const setupMFA = () =>
  apiCall('/auth/mfa/setup', { method: 'POST' })

export const verifyMFA = (code) =>
  apiCall('/auth/mfa/verify', {
    method: 'POST',
    body: JSON.stringify({ code }),
  })

export const disableMFA = (password) =>
  apiCall('/auth/mfa/disable', {
    method: 'POST',
    body: JSON.stringify({ password }),
  })

export const markNotificationRead = (notificationId) =>
  apiCall(`/notifications/me/${notificationId}/read`, {
    method: 'PATCH',
  })

// Identity workflow APIs
export const getMyDocuments = () => apiCall('/documents/me')

export const extractIdData = async (photo) => {
  const url = `${API_BASE_URL}/documents/extract-id`
  const formData = new FormData()
  formData.append('photo', photo)
  const response = await fetch(url, {
    method: 'POST',
    headers: { ...getAuthHeader() },
    body: formData,
  })
  if (!response.ok) {
    const err = await response.json().catch(() => ({}))
    throw new Error(err.detail || `HTTP ${response.status}`)
  }
  return response.json()
}

export const createDocument = (payload) =>
  apiCall('/documents', {
    method: 'POST',
    body: JSON.stringify(payload)
  })

export const createDocumentWithPhoto = async ({ document_type, document_number_masked, photo }) => {
  const url = `${API_BASE_URL}/documents/upload`
  const formData = new FormData()
  formData.append('document_type', document_type)
  formData.append('document_number_masked', document_number_masked)
  if (photo) {
    formData.append('photo', photo)
  }

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      ...getAuthHeader()
    },
    body: formData
  })

  if (!response.ok) {
    let errorMessage = `HTTP ${response.status}`
    try {
      const errorData = await response.json()
      if (errorData?.detail) {
        errorMessage = errorData.detail
      }
    } catch (_) {
      // Keep generic message if backend does not return JSON.
    }
    throw new Error(errorMessage)
  }

  return response.json()
}

export const submitIdentityValidationRequest = async ({
  legitimation_type,
  legitimation_number_masked,
  legitimation_photo_front,
  legitimation_photo_verso,
  profile_photo,
  university_name = '',
  year_of_study = 0,
  ci_number = '',
  ci_name = '',
  ci_date_of_birth = '',
  ci_sex = '',
  ci_address = '',
}) => {
  const url = `${API_BASE_URL}/documents/validation-request`
  const formData = new FormData()
  formData.append('legitimation_type', legitimation_type)
  formData.append('legitimation_number_masked', legitimation_number_masked)
  if (legitimation_photo_front) {
    formData.append('legitimation_photo_front', legitimation_photo_front)
  }
  if (legitimation_photo_verso) {
    formData.append('legitimation_photo_verso', legitimation_photo_verso)
  }
  if (profile_photo) {
    formData.append('profile_photo', profile_photo)
  }
  formData.append('university_name', university_name)
  formData.append('year_of_study', String(isNaN(year_of_study) || !year_of_study ? 0 : year_of_study))
  formData.append('ci_number', ci_number)
  formData.append('ci_name', ci_name)
  formData.append('ci_date_of_birth', ci_date_of_birth)
  formData.append('ci_sex', ci_sex)
  formData.append('ci_address', ci_address || '')

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      ...getAuthHeader()
    },
    body: formData
  })

  if (!response.ok) {
    let errorMessage = `HTTP ${response.status}`
    try {
      const errorData = await response.json()
      if (errorData?.detail) {
        errorMessage = errorData.detail
      }
    } catch (_) {
      // Keep generic message if backend does not return JSON.
    }
    throw new Error(errorMessage)
  }

  return response.json()
}

export const getIssuerPendingDocuments = (yearOfStudy = null) => {
  const qs = yearOfStudy ? `?year_of_study=${yearOfStudy}` : ''
  return apiCall(`/issuer/documents/pending${qs}`)
}

export const approveIssuerDocument = (documentId, notes = '') =>
  apiCall(`/issuer/documents/${documentId}/approve`, {
    method: 'POST',
    body: JSON.stringify({ notes })
  })

export const rejectIssuerDocument = (documentId, notes = '') =>
  apiCall(`/issuer/documents/${documentId}/reject`, {
    method: 'POST',
    body: JSON.stringify({ notes })
  })

export const getDocumentPhotoBlobUrl = async (documentId, side = 'front') => {
  const url = `${API_BASE_URL}/documents/${documentId}/photo?side=${encodeURIComponent(side)}`
  const response = await fetch(url, {
    headers: {
      ...getAuthHeader()
    }
  })

  if (!response.ok) {
    let errorMessage = `HTTP ${response.status}`
    try {
      const errorData = await response.json()
      if (errorData?.detail) {
        errorMessage = errorData.detail
      }
    } catch (_) {
      // Keep generic message if backend does not return JSON.
    }
    throw new Error(errorMessage)
  }

  const blob = await response.blob()
  return URL.createObjectURL(blob)
}

export const getMyCredentials = () => apiCall('/credentials/me')

export const getMyNotifications = () => apiCall('/notifications/me')

export const getMyCard = () => apiCall('/card/me')

export const generatePresentation = (payload = { ttl_seconds: 120 }) =>
  apiCall('/card/present', {
    method: 'POST',
    body: JSON.stringify(payload)
  })

export const verifyPresentation = (payload) =>
  apiCall('/card/verify', {
    method: 'POST',
    body: JSON.stringify(payload)
  })

// =============================================================================
// Verificare OFFLINE a tokenurilor de prezentare (semnatura Ed25519)
// =============================================================================
//
// Algoritmul Ed25519 are urmatoarele caracteristici critice pentru cazul nostru:
//   - cheia publica = 32 bytes (importabila ca 'raw' in Web Crypto API)
//   - semnatura = 64 bytes
//   - verificarea = O(1), <1ms pe hardware modern
//
// Cheia publica e descarcata o singura data de la /verification-key si
// pastrata in localStorage cu TTL 24h. Daca server-ul roteste cheia (kid
// diferit), refacem fetch-ul si invalidam cache-ul.
//
// IMPORTANT: nu cache-uim cheia privata; aceasta sta DOAR pe server.
// =============================================================================

const VERIFICATION_KEY_CACHE_KEY = 'rdc_verification_key_v1'
const VERIFICATION_KEY_TTL_MS = 24 * 60 * 60 * 1000  // 24h

/**
 * Descarca cheia publica Ed25519 de la /verification-key.
 * Cache-uieste in localStorage. Forteaza refresh daca:
 *   - cache lipsa
 *   - TTL expirat
 *   - param `force=true`
 *
 * Returneaza { algorithm, kid, pem, raw_base64, fetched_at }.
 */
export const getVerificationKey = async ({ force = false } = {}) => {
  if (!force) {
    try {
      const cached = JSON.parse(localStorage.getItem(VERIFICATION_KEY_CACHE_KEY))
      if (cached?.fetched_at && Date.now() - cached.fetched_at < VERIFICATION_KEY_TTL_MS) {
        return cached
      }
    } catch (_) {
      // cache corupt - reimprospatam
    }
  }
  const data = await apiCall('/verification-key')
  const enriched = { ...data, fetched_at: Date.now() }
  try {
    localStorage.setItem(VERIFICATION_KEY_CACHE_KEY, JSON.stringify(enriched))
  } catch (_) {
    // localStorage plin / dezactivat - continuam fara cache
  }
  return enriched
}

/**
 * Sterge cache-ul cheii publice. Util la logout sau cand utilizatorul
 * raporteaza "verificarea nu mai merge".
 */
export const clearVerificationKeyCache = () => {
  try {
    localStorage.removeItem(VERIFICATION_KEY_CACHE_KEY)
  } catch (_) { /* ignore */ }
}

// Helpers base64url (compatibili cu signing.py de pe server)
const b64urlToBytes = (s) => {
  const padded = s + '='.repeat((-s.length) & 3)
  const std = padded.replace(/-/g, '+').replace(/_/g, '/')
  const bin = atob(std)
  const bytes = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
  return bytes
}

const b64stdToBytes = (s) => {
  const bin = atob(s)
  const bytes = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
  return bytes
}

/**
 * Verifica OFFLINE un token semnat de server.
 * Format token: "<b64url_payload>.<b64url_signature>"
 *
 * Returneaza un obiect:
 *   { valid: true, payload: {...} }  daca semnatura e valida si exp > now
 *   { valid: false, reason: '...' }  altfel (motive lizibile pentru UI)
 *
 * NU arunca exceptii pentru erori de validare - controlorul vrea un raspuns
 * binar clar verde/rosu, nu un stack trace.
 */
export const verifyOfflineToken = async (token) => {
  if (typeof token !== 'string' || token.indexOf('.') === -1) {
    return { valid: false, reason: 'Format token invalid (lipseste separatorul ".")' }
  }
  const parts = token.split('.')
  if (parts.length !== 2) {
    return { valid: false, reason: 'Format token invalid (asteptat 2 segmente)' }
  }

  let canonical, signature
  try {
    canonical = b64urlToBytes(parts[0])
    signature = b64urlToBytes(parts[1])
  } catch (e) {
    return { valid: false, reason: 'Token corupt (base64 invalid)' }
  }
  if (signature.length !== 64) {
    return { valid: false, reason: `Semnatura asteptata 64 bytes, primita ${signature.length}` }
  }

  let pubKey
  try {
    const keyData = await getVerificationKey()
    const rawKey = b64stdToBytes(keyData.raw_base64)
    if (rawKey.length !== 32) {
      return { valid: false, reason: `Cheie publica invalida: ${rawKey.length} bytes` }
    }
    if (!window.crypto?.subtle?.importKey) {
      return { valid: false, reason: 'Web Crypto API indisponibil in acest browser' }
    }
    pubKey = await window.crypto.subtle.importKey(
      'raw',
      rawKey,
      { name: 'Ed25519' },
      false,
      ['verify']
    )
  } catch (e) {
    return { valid: false, reason: `Eroare la incarcarea cheii publice: ${e.message || e}` }
  }

  let signatureValid = false
  try {
    signatureValid = await window.crypto.subtle.verify(
      { name: 'Ed25519' },
      pubKey,
      signature,
      canonical
    )
  } catch (e) {
    return { valid: false, reason: `Verificare esuata: ${e.message || e}` }
  }
  if (!signatureValid) {
    return { valid: false, reason: 'Semnatura invalida - tokenul a fost modificat sau emis de alta cheie' }
  }

  let payload
  try {
    payload = JSON.parse(new TextDecoder().decode(canonical))
  } catch (e) {
    return { valid: false, reason: 'Payload JSON invalid' }
  }

  if (!payload.exp) {
    return { valid: false, reason: 'Payload lipseste campul "exp"' }
  }
  const expRaw = String(payload.exp)
  const hasTimezone = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(expRaw)
  const expMs = new Date(hasTimezone ? expRaw : expRaw + 'Z').getTime()
  if (!Number.isFinite(expMs)) {
    return { valid: false, reason: `Camp "exp" nu este timestamp valid: ${expRaw}` }
  }
  if (Date.now() > expMs) {
    return {
      valid: false,
      reason: `Token expirat la ${new Date(expMs).toLocaleString('ro-RO')}`,
      payload,
    }
  }

  return { valid: true, payload }
}

// User
export const getUserProfile = () =>
  apiCall('/users/me')

export const getUserProfilePhotoBlobUrl = async (userId) => {
  const url = `${API_BASE_URL}/users/${userId}/profile-photo`
  const response = await fetch(url, { headers: { ...getAuthHeader() } })
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`)
  }
  const blob = await response.blob()
  return URL.createObjectURL(blob)
}

export const updateProfile = (userData) =>
  apiCall('/users/me', {
    method: 'PUT',
    body: JSON.stringify(userData),
  })

export const updateProfilePhoto = async (file) => {
  const formData = new FormData()
  formData.append('profile_photo', file)
  const url = `${API_BASE_URL}/users/me/profile-photo`
  const response = await fetch(url, {
    method: 'PUT',
    headers: { ...getAuthHeader() },
    body: formData,
  })
  if (!response.ok) {
    const err = await response.json().catch(() => ({}))
    throw new Error(err.detail || `HTTP ${response.status}`)
  }
  return response.json()
}

export const changePassword = (currentPassword, newPassword) =>
  apiCall('/users/me/password', {
    method: 'PUT',
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
    }),
  })

export const exportUserData = () =>
  apiCall('/users/me/export')

export const deleteAccount = () =>
  apiCall('/users/me', { method: 'DELETE' })



// ============================================================================
// Tickets / Travel
// ============================================================================
export const getTicketsCatalog = () => apiCall('/tickets/catalog')

export const buyTicket = ({
  train_id,
  departure_station_id,
  arrival_station_id,
  travel_date,
  ticket_type = 'single',
}) =>
  apiCall('/tickets/buy', {
    method: 'POST',
    body: JSON.stringify({
      train_id,
      departure_station_id,
      arrival_station_id,
      travel_date,
      ticket_type,
    }),
  })

export const getMyTickets = () => apiCall('/tickets/my')

export const validateTicketToken = (token, deviceId = null, locationName = null) =>
  apiCall('/tickets/validate', {
    method: 'POST',
    body: JSON.stringify({
      token,
      ...(deviceId ? { device_id: deviceId } : {}),
      ...(locationName ? { location_name: locationName } : {}),
    }),
  })

export const getValidationsHistory = (limit = 50) =>
  apiCall(`/validations/history?limit=${limit}`)

export const quoteTicket = ({
  train_id,
  departure_station_id,
  arrival_station_id,
  travel_date,
  ticket_type = 'single',
}) =>
  apiCall('/tickets/quote', {
    method: 'POST',
    body: JSON.stringify({
      train_id,
      departure_station_id,
      arrival_station_id,
      travel_date,
      ticket_type,
    }),
  })

export const searchStations = (q = '', limit = 15) =>
  apiCall(`/stations/search?q=${encodeURIComponent(q)}&limit=${limit}`)

export const searchTrains = (fromStationId, toStationId, travelDate = null) => {
  const qs = new URLSearchParams({
    from_station_id: String(fromStationId),
    to_station_id: String(toStationId),
  })
  if (travelDate) qs.set('travel_date', travelDate)
  return apiCall(`/trains/search?${qs.toString()}`)
}

// Map endpoints
export const getMapStations = ({ only_university = false, operator_id = null } = {}) => {
  const qs = new URLSearchParams()
  if (only_university) qs.set('only_university', 'true')
  if (operator_id) qs.set('operator_id', String(operator_id))
  const q = qs.toString()
  return apiCall(`/map/stations${q ? '?' + q : ''}`)
}

export const getMapConnections = ({ min_trains = 1, only_university = true, operator_id = null } = {}) => {
  const qs = new URLSearchParams({
    min_trains: String(min_trains),
    only_university: String(only_university),
  })
  if (operator_id) qs.set('operator_id', String(operator_id))
  return apiCall(`/map/connections?${qs.toString()}`)
}

export const getMapOperators = () => apiCall('/map/operators')

export const simulateTrainPosition = (trainId) =>
  apiCall(`/map/train-simulate/${trainId}`)


// =============================================================================
// Seats & Ticket Lifecycle (Faza 5)
// =============================================================================

/**
 * Layout-ul complet al unui tren + status fiecarui loc pentru o data calatorie.
 * Status: 'free' | 'sold' | 'held' | 'mine_held' | 'mine_sold'
 */
export const getTrainSeats = (trainId, travelDate) =>
  apiCall(`/trains/${trainId}/seats?travel_date=${encodeURIComponent(travelDate)}`)

/**
 * Tine un loc rezervat pentru 5 minute. Idempotent (refresh la timer).
 */
export const holdSeat = ({ train_id, seat_id, travel_date }) =>
  apiCall('/seats/hold', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ train_id, seat_id, travel_date }),
  })

/**
 * Elibereaza un hold al userului curent. Idempotent.
 */
export const releaseSeat = ({ seat_id, travel_date }) =>
  apiCall('/seats/release', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ seat_id, travel_date }),
  })

/**
 * Anuleaza un bilet activ. Returneaza refund_amount + refund_tier
 * ('full' | 'half' | 'none') conform regulilor CFR.
 */
export const cancelTicket = (ticketId) =>
  apiCall(`/tickets/${ticketId}/cancel`, { method: 'POST' })

/**
 * Reprogrameaza un bilet pe alt tren / alta data (acelasi traseu).
 * Diferenta de pret nu se restituie.
 */
export const rescheduleTicket = (ticketId, { new_train_id, new_travel_date, new_seat_ids }) =>
  apiCall(`/tickets/${ticketId}/reschedule`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ new_train_id, new_travel_date, new_seat_ids }),
  })

