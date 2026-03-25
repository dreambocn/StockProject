export const PASSWORD_POLICY_MESSAGE_KEY = 'password.policy'

// 正则口径与后端一致，前端只做提示与拦截，最终校验仍以服务端为准。
const strongPasswordPattern = /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z\d]).{8,128}$/

// 与后端保持一致的强密码判定，避免前后端策略不一致。
export const isStrongPassword = (value: string) => strongPasswordPattern.test(value)

const getPasswordScore = (value: string) => {
  // 强度评分用于交互提示，不作为最终安全判定依据。
  let score = 0
  if (value.length >= 8) score += 1
  if (/[a-z]/.test(value)) score += 1
  if (/[A-Z]/.test(value)) score += 1
  if (/\d/.test(value)) score += 1
  if (/[^A-Za-z\d]/.test(value)) score += 1
  return score
}

export const getPasswordStrength = (value: string): 'none' | 'weak' | 'medium' | 'strong' => {
  // 空值单独返回 none，避免初始状态显示误导性的弱密码提示。
  if (!value.trim()) return 'none'
  const score = getPasswordScore(value)
  if (score >= 5) return 'strong'
  if (score >= 4) return 'medium'
  return 'weak'
}
