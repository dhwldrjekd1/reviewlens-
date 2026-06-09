<script setup>
import { computed } from 'vue'
import SentIcon from '../../components/SentIcon.vue'
import { colr } from '../../lib/viz.js'

const props = defineProps({ board: Object })
const k = computed(() => props.board.kpi)
const a = computed(() => props.board.aspects)
const q = computed(() => props.board.quotes)

const posr = computed(() => k.value.pos_ratio)
const negr = computed(() => Math.round(100 - k.value.pos_ratio))
const byMention = computed(() => [...a.value].sort((x, y) => (y.pos + y.neg) - (x.pos + x.neg)))
const maxM = computed(() => byMention.value[0].pos + byMention.value[0].neg)
const revs = computed(() => [
  ...q.value.pos.slice(0, 2).map((x) => ({ ...x, g: true })),
  ...q.value.neg.slice(0, 2).map((x) => ({ ...x, g: false })),
])
const replies = computed(() => (q.value.neg || []).filter((x) => x.reply).slice(0, 4))
</script>

<template>
  <div class="row r3">
    <div class="panel">
      <div class="phead"><h3>감성 분포</h3></div>
      <div class="alist">
        <div class="arow"><span class="nm">긍정</span><span class="tr"><i :style="{ width: posr + '%', background: '#1fbf8f' }"></i></span><span class="sc pos">{{ posr }}%</span></div>
        <div class="arow"><span class="nm">부정</span><span class="tr"><i :style="{ width: negr + '%', background: '#ef5878' }"></i></span><span class="sc neg">{{ negr }}%</span></div>
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
    <div class="phead"><h3>💬 AI 리뷰 답글 <span style="font-weight:500;color:#aab">(부정 리뷰 자동 대응 초안)</span></h3></div>
    <div v-for="(x, i) in replies" :key="i" class="quote n" style="flex-direction:column;align-items:stretch;gap:7px">
      <div style="display:flex;gap:9px">
        <span class="em"><SentIcon :score="20" :size="19" /></span>
        <div>"{{ x.text }}"<span style="font-size:12px;color:#aab"> · {{ x.meta }}</span></div>
      </div>
      <div style="background:#fff;border:1px solid var(--line);border-radius:9px;padding:9px 12px;font-size:13.5px;color:#444;margin-left:28px">
        <b style="color:#4f7cf7">💬 AI 답글</b><br>{{ x.reply }}
      </div>
    </div>
  </div>
</template>
