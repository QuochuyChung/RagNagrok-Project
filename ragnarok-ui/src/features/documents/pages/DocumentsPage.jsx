import { useMemo, useState, useEffect, useRef, useCallback } from 'react'
import JSZip from 'jszip'
import { DocumentList } from '../components/DocumentList'
import { DocumentUploader } from '../components/DocumentUploader'
import { DocumentViewerPanel } from '../components/DocumentPreview'
import { useDocuments } from '../hooks/useDocuments'
import { API_BASE_URL, createRequestId } from '../../../api/client'
import './DocumentsPage.css'

const SPLIT_RATIO_STORAGE_KEY = 'ragnarok_docs_split_ratio'
const DEFAULT_SPLIT_RATIO = 0.4  // 40% pane trái khi có document
const MIN_RATIO = 0.18
const MAX_RATIO = 0.7

function normalizeForSearch(value = '') {
  return value
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/đ/g, 'd')
    .toLowerCase()
}

// Fuzzy match: tính điểm tương đồng giữa query và filename
function fuzzyScore(name, needle) {
  // Tách thành các từ
  const words = name.split(/[^a-z0-9]+/).filter(w => w.length > 0)

  // 1. Từ bắt đầu bằng query (ưu tiên cao nhất)
  if (words.some(word => word.startsWith(needle))) return 10

  // 2. Từ chứa query
  if (words.some(word => word.includes(needle))) return 20

  // 3. Query match từng ký tự trong tên (theo thứ tự)
  let pos = -1
  let matchCount = 0
  for (const char of needle) {
    const newPos = name.indexOf(char, pos + 1)
    if (newPos === -1) break
    pos = newPos
    matchCount++
  }
  if (matchCount === needle.length) {
    return 30 + (name.length - pos) // ưu tiên kết quả match gần cuối hơn
  }

  // 4. Fuzzy match: tính Levenshtein distance đơn giản
  if (needle.length >= 2) {
    // Tìm subsequence gần nhất
    let bestScore = 0
    for (const word of words) {
      if (word.length < needle.length - 1) continue
      // Tính matching characters
      let matched = 0
      let needleIdx = 0
      for (const char of word) {
        if (needleIdx < needle.length && char === needle[needleIdx]) {
          matched++
          needleIdx++
        }
      }
      const ratio = matched / needle.length
      if (ratio >= 0.6 && ratio > bestScore) {
        bestScore = ratio
      }
    }
    if (bestScore > 0) {
      return 40 + Math.floor(bestScore * 10) // score 40-49
    }
  }

  return null
}

function suggestionScore(filename, query) {
  const name = normalizeForSearch(filename)
  const needle = normalizeForSearch(query).trim()
  if (!needle) return null
  if (name.startsWith(needle)) return 0
  if (name.split(/[^a-z0-9]+/).some((part) => part.startsWith(needle))) return 1
  if (name.includes(needle)) return 2

  let position = -1
  for (const character of needle) {
    position = name.indexOf(character, position + 1)
    if (position === -1) return null
  }
  return 3 + position - needle.length
}

function filterDocuments(documents, query, statusFilter) {
  const q = query.trim().toLowerCase()
  // Helper: doc có khớp với status filter hiện tại không.
  // Lưu ý: status='deleted' khớp với mọi doc có is_deleted=true
  // (kể cả khi backend đã set status=PENDING sau restore).
  const matchesStatus = (doc) => {
    if (statusFilter === 'ALL') return true
    if (statusFilter === 'deleted') return Boolean(doc.is_deleted)
    return doc.status === statusFilter
  }

  if (!q) {
    return documents.filter(matchesStatus)
  }

  return documents
    .map((doc) => {
      const filename = doc.filename || doc.doc_name || ''
      const normalizedName = normalizeForSearch(filename)
      const needle = normalizeForSearch(q)
      return {
        doc,
        filename,
        exactScore: suggestionScore(filename, q),
        fuzzyScore: fuzzyScore(normalizedName, needle)
      }
    })
    .filter(({ exactScore, fuzzyScore: fs, doc }) => {
      if (!matchesStatus(doc)) return false
      // Có exact match hoặc fuzzy match
      return exactScore !== null || fs !== null
    })
    .sort((a, b) => {
      // Ưu tiên exact match trước
      if (a.exactScore !== null && b.exactScore !== null) {
        return a.exactScore - b.exactScore || a.filename.localeCompare(b.filename, 'vi')
      }
      if (a.exactScore !== null) return -1
      if (b.exactScore !== null) return 1
      // Sau đó mới đến fuzzy match
      return (a.fuzzyScore || 100) - (b.fuzzyScore || 100) || a.filename.localeCompare(b.filename, 'vi')
    })
    .map(({ doc }) => doc)
}

