export function DocumentStatusBadge({ status = 'pending' }) {
  return <span data-status={status}>{status}</span>
}
