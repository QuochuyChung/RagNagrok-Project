export function useRequestId() {
  return crypto.randomUUID()
}
