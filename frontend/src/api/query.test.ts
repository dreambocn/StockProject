import { describe, expect, it } from 'vitest'

import { buildQueryString } from './query'

describe('buildQueryString', () => {
  it('returns empty string when no params are present', () => {
    expect(buildQueryString({})).toBe('')
    expect(buildQueryString({ keyword: '' })).toBe('')
    expect(buildQueryString({ keyword: undefined })).toBe('')
  })

  it('builds query string with string and number values', () => {
    const query = buildQueryString({
      keyword: '平安',
      page: 2,
      page_size: 50,
      list_status: 'ALL',
    })

    expect(query).toBe(
      '?keyword=%E5%B9%B3%E5%AE%89&page=2&page_size=50&list_status=ALL',
    )
  })
})
