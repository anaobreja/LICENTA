/**
 * API Service - Handles all backend communication
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api'

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
    let errorMessage = `HTTP ${response.status}`
    try {
      const errorData = await response.json()
      if (errorData?.detail) {
        errorMessage = typeof errorData.detail === 'string'
          ? errorData.detail
          : JSON.stringify(errorData.detail)
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