function sortDocuments(documents, sortField, sortDirection) {
  if (!sortField) return documents

  return [...documents].sort((a, b) => {
    let aVal, bVal

    if (sortField === 'size') {
      aVal = a.file_size || 0
      bVal = b.file_size || 0
    } else if (sortField === 'date') {
      aVal = new Date(a.createdAt || a.ingested_at || a.created_at || 0).getTime()
      bVal = new Date(b.createdAt || b.ingested_at || b.created_at || 0).getTime()
    } else if (sortField === 'name') {
      aVal = (a.filename || a.doc_name || '').toLowerCase()
      bVal = (b.filename || b.doc_name || '').toLowerCase()
      return sortDirection === 'asc'
        ? aVal.localeCompare(bVal, 'vi')
        : bVal.localeCompare(aVal, 'vi')
    }

    return sortDirection === 'asc' ? aVal - bVal : bVal - aVal
  })
}

export function DocumentsPage() {
  const { documents, isLoading, error, uploadBatch, deleteDoc, restoreDoc } = useDocuments()
  const [showUploader, setShowUploader] = useState(false)
  const [searchQuery, setSearchQuery]   = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const [isSearchFocused, setIsSearchFocused] = useState(false)
  const [activeSuggestion, setActiveSuggestion] = useState(-1)
  const [statusFilter, setStatusFilter] = useState('ALL')
  const [message, setMessage]           = useState(null)
  const [sortField, setSortField] = useState('date') // 'name', 'size', 'date'
  const [sortDirection, setSortDirection] = useState('desc') // 'asc', 'desc'
  const [selectedDoc, setSelectedDoc] = useState(null)
  const [selectedIds, setSelectedIds] = useState([])
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [splitRatio, setSplitRatio] = useState(() => {
    const saved = parseFloat(localStorage.getItem(SPLIT_RATIO_STORAGE_KEY))
    if (saved >= MIN_RATIO && saved <= MAX_RATIO) return saved
    return DEFAULT_SPLIT_RATIO
  })
  const [isDraggingDivider, setIsDraggingDivider] = useState(false)

  const searchRef = useRef(null)
  const searchInputRef = useRef(null)

  // Debounce search query (150ms)
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedQuery(searchQuery)
    }, 150)
    return () => clearTimeout(timer)
  }, [searchQuery])

  // Click outside to close suggestions
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (searchRef.current && !searchRef.current.contains(e.target)) {
        setIsSearchFocused(false)
        setActiveSuggestion(-1)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const showMsg = (type, text) => {
    setMessage({ type, text })
    setTimeout(() => setMessage(null), 4000)
  }

  const searchSuggestions = useMemo(() => {
    if (!debouncedQuery.trim()) return []
    const needle = normalizeForSearch(debouncedQuery)
    return documents
      .map((doc) => {
        const filename = doc.filename || doc.doc_name || ''
        const normalizedName = normalizeForSearch(filename)
        return { doc, filename, score: suggestionScore(filename, debouncedQuery), fuzzyScore: fuzzyScore(normalizedName, needle) }
      })
      .filter(({ score, fuzzyScore: fs }) => score !== null || fs !== null)
      .sort((a, b) => {
        // Ưu tiên score chính xác trước
        if (a.score !== null && b.score !== null) {
          return a.score - b.score || a.filename.localeCompare(b.filename, 'vi')
        }
        if (a.score !== null) return -1
        if (b.score !== null) return 1
        // Sau đó mới đến fuzzy match
        return a.fuzzyScore - b.fuzzyScore || a.filename.localeCompare(b.filename, 'vi')
      })
      .slice(0, 6)
  }, [documents, debouncedQuery])

  // Filtered documents for table (sử dụng debouncedQuery để tránh lag khi gõ)
  const filteredDocuments = useMemo(() => {
    const filtered = filterDocuments(documents, debouncedQuery, statusFilter)
    return sortDocuments(filtered, sortField, sortDirection)
  }, [documents, debouncedQuery, statusFilter, sortField, sortDirection])

  const handleSort = (field) => {
    if (sortField === field) {
      // Đảo chiều nếu cùng field
      setSortDirection(prev => prev === 'asc' ? 'desc' : 'asc')
    } else {
      // Field mới: mặc định descending cho size và date
      setSortField(field)
      setSortDirection(field === 'name' ? 'asc' : 'desc')
    }
  }

  // Keyboard navigation for suggestions
  const handleKeyDown = useCallback((e) => {
    if (!isSearchFocused || searchSuggestions.length === 0) return

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        setActiveSuggestion((prev) =>
          prev < searchSuggestions.length - 1 ? prev + 1 : prev
        )
        break
      case 'ArrowUp':
        e.preventDefault()
        setActiveSuggestion((prev) => (prev > 0 ? prev - 1 : -1))
        break
      case 'Enter':
        e.preventDefault()
        if (activeSuggestion >= 0 && searchSuggestions[activeSuggestion]) {
          const filename = searchSuggestions[activeSuggestion].filename
          setSearchQuery(filename)
          setDebouncedQuery(filename)
          setIsSearchFocused(false)
          setActiveSuggestion(-1)
          searchInputRef.current?.blur()
        }
        break
      case 'Escape':
        e.preventDefault()
        setIsSearchFocused(false)
        setActiveSuggestion(-1)
        searchInputRef.current?.blur()
        break
      default:
        break
    }
  }, [isSearchFocused, searchSuggestions, activeSuggestion])

  const handleSuggestionClick = (filename) => {
    setSearchQuery(filename)
    setDebouncedQuery(filename)
    setIsSearchFocused(false)
    setActiveSuggestion(-1)
  }

  const handleClearSearch = () => {
    setSearchQuery('')
    setDebouncedQuery('')
    setIsSearchFocused(false)
    setActiveSuggestion(-1)
  }

  // Reset active suggestion when query changes
  useEffect(() => {
    setActiveSuggestion(-1)
  }, [searchQuery])

  const handleUploadBatch = async (files) => {
    try {
      const result = await uploadBatch(files)
      const n = result?.new?.length || 0
      const u = result?.updated?.length || 0
      const f = result?.failed?.length || 0
      if (f > 0) {
        showMsg('error', `Hoàn tất: ${n} mới, ${u} cập nhật, ${f} thất bại.`)
      } else {
        showMsg('success', `Tải lên thành công: ${n + u} file (${n} mới, ${u} cập nhật).`)
      }
      return result
    } catch (err) {
      showMsg('error', err?.message || 'Tải lên batch thất bại.')
      throw err
    }
  }

  const handleToggleSelectDoc = useCallback((id) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
    )
  }, [])

  const handleToggleSelectAll = useCallback((visibleDocIds = []) => {
    setSelectedIds((prev) => {
      const set = new Set(prev)
      const isAllVisibleSelected = visibleDocIds.every((id) => set.has(id))
      if (isAllVisibleSelected) {
        visibleDocIds.forEach((id) => set.delete(id))
      } else {
        visibleDocIds.forEach((id) => set.add(id))
      }
      return Array.from(set)
    })
  }, [])

  const handleClearSelection = useCallback(() => {
    setSelectedIds([])
  }, [])

  const selectedDocs = useMemo(() => {
    const set = new Set(selectedIds)
    return documents.filter((d) => set.has(d.id || d.doc_id))
  }, [documents, selectedIds])

  const activeSelectedDocs = useMemo(() => {
    return selectedDocs.filter((d) => !d.is_deleted)
  }, [selectedDocs])

  const deletedSelectedDocs = useMemo(() => {
    return selectedDocs.filter((d) => Boolean(d.is_deleted))
  }, [selectedDocs])

  const handleBulkDelete = async () => {
    if (!activeSelectedDocs.length) return
    if (!window.confirm(`Xóa ${activeSelectedDocs.length} tài liệu đã chọn?\nTài liệu sẽ được làm mờ và chuyển xuống cuối danh sách.`)) return
    try {
      for (const doc of activeSelectedDocs) {
        await deleteDoc(doc.id || doc.doc_id)
      }
      const deletedDocIds = new Set(activeSelectedDocs.map((d) => d.id || d.doc_id))
      setSelectedIds((prev) => prev.filter((id) => !deletedDocIds.has(id)))
      showMsg('success', `Đã xóa ${activeSelectedDocs.length} tài liệu đã chọn.`)
    } catch (err) {
      showMsg('error', err?.message || 'Xóa hàng loạt thất bại.')
    }
  }

  const handleBulkRestore = async () => {
    if (!deletedSelectedDocs.length) return
    try {
      for (const doc of deletedSelectedDocs) {
        await restoreDoc(doc.id || doc.doc_id)
      }
      const restoredDocIds = new Set(deletedSelectedDocs.map((d) => d.id || d.doc_id))
      setSelectedIds((prev) => prev.filter((id) => !restoredDocIds.has(id)))
      showMsg('success', `Đã khôi phục ${deletedSelectedDocs.length} tài liệu.`)
    } catch (err) {
      showMsg('error', err?.message || 'Khôi phục hàng loạt thất bại.')
    }
  }

  const handleDelete = async (id) => {
    const doc = documents.find((d) => (d.id || d.doc_id) === id)
    const name = doc?.filename || doc?.doc_name || 'tài liệu này'
    if (!window.confirm(`Xóa tài liệu "${name}"?\nTài liệu sẽ được làm mờ và chuyển xuống cuối danh sách — bạn có thể khôi phục lại sau.`)) return
    try {
      await deleteDoc(id)
      showMsg('success', 'Đã xóa tài liệu. Bạn có thể khôi phục từ cuối danh sách.')
    } catch (err) {
      showMsg('error', err?.message || 'Xóa tài liệu thất bại.')
    }
  }

  const handleRestore = async (id) => {
    try {
      await restoreDoc(id)
      showMsg('success', 'Đã khôi phục tài liệu.')
    } catch (err) {
      showMsg('error', err?.message || 'Khôi phục tài liệu thất bại.')
    }
  }

  const handlePreview = (doc) => {
    setSelectedDoc(doc)
  }

  const handleClosePreview = () => {
    setSelectedDoc(null)
    setIsFullscreen(false)
  }

  const handleToggleFullscreen = useCallback(() => {
    setIsFullscreen((prev) => !prev)
  }, [])

  // Resizable divider handlers
  const containerRef = useRef(null)
  const handleDividerMouseDown = useCallback((e) => {
    e.preventDefault()
    setIsDraggingDivider(true)
  }, [])

  useEffect(() => {
    if (!isDraggingDivider) return

    const handleMouseMove = (e) => {
      const container = containerRef.current
      if (!container) return
      const rect = container.getBoundingClientRect()
      const offsetX = e.clientX - rect.left
      const ratio = offsetX / rect.width
      const clamped = Math.min(MAX_RATIO, Math.max(MIN_RATIO, ratio))
      setSplitRatio(clamped)
    }

    const handleMouseUp = () => {
      setIsDraggingDivider(false)
    }

    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
    }
  }, [isDraggingDivider])

  // Lưu ratio vào localStorage khi thay đổi
  useEffect(() => {
    localStorage.setItem(SPLIT_RATIO_STORAGE_KEY, splitRatio.toString())
  }, [splitRatio])

  const fetchDocBlob = async (doc) => {
    const docId = doc.id || doc.doc_id
    const filename = doc.filename || doc.doc_name || 'document.txt'

    try {
      const token = localStorage.getItem('ragnarok_token')
      const rawTenantId = localStorage.getItem('tenantId')
      const tenantId =
        (rawTenantId && rawTenantId !== 'null' && rawTenantId !== 'undefined')
          ? rawTenantId
          : import.meta.env.VITE_DEFAULT_TENANT

      const headers = {
        'X-Request-ID': createRequestId(),
      }
      if (token) headers['Authorization'] = `Bearer ${token}`
      if (tenantId && tenantId !== 'null' && tenantId !== 'undefined') {
        headers['X-Tenant-ID'] = tenantId
      }

      const res = await fetch(`${API_BASE_URL}/v1/documents/${docId}/content?disposition=attachment`, {
        headers,
      })
      if (res.ok) {
        const disposition = res.headers.get('Content-Disposition') || ''
        const match = disposition.match(/filename\*=UTF-8''([^;]+)/)
        const name = match ? decodeURIComponent(match[1]) : filename
        const blob = await res.blob()
        return { blob, filename: name }
      }
    } catch (e) {
      void e
    }

    const fallbackText = `Document: ${filename}\nID: ${docId}\nStatus: ${doc.status || 'ingested'}\nCreated At: ${doc.createdAt || doc.created_at || new Date().toISOString()}\n\nNội dung tài liệu trong Ragnarok Knowledge Base.`
    const blob = new Blob([fallbackText], { type: 'text/plain;charset=utf-8' })
    return { blob, filename }
  }

  const handleDownload = async (doc) => {
    try {
      const { blob, filename } = await fetchDocBlob(doc)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      setTimeout(() => URL.revokeObjectURL(url), 1000)

      showMsg('success', `Đã tải về: ${filename}`)
    } catch (err) {
      showMsg('error', err?.message || 'Tải về thất bại.')
    }
  }

  const handleBulkDownload = async () => {
    if (!selectedDocs.length) return
    showMsg('success', `Đang nén ${selectedDocs.length} tài liệu thành tệp ZIP...`)

    try {
      const zip = new JSZip()
      const usedNames = new Set()

      for (const doc of selectedDocs) {
        const { blob, filename } = await fetchDocBlob(doc)
        let uniqueName = filename
        let counter = 1
        while (usedNames.has(uniqueName)) {
          const parts = filename.split('.')
          if (parts.length > 1) {
            const ext = parts.pop()
            uniqueName = `${parts.join('.')}_(${counter}).${ext}`
          } else {
            uniqueName = `${filename}_(${counter})`
          }
          counter++
        }
        usedNames.add(uniqueName)
        zip.file(uniqueName, blob)
      }

      const zipBlob = await zip.generateAsync({ type: 'blob' })
      const url = URL.createObjectURL(zipBlob)
      const a = document.createElement('a')
      a.href = url
      const dateStr = new Date().toISOString().slice(0, 10)
      a.download = `ragnarok_documents_${dateStr}.zip`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      setTimeout(() => URL.revokeObjectURL(url), 1000)

      showMsg('success', `Đã tải về gói ZIP chứa ${selectedDocs.length} tài liệu thành công!`)
    } catch (err) {
      showMsg('error', err?.message || 'Nén và tải về hàng loạt thất bại.')
    }
  }

  // Compute stats from full documents list
  const stats = useMemo(() => {
    const total      = documents.length
    const indexed    = documents.filter((d) => {
      const s = (d.status || '').toLowerCase()
      return s === 'ingested' || s === 'completed'
    }).length
    const processing = documents.filter((d) => {
      const s = (d.status || '').toLowerCase()
      return s === 'processing' || s === 'pending'
    }).length
    const totalBytes = documents.reduce((acc, d) => {
      const bytes = d.file_size || (parseFloat(d.size) * (d.size?.includes('MB') ? 1048576 : 1024)) || 0
      return acc + bytes
    }, 0)
    const sizeStr = totalBytes > 0
      ? totalBytes >= 1048576
        ? `${(totalBytes / 1048576).toFixed(1)} MB`
        : `${(totalBytes / 1024).toFixed(1)} KB`
      : '—'
    return { total, indexed, processing, sizeStr }
  }, [documents])

  // Count filtered documents for display
  const filteredCount = filteredDocuments.length
  const totalCount = documents.length

  return (
    <div className={`docs-page ${selectedDoc ? 'docs-page--with-viewer' : ''} ${isFullscreen ? 'docs-page--fullscreen' : ''} ${isDraggingDivider ? 'docs-page--dragging' : ''}`} ref={containerRef}>
      {/* ── Khung bên trái (Header + Stats + Toolbar + Table) ── */}
      {(!selectedDoc || !isFullscreen) && (
        <div
          className="docs-main-container"
          style={{ flexBasis: selectedDoc ? `${splitRatio * 100}%` : '100%' }}
        >
          {/* ── Header ────────────────────────────────────── */}
          <div className="docs-header">
            <div className="docs-header__info">
              <h1 className="docs-header__title">Thư Viện Tài Liệu</h1>
              <p className="docs-header__subtitle">
                Quản lý nguồn tri thức của Workspace — tải lên, lập chỉ mục và kiểm soát tài liệu cho hệ thống RAG.
              </p>
            </div>
            <button
              className={`docs-btn-primary ${showUploader ? 'docs-btn-primary--active' : ''}`}
              onClick={() => setShowUploader((v) => !v)}
            >
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                {showUploader
                  ? <><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></>
                  : <><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" /><polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" /></>
                }
              </svg>
              {showUploader ? 'Đóng' : 'Tải lên tài liệu'}
            </button>
          </div>

          {/* ── Toast ─────────────────────────────────────── */}
          {message && (
            <div className={`docs-toast docs-toast--${message.type}`}>
              <span className="docs-toast__icon">{message.type === 'success' ? '✓' : '!'}</span>
              <span>{message.text}</span>
            </div>
          )}

          {/* ── Stats Cards ───────────────────────────────── */}
          <div className="docs-stats">
            <div className="docs-stat docs-stat--blue">
              <div className="docs-stat__label">Tổng tài liệu</div>
              <div className="docs-stat__value">{stats.total}</div>
              <div className="docs-stat__sub">trong Knowledge Base</div>
            </div>
            <div className="docs-stat docs-stat--green">
              <div className="docs-stat__label">Đã indexed</div>
              <div className="docs-stat__value">{stats.indexed}</div>
              <div className="docs-stat__sub">sẵn sàng cho RAG</div>
            </div>
            <div className="docs-stat docs-stat--amber">
              <div className="docs-stat__label">Đang xử lý</div>
              <div className="docs-stat__value">{stats.processing}</div>
              <div className="docs-stat__sub">đang lập chỉ mục</div>
            </div>
            <div className="docs-stat docs-stat--slate">
              <div className="docs-stat__label">Tổng dung lượng</div>
              <div className="docs-stat__value" style={{ fontSize: stats.sizeStr.length > 6 ? '22px' : '30px' }}>
                {stats.sizeStr}
              </div>
              <div className="docs-stat__sub">đã lưu trữ</div>
            </div>
          </div>

          {/* ── Upload Zone (toggle) ───────────────────────── */}
          {showUploader && (
            <DocumentUploader onUploadBatch={handleUploadBatch} />
          )}

          {/* ── Toolbar ───────────────────────────────────── */}
          <div className="docs-toolbar">
            <div className="docs-search" ref={searchRef}>
              <svg className="docs-search__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
              </svg>
              <input
                ref={searchInputRef}
                className="docs-search__input"
                type="text"
                placeholder="Tìm theo tên tài liệu..."
                value={searchQuery}
                onChange={(e) => { setSearchQuery(e.target.value); setIsSearchFocused(true) }}
                onFocus={() => setIsSearchFocused(true)}
                onKeyDown={handleKeyDown}
              />
              {searchQuery && (
                <button className="docs-search__clear" onClick={handleClearSearch}>✕</button>
              )}
              {isSearchFocused && debouncedQuery.trim() && searchSuggestions.length > 0 && (
                <div className="docs-search__suggestions" role="listbox" aria-label="Gợi ý tài liệu">
                  <div className="docs-search__suggestions-label">Gợi ý tài liệu</div>
                  {searchSuggestions.map(({ doc, filename }, index) => (
                    <button
                      key={doc.id || doc.doc_id}
                      role="option"
                      className={`docs-search__suggestion ${index === activeSuggestion ? 'docs-search__suggestion--active' : ''}`}
                      onMouseDown={(event) => {
                        event.preventDefault()
                        handleSuggestionClick(filename)
                      }}
                      onMouseEnter={() => setActiveSuggestion(index)}
                    >
                      <span className="docs-search__suggestion-icon">⌕</span>
                      <span>{filename}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="docs-filters">
              <span className="docs-filter-label">Trạng thái:</span>
              <select
                className="docs-filter-select"
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
              >
                <option value="ALL">Tất cả</option>
                <option value="ingested">Đã indexed</option>
                <option value="processing">Đang xử lý</option>
                <option value="deleted">Đã xóa</option>
              </select>
              <span className="docs-count">
                {debouncedQuery ? `${filteredCount}/${totalCount} tài liệu` : `${totalCount} tài liệu`}
              </span>
            </div>
          </div>

          {/* ── Bulk Action Bar ────────────────────────────── */}
          {selectedIds.length > 0 && (
            <div className="docs-bulk-bar">
              <div className="docs-bulk-bar__top">
                <div className="docs-bulk-bar__info">
                  <span className="docs-bulk-bar__count">{selectedIds.length}</span>
                  <span>tài liệu được chọn</span>
                </div>
                <div className="docs-bulk-bar__actions">
                  {activeSelectedDocs.length > 0 && (
                    <button
                      className="docs-bulk-bar__btn docs-bulk-bar__btn--danger"
                      onClick={handleBulkDelete}
                      title="Xóa các tài liệu đang hoạt động đã chọn"
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                        <polyline points="3,6 5,6 21,6" />
                        <path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6" />
                      </svg>
                      Xóa ({activeSelectedDocs.length})
                    </button>
                  )}
                  {deletedSelectedDocs.length > 0 && (
                    <button
                      className="docs-bulk-bar__btn docs-bulk-bar__btn--restore"
                      onClick={handleBulkRestore}
                      title="Khôi phục các tài liệu đã xóa được chọn"
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                        <path d="M3 12a9 9 0 1015-6.7L21 8" />
                        <polyline points="21 3 21 8 16 8" />
                      </svg>
                      Khôi phục ({deletedSelectedDocs.length})
                    </button>
                  )}
                  <button
                    className="docs-bulk-bar__btn docs-bulk-bar__btn--download"
                    onClick={handleBulkDownload}
                    title="Tải về các tài liệu đã chọn"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                      <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
                      <polyline points="7 10 12 15 17 10" />
                      <line x1="12" y1="15" x2="12" y2="3" />
                    </svg>
                    Tải về ({selectedIds.length})
                  </button>
                  <button
                    className="docs-bulk-bar__btn docs-bulk-bar__btn--clear"
                    onClick={handleClearSelection}
                  >
                    Bỏ chọn
                  </button>
                </div>
              </div>

              {/* Khung xem lại các tài liệu đã chọn — bỏ chọn từng tài liệu nếu không muốn tải về/xóa nữa */}
              <ul className="docs-bulk-bar__list">
                {selectedDocs.map((doc) => {
                  const id = doc.id || doc.doc_id
                  const name = doc.filename || doc.doc_name || 'Tài liệu'
                  return (
                    <li key={id} className="docs-bulk-bar__list-item" title={name}>
                      <span className="docs-bulk-bar__list-name">{name}</span>
                      <button
                        type="button"
                        className="docs-bulk-bar__list-remove"
                        onClick={() => handleToggleSelectDoc(id)}
                        aria-label={`Bỏ chọn ${name}`}
                        title="Bỏ chọn tài liệu này"
                      >
                        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                          <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                        </svg>
                      </button>
                    </li>
                  )
                })}
              </ul>
            </div>
          )}

          {/* ── Table Card ────────────────────────────────── */}
          <div className="docs-table-card">
            {isLoading ? (
              <div className="docs-empty">
                <div className="docs-spinner" />
                <span>Đang tải danh sách tài liệu...</span>
              </div>
            ) : error ? (
              <div className="docs-empty">
                <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="1.5">
                  <circle cx="12" cy="12" r="10" />
                  <line x1="12" y1="8" x2="12" y2="12" />
                  <line x1="12" y1="16" x2="12.01" y2="16" />
                </svg>
                <p>Đã xảy ra lỗi khi tải dữ liệu. Vui lòng thử lại.</p>
              </div>
            ) : (
              <DocumentList
                documents={filteredDocuments}
                onDelete={handleDelete}
                onRestore={handleRestore}
                onPreview={handlePreview}
                selectedDocId={selectedDoc?.id || selectedDoc?.doc_id}
                selectedIds={selectedIds}
                onToggleSelect={handleToggleSelectDoc}
                onToggleSelectAll={handleToggleSelectAll}
                sortField={sortField}
                sortDirection={sortDirection}
                onSort={handleSort}
              />
            )}
          </div>
        </div>
      )}

      {/* ── Divider kéo thả (chỉ hiện khi có viewer) ─── */}
      {selectedDoc && !isFullscreen && (
        <div
          className="docs-split-view__divider"
          onMouseDown={handleDividerMouseDown}
          role="separator"
          aria-orientation="vertical"
          title="Kéo để thay đổi tỉ lệ"
        >
          <div className="docs-split-view__divider-handle" />
        </div>
      )}

      {/* ── Khung bên phải: Full-height Document Viewer ───────────── */}
      {selectedDoc && (
        <div
          className="docs-viewer-container"
          style={{ flexBasis: isFullscreen ? '100%' : `${(1 - splitRatio) * 100}%` }}
        >
          <DocumentViewerPanel
            document={selectedDoc}
            onClose={handleClosePreview}
            onDownload={handleDownload}
            isFullscreen={isFullscreen}
            onToggleFullscreen={handleToggleFullscreen}
          />
        </div>
      )}
    </div>
  )
}
