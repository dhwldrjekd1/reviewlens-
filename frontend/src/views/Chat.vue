<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { RouterLink } from 'vue-router'
import { ArrowLeft, Bot, Plus, Send, Search } from 'lucide-vue-next'
import { chatStream } from '../api.js'

const KEY = 'rl_chat'
const GREETING = '안녕하세요! 무엇을 도와드릴까요? 상품·배송·품질·전체 리뷰에 대해 실제 리뷰를 근거로 답해드려요.'
const CHIPS = ['전체 리뷰 알려줘', '배송 빠른 편인가요?', '이어폰 소리 어때요?', '포장 상태 괜찮나요?', '가성비 좋은 거 추천해줘']

const messages = ref([])      // {role:'u'|'a', text, ev}
const input = ref('')
const busy = ref(false)
const box = ref(null)

function save() {
  try { localStorage.setItem(KEY, JSON.stringify(messages.value)) } catch (e) { /* quota */ }
}
function load() {
  try { messages.value = JSON.parse(localStorage.getItem(KEY) || '[]') } catch (e) { messages.value = [] }
}
async function scrollDown() {
  await nextTick()
  if (box.value) box.value.scrollTop = box.value.scrollHeight
}

async function ask(text) {
  const q = (text ?? input.value).trim()
  if (!q || busy.value) return
  input.value = ''
  busy.value = true
  messages.value.push({ role: 'u', text: q })
  const bot = { role: 'a', text: '', ev: '' }
  messages.value.push(bot)
  save()
  scrollDown()
  let started = false
  try {
    await chatStream(q, {
      onToken: (t) => { if (!started) { bot.text = ''; started = true } bot.text += t; scrollDown() },
      onReplace: (full) => { bot.text = full },
      onEvidence: (ev) => { bot.ev = ev },
    })
  } catch (e) {
    bot.text = '응답을 받지 못했어요. (서버/Ollama 확인)'
  }
  busy.value = false
  save()
  scrollDown()
}

function newChat() {
  messages.value = []
  save()
}

onMounted(() => { load(); scrollDown() })
</script>

<template>
  <div class="chat">
    <div class="top">
      <RouterLink class="home" to="/"><ArrowLeft :size="16" /> 홈</RouterLink>
      <div class="ti">
        <span class="av"><Bot :size="17" color="#fff" /></span>
        <div><b>ReviewLens 상담봇</b><small>실제 리뷰를 근거로 답해드려요</small></div>
      </div>
      <div class="grow"></div>
      <button class="new" @click="newChat"><Plus :size="15" /> 새 대화</button>
    </div>

    <div class="box" ref="box">
      <div class="col">
        <div v-if="!messages.length" class="msg a">
          <span class="ab"></span><div class="body">{{ GREETING }}</div>
        </div>
        <template v-for="(m, i) in messages" :key="i">
          <div v-if="m.role === 'u'" class="msg u">{{ m.text }}</div>
          <div v-else class="msg a">
            <span class="ab"></span>
            <div class="body">
              <span>{{ m.text || '…' }}</span>
              <div v-if="m.ev" class="ev">
                <div class="t"><Search :size="13" /> 근거 리뷰</div>
                <div v-for="(line, j) in m.ev.split('\n').filter(Boolean)" :key="j" class="r">{{ line }}</div>
              </div>
            </div>
          </div>
        </template>
      </div>
    </div>

    <div class="dock">
      <div class="dockin">
        <div class="chips">
          <span v-for="c in CHIPS" :key="c" @click="ask(c)">{{ c }}</span>
        </div>
        <div class="in">
          <input v-model="input" placeholder="궁금한 점을 입력해주세요..." @keydown.enter="ask()" :disabled="busy" />
          <button @click="ask()" :disabled="busy"><Send :size="18" /></button>
        </div>
        <div class="hint">대화는 이 브라우저에만 저장됩니다 · 언제든 ‘새 대화’로 초기화</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chat{height:100vh;background:#f7f8fb;display:flex;flex-direction:column}
.top{display:flex;align-items:center;gap:12px;padding:13px 20px;background:#fff;border-bottom:1px solid #e6e9ef}
.home{display:flex;align-items:center;gap:6px;color:#6c7280;font-size:13px;font-weight:600}
.ti{display:flex;align-items:center;gap:9px}
.ti .av{width:30px;height:30px;border-radius:9px;background:linear-gradient(135deg,#5b8def,#7c6cf0);display:flex;align-items:center;justify-content:center}
.ti b{font-size:14px;font-weight:800}.ti small{display:block;color:#9aa0ac;font-size:11px}
.grow{flex:1}
.new{display:flex;align-items:center;gap:6px;font-size:13px;font-weight:700;color:#5c6270;border:1px solid #e6e9ef;background:#fff;border-radius:10px;padding:8px 13px;cursor:pointer;transition:.12s}
.new:hover{border-color:#cdd3df;color:#222}
.box{flex:1;overflow-y:auto;padding:26px 18px}
.col{max-width:760px;margin:0 auto;display:flex;flex-direction:column;gap:18px}
.msg{font-size:14.5px;line-height:1.65}
.msg.u{align-self:flex-end;max-width:80%;background:#4f7cf7;color:#fff;padding:11px 15px;border-radius:16px;border-bottom-right-radius:5px}
.msg.a{align-self:flex-start;display:flex;gap:11px;max-width:92%}
.msg.a .ab{width:30px;height:30px;border-radius:9px;background:linear-gradient(135deg,#5b8def,#7c6cf0);flex:none}
.msg.a .body{background:#fff;border:1px solid #e6e9ef;padding:13px 16px;border-radius:16px;border-bottom-left-radius:5px;white-space:pre-wrap}
.msg.a .ev{margin-top:10px;background:#f7f8fb;border:1px solid #e6e9ef;border-radius:11px;padding:11px 13px;font-size:11.5px;color:#7a8090}
.msg.a .ev .t{font-weight:700;color:#555;margin-bottom:6px;display:flex;align-items:center;gap:5px}
.msg.a .ev .r{padding:3px 0;border-top:1px dashed #e8eaef}
.dock{border-top:1px solid #e6e9ef;background:#fff;padding:12px 18px 14px}
.dockin{max-width:760px;margin:0 auto}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:11px}
.chips span{font-size:12.5px;border:1px solid #e6e9ef;border-radius:18px;padding:7px 13px;color:#555;cursor:pointer;background:#fff;transition:.12s}
.chips span:hover{background:#f0f4ff;border-color:#bcd0ff;color:#3a5bd0}
.in{display:flex;gap:10px}
.in input{flex:1;border:1px solid #e6e9ef;border-radius:13px;padding:13px 16px;font-size:14.5px;outline:0}
.in input:focus{border-color:#bcd0ff}
.in button{width:50px;border:0;border-radius:13px;background:#4f7cf7;color:#fff;cursor:pointer;display:flex;align-items:center;justify-content:center}
.in button:disabled{opacity:.45}
.hint{text-align:center;font-size:11px;color:#aab;margin-top:9px}
</style>
