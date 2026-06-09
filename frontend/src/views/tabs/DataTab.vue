<script setup>
import { computed } from 'vue'
const props = defineProps({ board: Object })
const k = computed(() => props.board.kpi)
</script>

<template>
  <div class="row" style="grid-template-columns:1.6fr 1fr;align-items:start">
    <div class="panel">
      <div class="phead"><h3>데이터 소스</h3></div>
      <div class="issues">
        <div class="issue"><span class="tx"><b><span class="dot" style="background:#1fbf8f"></span>데모 리뷰셋 (data/reviews.csv)</b><span>{{ k.items }}개 상품 · {{ k.reviews }}개 리뷰</span></span><span class="pc pos">로드됨</span></div>
        <div class="issue"><span class="tx"><b><span class="dot" style="background:#1fbf8f"></span>네이버쇼핑 200k</b><span>감성 분류기 학습(linear probing)</span></span><span class="pc pos">학습완료</span></div>
        <div class="issue"><span class="tx"><b><span class="dot" style="background:#f5a623"></span>국립국어원 ABSA 말뭉치</b><span>라이선스 · 로컬 전용</span></span><span class="pc neu">비공개</span></div>
      </div>
    </div>
    <div class="panel">
      <div class="phead"><h3>수집 현황</h3></div>
      <div class="alist">
        <div class="arow"><span class="nm" style="width:auto">상품</span><span class="tr" style="background:none"></span><span class="sc" style="width:auto;font-size:20px">{{ k.items }}</span></div>
        <div class="arow"><span class="nm" style="width:auto">리뷰</span><span class="tr" style="background:none"></span><span class="sc" style="width:auto;font-size:20px">{{ k.reviews }}</span></div>
        <div class="arow"><span class="nm" style="width:auto">감성 라벨</span><span class="tr" style="background:none"></span><span class="sc pos" style="width:auto;font-size:20px">{{ k.labels }}</span></div>
      </div>
    </div>
  </div>
</template>
