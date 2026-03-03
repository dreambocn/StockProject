export const PASSWORD_POLICY_MESSAGE_KEY = 'password.policy'

const strongPasswordPattern = /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z\d]).{8,128}$/

export const isStrongPassword = (value: string) => strongPasswordPattern.test(value)

const getPasswordScore = (value: string) => {
  let score = 0
  if (value.length >= 8) score += 1
  if (/[a-z]/.test(value)) score += 1
  if (/[A-Z]/.test(value)) score += 1
  if (/\d/.test(value)) score += 1
  if (/[^A-Za-z\d]/.test(value)) score += 1
  return score
}

export const getPasswordStrength = (value: string): 'none' | 'weak' | 'medium' | 'strong' => {
  if (!value.trim()) return 'none'
  const score = getPasswordScore(value)
  if (score >= 5) return 'strong'
  if (score >= 4) return 'medium'
  return 'weak'
}
