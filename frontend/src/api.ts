import type { AIAnalysisResult, ChainHealth, ChainProfile, EnterpriseSummary, GapAnalysis, SegmentEnterprise } from './types'

const base = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
const verificationTokenKey = 'chain-profile-demo-verification-token'

export function getVerificationToken(): string {
  return typeof window === 'undefined' ? '' : window.sessionStorage.getItem(verificationTokenKey) || ''
}

export function saveVerificationToken(token: string): void {
  window.sessionStorage.setItem(verificationTokenKey, token)
}

export function clearVerificationToken(): void {
  window.sessionStorage.removeItem(verificationTokenKey)
}

function verificationHeaders(): HeadersInit {
  const token = getVerificationToken()
  return token ? { Authorization: 'Bearer ' + token } : {}
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(base + path, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options?.headers },
  })
  if (!response.ok) {
    const detail = await response.text()
    throw new Error(detail || '请求失败（' + response.status + '）')
  }
  return response.json() as Promise<T>
}

export const api = {
  enterprises: () => request<EnterpriseSummary[]>('/api/v1/enterprises'),
  profile: (id: string) => request<ChainProfile>('/api/v1/enterprises/' + encodeURIComponent(id) + '/chain-profile'),
  aiAnalysis: (id: string) => request<AIAnalysisResult>('/api/v1/enterprises/' + encodeURIComponent(id) + '/ai-analysis', { method: 'POST' }),
  chainHealth: (id: string) => request<ChainHealth>('/api/v1/chains/' + encodeURIComponent(id) + '/health'),
  segmentEnterprises: (id: string) => request<SegmentEnterprise[]>('/api/v1/segments/' + encodeURIComponent(id) + '/enterprises'),
  gapAnalysis: (id: string) => request<GapAnalysis>('/api/v1/segments/' + encodeURIComponent(id) + '/gap-analysis'),
  verify: (positionId: number, action: 'confirm' | 'reject' | 'correct', correctedSegmentId?: string) =>
    request<unknown>('/api/v1/verifications', {
      method: 'POST',
      headers: verificationHeaders(),
      body: JSON.stringify({
        position_id: positionId,
        action,
        ...(correctedSegmentId ? { corrected_segment_id: correctedSegmentId } : {}),
        operator: 'demo-operator',
        idempotency_key: Date.now().toString(36) + '-' + Math.random().toString(36).slice(2),
      }),
    }),
}
