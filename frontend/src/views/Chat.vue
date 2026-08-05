<script setup>
import { ref, reactive, onMounted, onUnmounted, nextTick } from 'vue'
import { RouterLink } from 'vue-router'
import { ArrowLeft, Bot, Plus, Send, Search, ThumbsUp, ThumbsDown } from 'lucide-vue-next'
import { chatStream, sendFeedback } from '../api.js'

const KEY = 'rl_chat'
const CHIPS = ['개선점이 뭐야?', '강점·셀링포인트는?', '광고 카피 추천해줘', '전체 리뷰 요약해줘', '가성비 좋은 거 추천']
const INTENT_LABEL = { overview: '전체 개요', aggregate: '속성 집계', recommend: '추천', compare: '비교',
  product: '상품 요약', product_aspect: '상품·속성', proscons: '장단점', list: '상품 목록', smalltalk: '대화', review: '리뷰 검색(RAG)',
  repurchase: '재구매 의향', strength: '강점·셀링포인트', improve: '개선 우선순위', copy: '광고 카피', reply: '리뷰 답글' }
const intentLabel = (k) => INTENT_LABEL[k] || 'RAG'

const messages = ref([])
const input = ref('')
const busy = ref(false)
const box = ref(null)
let activeController = null   // 진행 중인 스트림 취소용(언마운트 시 중단)
let unmounted = false         // 언마운트 후엔 늦게 끝난 스트림이 localStorage를 덮어쓰지 않게 막음

function save() {
  if (unmounted) return
  try { localStorage.setItem(KEY, JSON.stringify(messages.value)) } catch (e) { /* quota */ }
}
function load() { try { messages.value = JSON.parse(localStorage.getItem(KEY) || '[]') } catch (e) { messages.value = [] } }
async function scrollDown() { await nextTick(); if (box.value) box.value.scrollTop = box.value.scrollHeight }

async function ask(text) {
  const q = (text ?? input.value).trim()
  if (!q || busy.value) return
  input.value = ''
  busy.value = true
  messages.value.push({ role: 'u', text: q })
  // reactive()로 만들지 않으면 아래 스트리밍 콜백에서 이 참조를 직접 mutate해도(bot.text += ...)
  // Vue의 반응성 프록시(set trap)를 안 거쳐 화면이 갱신되지 않음 — 최종 텍스트는 맞지만
  // 토큰이 올 때마다 실시간으로 안 보이고, busy 값이 바뀌는 순간에야 한 번에 나타났음
  const bot = reactive({ role: 'a', text: '', ev: '', intent: '', evN: 0, q, fb: null, showCorr: false, corrText: '', fbBusy: false, err: '' })
  messages.value.push(bot)
  save(); scrollDown()
  let started = false
  const controller = new AbortController()
  activeController = controller
  try {
    await chatStream(q, {
      signal: controller.signal,
      onMeta: (m) => { bot.intent = m.intent; bot.evN = m.evidence_n },
      onToken: (t) => { if (!started) { bot.text = ''; started = true } bot.text += t; scrollDown() },
      onReplace: (full) => { bot.text = full },
      onEvidence: (ev) => { bot.ev = ev },
    })
  } catch (e) {
    // 스트림이 중간에 끊겨도 이미 받은 답변(bot.text)은 그대로 두고, 에러는 별도 표시만 한다
    if (started) bot.err = '응답이 중간에 끊겼어요. 위 내용까지만 표시됩니다.'
    else bot.text = '응답을 받지 못했어요. (서버/Ollama 확인)'
  } finally {
    if (activeController === controller) activeController = null
    busy.value = false; save(); scrollDown()
  }
}
// 👍는 바로 전송, 👎는 정정 입력창을 먼저 연다(정정이 있어야 recall_corrections에 반영되므로)
function vote(m, v) {
  if (m.fb || m.fbBusy) return
  if (v === 'down') { m.showCorr = true; return }
  submitFeedback(m, 'up')
}
async function submitFeedback(m, v, correction = '') {
  m.fbBusy = true
  try {
    await sendFeedback({ q: m.q, answer: m.text, vote: v, correction })
    m.fb = v
    m.showCorr = false
  } catch (e) { /* 피드백은 부가 기능 - 실패해도 대화 자체는 계속 가능해야 함 */ }
  m.fbBusy = false
  save()
}
function newChat() { messages.value = []; save() }
onMounted(() => { load(); scrollDown() })
onUnmounted(() => { unmounted = true; activeController?.abort() })
</script>

