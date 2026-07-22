<script setup>
import { computed } from 'vue'

const props = defineProps({ board: Object })
const alerts = computed(() => {
  const a = props.board.aspects, iss = props.board.issues
  const out = []
  a.filter((x) => x.score <= 40).forEach((x) =>
    out.push({ sym: '!', bg: '#fdecef', color: '', title: `'${x.name}' 부정 우세`, sub: `${x.name} · 긍정률 ${x.score}%`, cls: 'neg', dl: `부정 ${x.neg}건` }))
  a.filter((x) => x.score >= 85).forEach((x) =>
    out.push({ sym: '✓', bg: '#eafaf4', color: '#1a9c79', title: `'${x.name}' 만족도 우수`, sub: `${x.name} · 긍정률 ${x.score}%`, cls: 'pos', dl: `긍정 ${x.pos}건` }))
  if (iss.length) out.push({ sym: 'i', bg: '#fff5e3', color: '#d98a13', title: `최다 부정 속성: ${iss[0].aspect}`, sub: `${iss[0].aspect} · 부정 ${iss[0].count}건`, cls: '', dl: '정보' })
  return out
})
const warn = computed(() => alerts.value.filter((x) => x.cls === 'neg').length)
const good = computed(() => alerts.value.filter((x) => x.cls === 'pos').length)
</script>

<template>
  <div class="row row-16" style="align-items:start">
    <div class="panel">
      <div class="phead"><h3>속성 알림</h3></div>
      <div class="issues">
        <div v-for="(x, i) in alerts" :key="i" class="issue">
          <span class="rk" :style="{ background: x.bg, color: x.color || undefined }">{{ x.sym }}</span>
          <span class="tx"><b>{{ x.title }}</b><span>{{ x.sub }}</span></span>
          <span class="dl" :class="x.cls">{{ x.dl }}</span>
        </div>
      </div>
    </div>
    <div class="panel">
      <div class="phead"><h3>요약</h3></div>
      <div class="alist">
        <div class="arow"><span class="nm" style="width:auto">주의 필요</span><span class="tr" style="background:none"></span><span class="sc neg" style="width:auto;font-size:20px">{{ warn }}건</span></div>
        <div class="arow"><span class="nm" style="width:auto">우수</span><span class="tr" style="background:none"></span><span class="sc pos" style="width:auto;font-size:20px">{{ good }}건</span></div>
      </div>
    </div>
  </div>
</template>
