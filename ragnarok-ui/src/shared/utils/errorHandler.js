export function parseApiError(error) {
  if (!error) {
    return { message: 'Unknown error' }
  }

  if (typeof error === 'string') {
    return { message: error }
  }

  return {
    code: error.error_code,
    message: error.message || 'Request failed',
    requestId: error.request_id,
    timestamp: error.timestamp,
  }
}
