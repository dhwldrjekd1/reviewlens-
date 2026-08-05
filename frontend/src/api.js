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
// firstChunkTimeoutMs: "콜드로드"는 첫 read 한 번으로 안 끝날 수 있음(meta 이벤트는 금방 오지만,
// 그 뒤 실제 LLM 첫 토큰이 프리워밍 요청과 큐잉 경합하며 늦게 올 수 있음) — 그래서 첫 read만이
// 아니라 "첫 토큰(또는 토큰 없는 즉답/캐시 응답의 evidence+done)"을 받기 전까지 계속 이 넉넉한
// 타임아웃을 쓰고, 실제 스트리밍이 시작된 뒤에야 idleTimeoutMs로 좁힌다.
// signal: 호출부가 진행 중인 스트림을 외부에서 취소하고 싶을 때(예: 컴포넌트 언마운트) 넘기는
// AbortSignal. 내부 idle/first-chunk 타임아웃용 controller와 별개라, 둘 중 어느 쪽이 먼저
// abort돼도 fetch가 즉시 중단되도록 이어붙인다.
export async function chatStream(q, { onToken, onReplace, onEvidence, onMeta, idleTimeoutMs = 30000, firstChunkTimeoutMs = 90000, signal } = {}) {
  const controller = new AbortController()
  if (signal) {
    if (signal.aborted) controller.abort()
    else signal.addEventListener('abort', () => controller.abort())
  }
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
  let warm = true   // 첫 토큰(또는 즉답)을 아직 못 받은 "콜드로드 구간"인지
  try {
    while (true) {
      let timer
      const timeoutMs = warm ? firstChunkTimeoutMs : idleTimeoutMs
      const idle = new Promise((_, reject) => {
        timer = setTimeout(() => { controller.abort(); reject(new Error('응답이 지연되고 있어요(타임아웃)')) }, timeoutMs)
      })
      let value, done
      try {
        ;({ value, done } = await Promise.race([reader.read(), idle]))
      } finally {
        clearTimeout(timer)
      }
      if (done) {
        buf += dec.decode()   // 스트림 종료 시 남아있을 수 있는 마지막 멀티바이트 문자를 플러시
        break
      }
      buf += dec.decode(value, { stream: true })
      let nl
      while ((nl = buf.indexOf('\n')) >= 0) {
        const line = buf.slice(0, nl).trim()
        buf = buf.slice(nl + 1)
        if (!line) continue
        const o = JSON.parse(line)
        if (o.meta !== undefined) onMeta && onMeta(o.meta)
        if (o.token !== undefined) { onToken && onToken(o.token); warm = false }
        if (o.replace !== undefined) onReplace && onReplace(o.replace)
        if (o.evidence !== undefined) { onEvidence && onEvidence(o.evidence); warm = false }
      }
    }
    const tail = buf.trim()   // 마지막 줄이 개행 없이 끝났을 경우까지 처리
    if (tail) {
      try {
        const o = JSON.parse(tail)
        if (o.meta !== undefined) onMeta && onMeta(o.meta)
        if (o.token !== undefined) onToken && onToken(o.token)
        if (o.replace !== undefined) onReplace && onReplace(o.replace)
        if (o.evidence !== undefined) onEvidence && onEvidence(o.evidence)
      } catch {
        // 연결이 진짜 중간에 끊겨 마지막 조각이 불완전한 경우 — 이미 받은 응답은 그대로 두고 무시
      }
    }
  } finally {
    reader.cancel().catch(() => {})
  }
}
