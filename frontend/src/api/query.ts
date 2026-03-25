export const buildQueryString = (params: Record<string, string | number | undefined>) => {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    // 空值与空字符串不下发，避免覆盖后端默认查询逻辑。
    if (value === undefined || value === '') {
      return
    }
    query.set(key, String(value))
  })

  const queryString = query.toString()
  // 无参数时返回空串，避免出现多余的问号。
  return queryString ? `?${queryString}` : ''
}
