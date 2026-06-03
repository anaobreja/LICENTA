import { Navigate } from 'react-router-dom'

function ProtectedRoute({ isAuthenticated, user, role, children }) {
  const hasToken = Boolean(localStorage.getItem('access_token'))

  const getRouteForRole = (userRole) => {
    if (userRole === 'train_verifier')   return '/verify'
    if (userRole === 'university_agent') return '/agent'
    return '/dashboard'
  }

  if (!isAuthenticated || !hasToken) {
    return <Navigate to="/login" replace />
  }

  if (role && user?.role !== role) {
    return <Navigate to={getRouteForRole(user?.role)} replace />
  }

  return children
}

export default ProtectedRoute

