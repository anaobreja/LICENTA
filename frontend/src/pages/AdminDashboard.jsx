import { useEffect, useState } from 'react'
import {
  approveIssuerDocument,
  getDocumentPhotoBlobUrl,
  getIssuerPendingDocuments,
  rejectIssuerDocument
} from '../services/api'
import { useToast } from '../components/Toast.jsx'

function AdminDashboard() {
  const toast = useToast()
  const [documents, setDocuments] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [workingId, setWorkingId] = useState(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [yearFilter, setYearFilter] = useState('')
  const [rejectDialog, setRejectDialog] = useState({ open: false, documentId: null, notes: '' })
  const [previewModal, setPreviewModal] = useState({
    open: false,
    userLabel: '',
    docs: []
  })

  const loadPending = async (year = null) => {
    setLoading(true)
    try {
      const data = await getIssuerPendingDocuments(year || null)
      setDocuments(data || [])
    } catch (err) {
      setError(err.message || 'Nu am putut incarca documentele pending')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadPending()
  }, [])

  const onYearFilterChange = (e) => {
    const val = e.target.value
    setYearFilter(val)
    loadPending(val ? parseInt(val, 10) : null)
  }

  const onApprove = async (documentId) => {
    setError('')
    setWorkingId(documentId)
    try {
      await approveIssuerDocument(documentId, 'Aprobat de issuer verifier')
      toast('Document aprobat.', 'success')
      await loadPending()
    } catch (err) {
      setError(err.message || 'Nu am putut aproba documentul')
    } finally {
      setWorkingId(null)
    }
  }

  const onRejectClick = (documentId) => {
    setRejectDialog({ open: true, documentId, notes: '' })
  }

  const onRejectConfirm = async () => {
    const { documentId, notes } = rejectDialog
    setError('')
    setSuccess('')
    setWorkingId(documentId)
    try {
      const result = await rejectIssuerDocument(documentId, notes || 'Respins de issuer verifier')
      console.log('Reject result:', result)
      setSuccess('Document respins cu succes')
      toast('Document respins.', 'warning')
      setRejectDialog({ open: false, documentId: null, notes: '' })
      await loadPending()
    } catch (err) {
      console.error('Reject error:', err)
      setError(err.message || 'Nu am putut respinge documentul')
    } finally {
      setWorkingId(null)
    }
  }

  const onRejectCancel = () => {
    setRejectDialog({ open: false, documentId: null, notes: '' })
  }

  const closePreviewModal = () => {
    previewModal.docs.forEach((doc) => {
      if (doc.photoUrl) {
        URL.revokeObjectURL(doc.photoUrl)
      }
    })
    setPreviewModal({
      open: false,
      userLabel: '',
      docs: []
    })
  }

  const onPreviewApplication = async (doc) => {
    setError('')
    setPreviewLoading(true)
    try {
      const relatedDocs = documents.filter((d) => d.user_id === doc.user_id)
      const docsWithPhotos = await Promise.all(
        relatedDocs.map(async (item) => {
          if (!item.has_photo) {
            return { ...item, photoUrl: null }
          }
          const photoUrl = await getDocumentPhotoBlobUrl(item.id)
          return { ...item, photoUrl }
        })
      )

      setPreviewModal({
        open: true,
        userLabel: `${doc.first_name} ${doc.last_name} (${doc.email})`,
        docs: docsWithPhotos,
      })
    } catch (err) {
      setError(err.message || 'Nu am putut deschide pozele documentelor')
    } finally {
      setPreviewLoading(false)
    }
  }

  return (
    <div className="container mx-auto px-4 py-8 max-w-5xl">
      <h1 className="text-3xl font-bold mb-6 text-slate-900 dark:text-slate-50">Issuer Verifier Dashboard</h1>

      {error && <div className="bg-red-50 border border-red-200 text-red-700 p-3 rounded-xl mb-4 dark:bg-red-950/40 dark:border-red-800 dark:text-red-200">{error}</div>}
      {success && <div className="bg-green-50 border border-green-200 text-green-700 p-3 rounded-xl mb-4 dark:bg-emerald-950/30 dark:border-emerald-800 dark:text-emerald-200">{success}</div>}

      <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm dark:bg-slate-900 dark:border-slate-700">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <h2 className="text-xl font-bold text-slate-900 dark:text-slate-100">Documente in asteptare</h2>
          <div className="flex items-center gap-2">
            <label className="text-sm font-semibold text-slate-700 dark:text-slate-300">Filtreaza dupa an:</label>
            <select
              value={yearFilter}
              onChange={onYearFilterChange}
              className="border border-slate-300 dark:border-slate-600 rounded-lg px-3 py-1.5 text-sm dark:bg-slate-800 dark:text-white"
            >
              <option value="">Toți anii</option>
              <option value="1">Licență 1</option>
              <option value="2">Licență 2</option>
              <option value="3">Licență 3</option>
              <option value="4">Licență 4</option>
              <option value="5">Master 1</option>
              <option value="6">Master 2</option>
            </select>
          </div>
        </div>

        {loading ? (
          <p className="text-slate-600 dark:text-slate-300">Loading...</p>
        ) : documents.length === 0 ? (
          <p className="text-slate-600 dark:text-slate-300">Nu exista documente pending.</p>
        ) : (
          <div className="space-y-3">
            {documents.map((doc) => (
              <div key={doc.id} className="border border-slate-200 rounded-xl p-4 dark:border-slate-700 dark:bg-slate-950">
                <div className="font-semibold text-slate-900 dark:text-slate-100">#{doc.id} — {doc.document_type}</div>
                <div className="text-sm text-slate-700 dark:text-slate-200">Cont: {doc.first_name} {doc.last_name} ({doc.email})</div>

                {/* Date CI extrase prin scanare MRZ */}
                {doc.ci_name && (
                  <div className="mt-2 rounded-lg bg-indigo-50 dark:bg-indigo-950/40 border border-indigo-200 dark:border-indigo-800 px-3 py-2 text-xs space-y-0.5">
                    <div className="font-semibold text-indigo-800 dark:text-indigo-300 mb-1">Date CI (extrase automat din MRZ):</div>
                    <div className="text-indigo-900 dark:text-indigo-200">Nume: <strong>{doc.ci_name}</strong></div>
                    {doc.ci_number && <div className="text-indigo-900 dark:text-indigo-200">Nr. CI: <strong>{doc.ci_number}</strong></div>}
                    {doc.ci_date_of_birth && <div className="text-indigo-900 dark:text-indigo-200">Data nașterii: <strong>{doc.ci_date_of_birth}</strong></div>}
                    {doc.ci_sex && <div className="text-indigo-900 dark:text-indigo-200">Sex: <strong>{doc.ci_sex === 'M' ? 'Masculin' : 'Feminin'}</strong></div>}
                  </div>
                )}

                <div className="text-sm text-slate-600 dark:text-slate-300 mt-1">Nr. legitimație: {doc.document_number_masked}</div>
                {doc.university_name && (
                  <div className="text-sm text-slate-600 dark:text-slate-300">
                    {doc.university_name}
                    {doc.year_of_study && (
                      <span className="ml-2 inline-block bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 text-xs font-semibold px-2 py-0.5 rounded-full">
                        {doc.year_of_study <= 4 ? `Licență ${doc.year_of_study}` : `Master ${doc.year_of_study - 4}`}
                      </span>
                    )}
                  </div>
                )}
                <div className="text-sm text-slate-600 dark:text-slate-300">Poză legitimație: {doc.has_photo ? 'da' : 'nu'}</div>
                <div className="mt-3 flex gap-2">
                  {doc.has_photo && (
                    <button
                      onClick={() => onPreviewApplication(doc)}
                      disabled={previewLoading}
                      className="bg-slate-200 text-slate-800 px-3 py-1 rounded hover:bg-slate-300 dark:bg-slate-800 dark:text-slate-100 dark:hover:bg-slate-700"
                    >
                      {previewLoading ? 'Se incarca...' : 'Vezi aplicarea (popup)'}
                    </button>
                  )}
                  <button
                    onClick={() => onApprove(doc.id)}
                    disabled={workingId === doc.id}
                    className="bg-green-600 text-white px-3 py-1 rounded hover:bg-green-700 disabled:opacity-60"
                  >
                    Aproba
                  </button>
                  <button
                    onClick={() => onRejectClick(doc.id)}
                    disabled={workingId === doc.id}
                    className="bg-red-600 text-white px-3 py-1 rounded hover:bg-red-700 disabled:opacity-60"
                  >
                    Respinge
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {previewModal.open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-5xl max-h-[90vh] overflow-auto bg-white rounded-2xl shadow-2xl border border-slate-200 dark:bg-slate-900 dark:border-slate-700">
            <div className="sticky top-0 bg-white border-b border-slate-200 p-4 flex items-center justify-between dark:bg-slate-900 dark:border-slate-700">
              <div>
                <h3 className="text-xl font-bold text-slate-900 dark:text-slate-100">Poze aplicare</h3>
                <p className="text-sm text-slate-600 dark:text-slate-300">{previewModal.userLabel}</p>
              </div>
              <button
                onClick={closePreviewModal}
                className="bg-slate-900 text-white px-3 py-1 rounded hover:bg-slate-800 dark:bg-cyan-600 dark:hover:bg-cyan-500"
              >
                Inchide
              </button>
            </div>

            <div className="p-4 grid gap-4 md:grid-cols-2">
              {previewModal.docs.map((item) => (
                <div key={item.id} className="border border-slate-200 rounded-xl p-3 dark:border-slate-700 dark:bg-slate-950">
                  <p className="font-semibold mb-1 text-slate-900 dark:text-slate-100">{item.document_type}</p>
                  <p className="text-sm text-slate-600 dark:text-slate-300 mb-2">Numar mascat: {item.document_number_masked}</p>
                  {item.photoUrl ? (
                    <img
                      src={item.photoUrl}
                      alt={`Document ${item.document_type}`}
                      className="w-full rounded-lg border border-slate-200 dark:border-slate-700"
                    />
                  ) : (
                    <p className="text-sm text-slate-500 dark:text-slate-400">Fara poza pentru acest document.</p>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {rejectDialog.open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-white rounded-2xl shadow-2xl border border-slate-200 max-w-md w-full dark:bg-slate-900 dark:border-slate-700">
            <div className="p-4 border-b border-slate-200 dark:border-slate-700">
              <h3 className="text-lg font-bold text-slate-900 dark:text-slate-100">Respinge document</h3>
            </div>
            <div className="p-4">
              <label className="block text-sm font-semibold mb-2 text-slate-800 dark:text-slate-200">Motiv respingere:</label>
              <textarea
                value={rejectDialog.notes}
                onChange={(e) => setRejectDialog({ ...rejectDialog, notes: e.target.value })}
                className="w-full border border-slate-300 rounded-lg p-2 text-sm dark:bg-slate-950 dark:border-slate-700 dark:text-slate-100"
                rows="4"
                placeholder="Explica de ce respingi acest document..."
              />
            </div>
            <div className="p-4 border-t border-slate-200 flex gap-2 justify-end dark:border-slate-700">
              <button
                onClick={onRejectCancel}
                className="px-4 py-2 rounded bg-slate-200 text-slate-800 hover:bg-slate-300 dark:bg-slate-800 dark:text-slate-100 dark:hover:bg-slate-700"
              >
                Anuleaza
              </button>
              <button
                onClick={onRejectConfirm}
                disabled={workingId === rejectDialog.documentId}
                className="px-4 py-2 rounded bg-red-600 text-white hover:bg-red-700 disabled:opacity-60"
              >
                {workingId === rejectDialog.documentId ? 'Se proceseaza...' : 'Respinge'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default AdminDashboard

