<script setup>
import { computed } from 'vue'
import Bar from '../../components/Bar.vue'
import { colr } from '../../lib/viz.js'

const props = defineProps({ board: Object })
const a = computed(() => props.board.aspects)
const tot = computed(() => a.value.reduce((s, x) => s + x.pos + x.neg, 0))
const interest = computed(() => [...a.value].sort((x, y) => (y.pos + y.neg) - (x.pos + x.neg))
  .map((x) => ({ name: x.name, value: Math.round((x.pos + x.neg) / tot.value * 100) })))
</script>

<template>
  <div class="row r2">
    <div class="panel">
      <div class="phead"><h3>고객 관심 속성 (언급 비중)</h3></div>
      <div class="alist">
        <Bar v-for="x in interest" :key="x.name" :name="x.name" :value="x.value" suffix="%" />
      </div>
    </div>
    <div class="panel">
      <div class="phead"><h3>속성별 만족도</h3></div>
      <div class="alist">
        <div v-for="x in a" :key="x.name" class="arow">
          <span class="nm">{{ x.name }}</span>
          <span class="tr"><i :style="{ width: Math.max(x.score, 3) + '%', background: colr(x.score) }"></i></span>
          <span class="sc" :class="x.score >= 60 ? 'pos' : 'neg'">{{ x.score }}%</span>
        </div>
      </div>
    </div>
  </div>
  <div class="foot">* 연령·성별 등 인구통계는 데모 데이터에 없어, 리뷰에서 실제 산출 가능한 '관심 속성'으로 대체했습니다.</div>
</template>
