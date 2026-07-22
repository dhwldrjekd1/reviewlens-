<script setup>
import { computed } from 'vue'
import { colr } from '../../lib/viz.js'

const props = defineProps({ board: Object })
const a = computed(() => props.board.aspects)
const base = computed(() => Math.round(props.board.kpi.pos_ratio))
const rows = computed(() => a.value.map((x) => {
  const d = x.score - base.value
  return { ...x, cls: d > 0 ? 'pos' : d < 0 ? 'neg' : 'neu' }
}))
const up = computed(() => a.value.filter((x) => x.score > base.value).length)
const dn = computed(() => a.value.filter((x) => x.score < base.value).length)
</script>

<template>
  <div class="row row-15" style="align-items:start">
    <div class="panel">
      <div class="phead"><h3>속성별 벤치마크</h3><span class="more" style="border:0">속성 점수 vs 전체 평균({{ base }})</span></div>
      <div class="alist">
        <div v-for="x in rows" :key="x.name" class="arow">
          <span class="nm">{{ x.name }}</span>
          <span class="tr"><i :style="{ width: Math.max(x.score, 3) + '%', background: colr(x.score) }"></i></span>
          <span class="sc" :class="x.cls">{{ x.score }} vs {{ base }}</span>
        </div>
      </div>
    </div>
    <div class="panel">
      <div class="phead"><h3>종합</h3></div>
      <div class="alist">
        <div class="arow"><span class="nm" style="width:auto">평균 상회</span><span class="tr" style="background:none"></span><span class="sc pos" style="width:auto;font-size:20px">{{ up }}개</span></div>
        <div class="arow"><span class="nm" style="width:auto">평균 하회</span><span class="tr" style="background:none"></span><span class="sc neg" style="width:auto;font-size:20px">{{ dn }}개</span></div>
        <p style="font-size:13px;color:#6c7280;line-height:1.6;margin-top:8px;border-top:1px solid var(--line);padding-top:12px">* 외부 경쟁사 데이터가 없어, 자사 속성을 <b>전체 평균 대비</b> 벤치마크로 표시합니다(데모).</p>
      </div>
    </div>
  </div>
</template>
