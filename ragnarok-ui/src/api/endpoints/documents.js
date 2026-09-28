import { apiRequest } from '../client'

export function listDocuments() {
  return apiRequest('/v1/documents')
}

/** Upload 1 file đơn lẻ → POST /v1/documents */
export function uploadDocument(file) {
  const formData = new FormData()
  formData.set('file', file)
  return apiRequest('/v1/documents', { method: 'POST', body: formData })
}

/**
 * Upload nhiều file hoặc cả folder → POST /v1/documents/batch
 * @param {File[]} files - mảng các File object (có thể có webkitRelativePath)
 */
export function uploadDocumentsBatch(files) {
  const formData = new FormData()
  for (const file of files) {
    // Giữ nguyên relative path nếu có (upload folder qua webkitdirectory)
    formData.append('files', file, file.webkitRelativePath || file.name)
  }
  return apiRequest('/v1/documents/batch', { method: 'POST', body: formData })
}

export function deleteDocument(documentId) {
  return apiRequest(`/v1/documents/${documentId}`, { method: 'DELETE' })
}

/**
 * Khôi phục một tài liệu đã bị soft-delete.
 * Endpoint: POST /v1/documents/{doc_id}/restore
 */
export function restoreDocument(documentId) {
  return apiRequest(`/v1/documents/${documentId}/restore`, { method: 'POST' })
}
