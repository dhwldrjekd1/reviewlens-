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

// 챗봇 스트리밍(NDJSON) — onToken/onReplace/onEvidence 콜백으로 토큰 전달
export async function chatStream(q, { onToken, onReplace, onEvidence, onMeta } = {}) {
  const res = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ q }),
  })
  const reader = res.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  while (true) {
    const { value, done } = await reader.read()
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
}
