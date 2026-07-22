<script setup>
import { computed } from 'vue'
import Bar from '../../components/Bar.vue'
import { colr } from '../../lib/viz.js'

const props = defineProps({ board: Object })
const products = computed(() => props.board.products)
const catAvg = computed(() => props.board.cat_avg)
</script>

<template>
  <div class="row row-15" style="align-items:start">
    <div class="panel">
      <div class="phead"><h3>상품별 만족도</h3><span class="more">{{ products.length }}개 상품</span></div>
      <div class="alist">
        <div v-for="(x, i) in products" :key="i" class="arow">
          <span class="rk" style="width:18px;height:18px;border-radius:50%;background:#fdecef;color:#ef4f6d;font-size:12px;font-weight:800;display:flex;align-items:center;justify-content:center;flex:none">{{ i + 1 }}</span>
          <span class="nm" style="width:140px">{{ x.name }}</span>
          <span class="tr"><i :style="{ width: Math.max(x.score, 3) + '%', background: colr(x.score) }"></i></span>
          <span class="sc">{{ x.score }}점</span>
        </div>
      </div>
    </div>
    <div class="panel">
      <div class="phead"><h3>카테고리 평균</h3></div>
      <div class="alist">
        <Bar v-for="x in catAvg" :key="x.name" :name="x.name" :value="x.score" suffix="점" />
      </div>
    </div>
  </div>
</template>
