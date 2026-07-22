// FastAPI 백엔드 호출 (/api/*). 개발은 Vite 프록시, 빌드는 동일 오리진.

export async function getBoard() {
  const r = await fetch('/api/board', { cache: 'no-store' })
  if (!r.ok) throw new Error('board fetch failed')
  return r.json()
}

// 챗봇 답변 피드백(👍/👎 + 정정) — correction이 있으면 이후 비슷한 질문에 우선 반영됨(recall_corrections)
export async function sendFeedback({ q, answer, vote, correction = '' }) {
  const r = await fetch('/api/feedback', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ q, answer, vote, correction }),
  })
  if (!r.ok) throw new Error('feedback failed')
  return r.json()
}

// 챗봇 피드백 집계(👍/👎 개수 + 실제 반영된 정정 목록) — 설정 탭에서 조회
export async function getFeedbackStats() {
  const r = await fetch('/api/feedback/stats', { cache: 'no-store' })
  if (!r.ok) throw new Error('feedback stats fetch failed')
  return r.json()
}

// 챗봇 스트리밍(NDJSON) — onToken/onReplace/onEvidence 콜백으로 토큰 전달.
// idleTimeoutMs: 마지막 청크 이후 이만큼 새 데이터가 없으면 멈춘 것으로 보고 중단(고정 전체 타임아웃이
// 아닌 이유 — 첫 응답은 콜드로드로 십수 초 걸릴 수 있어, 느리지만 진행 중인 응답을 오탐으로 끊으면 안 됨).
export async function chatStream(q, { onToken, onReplace, onEvidence, onMeta, idleTimeoutMs = 30000 } = {}) {
  const controller = new AbortController()
  const res = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ q }),
    signal: controller.signal,
  })
  if (!res.ok) throw new Error(`chat stream 요청 실패 (HTTP ${res.status})`)
  const reader = res.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  try {
    while (true) {
      let timer
      const idle = new Promise((_, reject) => {
        timer = setTimeout(() => { controller.abort(); reject(new Error('응답이 지연되고 있어요(타임아웃)')) }, idleTimeoutMs)
      })
      let value, done
      try {
        ;({ value, done } = await Promise.race([reader.read(), idle]))
      } finally {
        clearTimeout(timer)
      }
      if (done) break
      buf += dec.decode(value, { stream: true })
      let nl
      while ((nl = buf.indexOf('\n')) >= 0) {
        const line = buf.slice(0, nl).trim()
        buf = buf.slice(nl + 1)
        if (!line) continue
        const o = JSON.parse(line)
        if (o.meta !== undefined) onMeta && onMeta(o.meta)
        if (o.token !== undefined) onToken && onToken(o.token)
        if (o.replace !== undefined) onReplace && onReplace(o.replace)
        if (o.evidence !== undefined) onEvidence && onEvidence(o.evidence)
      }
    }
  } finally {
    reader.cancel().catch(() => {})
  }
}
