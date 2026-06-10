<script setup>
import { ref, computed } from 'vue'
import { Copy, Check } from 'lucide-vue-next'
import SentIcon from '../../components/SentIcon.vue'
import { colr } from '../../lib/viz.js'

const props = defineProps({ board: Object })
const k = computed(() => props.board.kpi)
const a = computed(() => props.board.aspects)
const q = computed(() => props.board.quotes)

const posr = computed(() => k.value.pos_ratio)
const negr = computed(() => Math.round((100 - k.value.pos_ratio) * 10) / 10)
const posArc = computed(() => Math.round(posr.value / 100 * 339))
const byMention = computed(() => [...a.value].sort((x, y) => (y.pos + y.neg) - (x.pos + x.neg)))
const maxM = computed(() => byMention.value[0].pos + byMention.value[0].neg)
const revs = computed(() => [
  ...q.value.pos.slice(0, 2).map((x) => ({ ...x, g: true })),
  ...q.value.neg.slice(0, 2).map((x) => ({ ...x, g: false })),
])
const replies = computed(() => (q.value.neg || []).filter((x) => x.reply).slice(0, 4))

const copied = ref(-1)
function copy(text, i) {
  try { navigator.clipboard.writeText(text); copied.value = i; setTimeout(() => { copied.value = -1 }, 1400) } catch (e) { /* */ }
}
</script>

<template>
  <div class="tabhead"><h2>리뷰 분석</h2><p>실제 리뷰의 감성 분포와 인사이트를 확인하세요.</p></div>
  <div class="row r3">
    <div class="panel">
      <div class="phead"><h3>감성 분포</h3></div>
      <div class="donutwrap">
        <div class="donut">
          <svg width="100%" height="100%" viewBox="0 0 140 140">
            <circle cx="70" cy="70" r="54" fill="none" stroke="#f3d0d8" stroke-width="16" />
            <circle cx="70" cy="70" r="54" fill="none" stroke="#1fbf8f" stroke-width="16" stroke-linecap="round"
              :stroke-dasharray="posArc + ' 339'" transform="rotate(-90 70 70)" />
          </svg>
          <div class="ctr"><span class="v">{{ posr }}%</span><span class="s">긍정</span></div>
        </div>
        <div class="leg">
          <div class="lrow"><span class="ld" style="background:#1fbf8f"></span><span class="ln">긍정</span><span class="lbar"><i :style="{ width: posr + '%', background: '#1fbf8f' }"></i></span><span class="lv pos">{{ posr }}%</span></div>
          <div class="lrow"><span class="ld" style="background:#ef5878"></span><span class="ln">부정</span><span class="lbar"><i :style="{ width: negr + '%', background: '#ef5878' }"></i></span><span class="lv neg">{{ negr }}%</span></div>
        </div>
      </div>
    </div>

    <div class="panel">
      <div class="phead"><h3>속성별 언급량</h3></div>
      <div class="alist">
        <div v-for="x in byMention" :key="x.name" class="arow">
          <span class="nm">{{ x.name }}</span>
          <span class="tr"><i :style="{ width: Math.round((x.pos + x.neg) / maxM * 100) + '%', background: colr(x.score) }"></i></span>
          <span class="sc">{{ x.pos + x.neg }}건</span>
        </div>
      </div>
    </div>

    <div class="panel">
      <div class="phead"><h3>대표 리뷰</h3></div>
      <div v-for="(x, i) in revs" :key="i" class="quote" :class="x.g ? 'g' : 'n'">
        <span class="em"><SentIcon :score="x.g ? 90 : 20" :size="19" /></span>
        <div>"{{ x.text }}"<div class="meta">{{ x.meta }}</div></div>
      </div>
    </div>
  </div>

  <div v-if="replies.length" class="panel" style="margin-top:20px">
    <div class="phead"><h3>리뷰 응대 가이드 <span style="font-weight:500;color:#aab">(부정 리뷰 추천 답변)</span></h3></div>
    <div class="guide">
      <div v-for="(x, i) in replies" :key="i" class="grow">
        <div class="gq">
          <span class="badge neg">부정 리뷰</span>
          <p>"{{ x.text }}"</p>
        </div>
        <div class="gr">
          <button class="cp" :title="copied === i ? '복사됨' : '복사'" @click="copy(x.reply, i)">
            <component :is="copied === i ? Check : Copy" :size="15" />
          </button>
          <span class="badge rec">권장 답변</span>
          <p>{{ x.reply }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.donutwrap{display:flex;flex-direction:column;align-items:center;gap:18px;padding:6px 0}
.donut{position:relative;width:150px;height:150px}
.donut .ctr{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center}
.donut .ctr .v{font-size:27px;font-weight:800;color:#2b2f38}
.donut .ctr .s{font-size:13px;color:#1fbf8f;font-weight:700;margin-top:2px}
.leg{width:100%;display:flex;flex-direction:column;gap:12px;padding:0 4px}
.lrow{display:flex;align-items:center;gap:10px;font-size:14px}
.ld{width:9px;height:9px;border-radius:50%;flex:none}
.ln{width:34px;color:#555;font-weight:600}
.lbar{flex:1;height:7px;background:#f0f1f4;border-radius:5px;overflow:hidden}
.lbar i{display:block;height:100%;border-radius:5px}
.lv{width:48px;text-align:right;font-weight:800}
.guide{display:flex;flex-direction:column;gap:14px}
.grow{display:grid;grid-template-columns:1fr 1.3fr;gap:14px;align-items:stretch}
.gq{background:#fff7ec;border:1px solid #f6e6cf;border-radius:13px;padding:14px 16px}
.gr{position:relative;background:#fff;border:1px solid #eef0f3;border-radius:13px;padding:14px 16px}
.badge{display:inline-block;font-size:11.5px;font-weight:800;border-radius:7px;padding:3px 9px;margin-bottom:8px}
.badge.neg{background:#fdecef;color:#ef4f6d}
.badge.rec{background:#eaf1ff;color:#4f7cf7}
.grow p{font-size:13.5px;line-height:1.65;color:#555;margin:0}
.gq p{color:#7a6a4a}
.cp{position:absolute;top:12px;right:12px;width:28px;height:28px;border:1px solid #eef0f3;background:#fff;border-radius:8px;color:#aab;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:.12s}
.cp:hover{border-color:#bcd0ff;color:#4f7cf7}
@media(max-width:760px){.grow{grid-template-columns:1fr}}
</style>
