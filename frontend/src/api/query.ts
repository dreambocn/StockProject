export const buildQueryString = (params: Record<string, string | number | undefined>) => {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === '') {
      return
    }
    query.set(key, String(value))
  })

  const queryString = query.toString()
  return queryString ? `?${queryString}` : ''
}
