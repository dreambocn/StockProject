import { describe, expect, it } from 'vitest'

import { getPasswordStrength, isStrongPassword } from './password'

describe('isStrongPassword', () => {
  it('accepts strong password format', () => {
    expect(isStrongPassword('StrongP@ss1')).toBe(true)
  })

  it('rejects password without uppercase lowercase digit and symbol', () => {
    expect(isStrongPassword('weakpass')).toBe(false)
    expect(isStrongPassword('WEAKPASS1!')).toBe(false)
    expect(isStrongPassword('Weakpass!!')).toBe(false)
    expect(isStrongPassword('Weakpass1')).toBe(false)
  })

  it('returns weak medium strong levels', () => {
    expect(getPasswordStrength('')).toBe('none')
    expect(getPasswordStrength('abc')).toBe('weak')
    expect(getPasswordStrength('Weakpass1')).toBe('medium')
    expect(getPasswordStrength('StrongP@ss1')).toBe('strong')
  })
})