<template>
  <div class="page">
    <div class="bar"><RouterLink class="home" to="/"><ArrowLeft :size="16" /> 홈</RouterLink></div>

    <div class="win">
      <div class="head">
        <span class="av"><Bot :size="22" color="#fff" /></span>
        <div class="ti"><b>ReviewLens 상담봇</b><small>실제 리뷰를 바탕으로 답변해드려요</small></div>
        <button class="new" @click="newChat" title="새 대화"><Plus :size="15" /></button>
        <span class="dot"><i></i> 온라인</span>
      </div>

      <div class="box" ref="box">
        <div v-if="!messages.length" class="msg a">
          <span class="ab"><Bot :size="17" color="#fff" /></span>
          <div class="body">안녕하세요! 무엇을 도와드릴까요?<br>리뷰, 배송, 품질 등 상품과 서비스에 대한 <b>실제 리뷰</b>를 바탕으로 답변해드릴게요.</div>
        </div>
        <template v-for="(m, i) in messages" :key="i">
          <div v-if="m.role === 'u'" class="msg u">{{ m.text }}</div>
          <div v-else class="msg a">
            <span class="ab"><Bot :size="17" color="#fff" /></span>
            <div class="body">
              <div v-if="m.intent" class="ibadge">{{ intentLabel(m.intent) }}<span v-if="m.evN" class="n"> · 근거 {{ m.evN }}</span></div>
              <span>{{ m.text || '…' }}</span>
              <div v-if="m.err" class="err">{{ m.err }}</div>
              <div v-if="m.ev" class="ev">
                <div class="t"><Search :size="13" /> 근거 리뷰</div>
                <div v-for="(line, j) in m.ev.split('\n').filter(Boolean)" :key="j" class="r">{{ line }}</div>
              </div>
              <div v-if="m.text && m.q && !busy" class="fb">
                <template v-if="!m.fb">
                  <span class="fq">이 답변이 도움이 됐나요?</span>
                  <button class="fbtn" :disabled="m.fbBusy" title="좋아요" @click="vote(m, 'up')"><ThumbsUp :size="14" /></button>
                  <button class="fbtn" :disabled="m.fbBusy" title="별로예요" @click="vote(m, 'down')"><ThumbsDown :size="14" /></button>
                </template>
                <span v-else class="fdone">
                  <ThumbsUp v-if="m.fb === 'up'" :size="13" /><ThumbsDown v-else :size="13" />
                  피드백 감사합니다!
                </span>
              </div>
              <div v-if="m.showCorr" class="corr">
                <input v-model="m.corrText" placeholder="어떻게 답했어야 할까요? (선택 입력)" maxlength="1000" :disabled="m.fbBusy"
                  @keydown.enter="submitFeedback(m, 'down', m.corrText)" />
                <button :disabled="m.fbBusy" @click="submitFeedback(m, 'down', m.corrText)">제출</button>
              </div>
            </div>
          </div>
        </template>
      </div>

      <div class="chips">
        <span v-for="c in CHIPS" :key="c" @click="ask(c)">{{ c }}</span>
      </div>
      <div class="in">
        <input v-model="input" placeholder="궁금한 점을 입력해주세요..." maxlength="500" @keydown.enter="ask()" :disabled="busy" />
        <button @click="ask()" :disabled="busy"><Send :size="18" /></button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page{min-height:100vh;background:#eef1f6;display:flex;flex-direction:column;align-items:center}
.bar{width:100%;max-width:820px;padding:18px 22px 8px}
.home{display:flex;align-items:center;gap:6px;color:#6c7280;font-size:14px;font-weight:600}
.win{width:100%;max-width:820px;flex:1;min-height:0;margin-bottom:22px;background:#fff;border:1px solid #e9ecf2;border-radius:20px;display:flex;flex-direction:column;box-shadow:0 12px 40px rgba(30,40,70,.08);overflow:hidden}
.head{display:flex;align-items:center;gap:13px;padding:18px 24px;border-bottom:1px solid #eef0f3}
.head .av{width:44px;height:44px;border-radius:13px;background:linear-gradient(135deg,#f76b8a,#f99);display:flex;align-items:center;justify-content:center;flex:none}
.head .ti{flex:1}.head .ti b{font-size:16px;font-weight:800}.head .ti small{display:block;color:#9aa0ac;font-size:12px;margin-top:2px}
.head .new{display:flex;align-items:center;justify-content:center;width:30px;height:30px;color:#b3b9c4;border:1px solid #eceef2;background:#fff;border-radius:9px;cursor:pointer;transition:.12s;flex:none}
.head .new:hover{border-color:#f0c2cc;color:#777}
.head .dot{display:flex;align-items:center;gap:6px;font-size:12px;color:#1fbf8f;font-weight:700;white-space:nowrap;flex:none}
.head .dot i{width:8px;height:8px;border-radius:50%;background:#1fbf8f;display:inline-block}
.box{flex:1;overflow-y:auto;padding:24px;display:flex;flex-direction:column;gap:16px;background:#fff}
.box::-webkit-scrollbar{width:8px}.box::-webkit-scrollbar-thumb{background:#dde2ea;border-radius:5px}
.msg{font-size:14.5px;line-height:1.65;max-width:80%}
.msg.u{align-self:flex-end;background:#f5566f;color:#fff;padding:11px 16px;border-radius:16px;border-bottom-right-radius:5px}
.msg.a{align-self:flex-start;display:flex;gap:11px;max-width:88%}
.msg.a .ab{width:34px;height:34px;border-radius:11px;background:linear-gradient(135deg,#f76b8a,#f99);display:flex;align-items:center;justify-content:center;flex:none}
.msg.a .body{background:#f4f6fa;padding:13px 16px;border-radius:16px;border-top-left-radius:5px;color:#2b2f38;white-space:pre-wrap}
.msg.a .body b{color:#f0617e;font-weight:700}
.msg.a .ibadge{display:inline-block;font-size:11px;font-weight:700;color:#c2486a;background:#fde7ec;border:1px solid #f7cdd8;border-radius:7px;padding:2px 8px;margin-bottom:8px;white-space:normal}
.msg.a .ibadge .n{color:#a98;font-weight:600}
.msg.a .err{margin-top:8px;font-size:12px;color:#c0392b}
.msg.a .ev{margin-top:10px;background:#fff;border:1px solid #e9ecf2;border-radius:11px;padding:11px 13px;font-size:11.5px;color:#7a8090}
.msg.a .ev .t{font-weight:700;color:#555;margin-bottom:6px;display:flex;align-items:center;gap:5px}
.msg.a .ev .r{padding:3px 0;border-top:1px dashed #eaedf2}
.fb{display:flex;align-items:center;gap:7px;margin-top:10px}
.fb .fq{font-size:11.5px;color:#9aa0ac}
.fbtn{display:flex;align-items:center;justify-content:center;width:26px;height:26px;border:1px solid #e6e9ef;background:#fff;border-radius:8px;color:#9aa0ac;cursor:pointer;transition:.12s}
.fbtn:hover:not(:disabled){border-color:#f3c3cf;color:#d9526e;background:#fdf1f4}
.fbtn:disabled{opacity:.5;cursor:default}
.fdone{display:flex;align-items:center;gap:5px;font-size:11.5px;color:#1fbf8f;font-weight:700}
.corr{display:flex;gap:7px;margin-top:9px}
.corr input{flex:1;border:1px solid #e6e9ef;border-radius:10px;padding:8px 12px;font-size:12.5px;outline:0;background:#fff}
.corr input:focus{border-color:#f3c3cf}
.corr button{border:0;border-radius:10px;padding:0 14px;background:#f5566f;color:#fff;font-size:12px;font-weight:700;cursor:pointer}
.corr button:disabled{opacity:.5;cursor:default}
.chips{display:flex;flex-wrap:wrap;gap:9px;padding:0 24px 14px;background:#fff}
.chips span{font-size:13px;border:1px solid #e6e9ef;border-radius:20px;padding:9px 16px;color:#5a6170;cursor:pointer;background:#fff;transition:.12s}
.chips span:hover{background:#fdf1f4;border-color:#f3c3cf;color:#d9526e}
.in{display:flex;gap:11px;padding:16px 24px;border-top:1px solid #eef0f3;background:#fff}
.in input{flex:1;border:1px solid #e6e9ef;border-radius:14px;padding:14px 18px;font-size:14.5px;outline:0}
.in input:focus{border-color:#f3c3cf}
.in button{width:52px;border:0;border-radius:14px;background:#f5566f;color:#fff;cursor:pointer;display:flex;align-items:center;justify-content:center}
.in button:disabled{opacity:.45}
</style>
