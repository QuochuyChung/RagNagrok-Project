import { useEffect, useState } from 'react'
import {
  listDocuments,
  uploadDocument,
  uploadDocumentsBatch,
  deleteDocument,
  restoreDocument,
} from '../../../api/endpoints/documents'

export function useDocuments() {
  const [documents, setDocuments] = useState([])
  const [error, setError] = useState(null)
  const [isLoading, setIsLoading] = useState(false)

  // Load mock list initially
  const getMockDocs = () => {
    const stored = localStorage.getItem('ragnarok_mock_documents')
    if (stored) return JSON.parse(stored)
    const initial = [
      { id: 'doc-1', filename: 'chinh_sach_nhan_su.pdf', size: '2.4 MB', status: 'ingested', createdAt: '2026-07-04T08:00:00Z' },
      { id: 'doc-2', filename: 'huong_dan_bao_mat.md', size: '15.2 KB', status: 'ingested', createdAt: '2026-07-05T12:00:00Z' },
      { id: 'doc-3', filename: 'bao_cao_tai_chinh_q2.pdf', size: '12.8 MB', status: 'ingested', createdAt: '2026-07-06T15:30:00Z' }
    ]
    localStorage.setItem('ragnarok_mock_documents', JSON.stringify(initial))
    return initial
  }

  function refresh() {
    setIsLoading(true)
    setError(null)
    return listDocuments()
      .then((data) => {
        // Backend may return {documents: [...]} or just [...]
        const rawList = Array.isArray(data)
          ? data
          : Array.isArray(data?.documents)
          ? data.documents
          : []
        const list = rawList.map((doc) => {
          const s = (doc.status || '').toLowerCase()
          const normalizedStatus =
            s === 'completed' || s === 'ingested'
              ? 'ingested'
              : s === 'failed'
              ? 'failed'
              : 'processing'
          return {
            ...doc,
            id: doc.doc_id || doc.id,
            filename: doc.doc_name || doc.filename,
            file_size: doc.file_size !== undefined ? doc.file_size : 0,
            status: normalizedStatus,
            createdAt: doc.created_at || doc.ingested_at || doc.createdAt,
            is_deleted: Boolean(doc.is_deleted),
          }
        })
        setDocuments(list)
      })
      .catch((err) => {
        console.warn('Backend API not available, falling back to mock storage:', err)
        setDocuments(getMockDocs())
      })
      .finally(() => setIsLoading(false))
  }

  async function upload(file) {
    setIsLoading(true)
    setError(null)
    try {
      const res = await uploadDocument(file)
      await refresh()
      return res
    } catch (err) {
      throw err
    } finally {
      setIsLoading(false)
    }
  }

  /** Upload nhiều file cùng lúc (batch / folder / zip) */
  async function uploadBatch(files) {
    setIsLoading(true)
    setError(null)
    try {
      const result = await uploadDocumentsBatch(files)
      await refresh()
      return result // { new: [], updated: [], unchanged: [], failed: [] }
    } catch (err) {
      throw err
    } finally {
      setIsLoading(false)
    }
  }

  const deleteDoc = async (docId) => {
    try {
      await deleteDocument(docId)
      await refresh()
    } catch (err) {
      console.warn('Backend deleteDocument failed, using local fallback:', err)
      // Soft-delete ở local: đánh dấu is_deleted=true để khớp với backend
      // và vẫn hiển thị ở cuối danh sách cho tới khi người dùng restore.
      const currentList = getMockDocs()
      const updated = currentList.map((doc) =>
        doc.id === docId ? { ...doc, is_deleted: true } : doc
      )
      localStorage.setItem('ragnarok_mock_documents', JSON.stringify(updated))
      setDocuments(updated)
    }
  }

  const restoreDoc = async (docId) => {
    try {
      await restoreDocument(docId)
      await refresh()
    } catch (err) {
      console.warn('Backend restoreDocument failed, using local fallback:', err)
      // Local fallback: clear is_deleted flag in mock storage.
      const currentList = getMockDocs()
      const updated = currentList.map((doc) =>
        doc.id === docId ? { ...doc, is_deleted: false } : doc
      )
      localStorage.setItem('ragnarok_mock_documents', JSON.stringify(updated))
      setDocuments(updated)
    }
  }

  const reindexDoc = (docId) => {
    const currentList = getMockDocs()
    const updated = currentList.map(doc => 
      doc.id === docId ? { ...doc, status: 'processing' } : doc
    )
    setDocuments(updated)
    localStorage.setItem('ragnarok_mock_documents', JSON.stringify(updated))
    
    setTimeout(() => {
      const currentList2 = JSON.parse(localStorage.getItem('ragnarok_mock_documents') || '[]')
      const updatedList = currentList2.map(doc => 
        doc.id === docId ? { ...doc, status: 'ingested' } : doc
      )
      localStorage.setItem('ragnarok_mock_documents', JSON.stringify(updatedList))
      setDocuments(updatedList)
    }, 3000)
  }

  useEffect(() => {
    refresh()
  }, [])

  return { documents, error, isLoading, refresh, upload, uploadBatch, deleteDoc, restoreDoc, reindexDoc }
}
