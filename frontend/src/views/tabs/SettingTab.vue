<script setup>
import { ref, onMounted } from 'vue'
import { getFeedbackStats } from '../../api.js'

defineProps({ board: Object })
const ROWS = [
  ['데이터베이스', 'SQLite (기본) · Postgres 전환 가능 (RL_DB)'],
  ['라이브 챗봇 LLM', 'gemma3:4b (Ollama, CPU)'],
  ['오프라인 요약 LLM', 'gemma4:12b (Ollama, 빌드 시 1회)'],
  ['ABSA 추출 LLM', 'qwen2.5:3b (JSON 스키마 강제)'],
  ['임베딩', 'jhgan/ko-sroberta-multitask (768d) + FAISS'],
  ['감성 분류기', '네이버쇼핑 200k linear probing (F1 0.914)'],
]

const fb = ref(null)
const fbError = ref(false)
onMounted(async () => {
  try { fb.value = await getFeedbackStats() } catch (e) { fbError.value = true }
})
</script>

<template>
  <div class="row r2">
    <div class="panel">
      <div class="phead"><h3>시스템 구성</h3></div>
      <div class="issues">
        <div v-for="(r, i) in ROWS" :key="i" class="issue">
          <span class="tx"><b>{{ r[0] }}</b><span>{{ r[1] }}</span></span>
        </div>
      </div>
    </div>
    <div class="panel">
      <div class="phead"><h3>안내</h3></div>
      <p style="font-size:13.5px;color:#6c7280;line-height:1.7">데모 환경의 구성 정보입니다. 모든 분석은 <b>로컬 CPU</b>에서 수행되며, 외부 API 비용이 들지 않습니다. 데이터셋·모델 교체는 백엔드 환경변수로 전환합니다.</p>
    </div>
  </div>

  <div class="panel" style="margin-top:20px">
    <div class="phead"><h3>챗봇 피드백</h3></div>
    <p v-if="fbError" style="font-size:13.5px;color:#c0392b">피드백 정보를 불러오지 못했어요.</p>
    <template v-else-if="fb">
      <div class="issues" style="margin-bottom:14px">
        <div class="issue">
          <span class="tx"><b>👍 도움됨</b></span>
          <span class="dl pos">{{ fb.up }}건</span>
        </div>
        <div class="issue">
          <span class="tx"><b>👎 별로예요</b></span>
          <span class="dl neg">{{ fb.down }}건</span>
        </div>
      </div>
      <p v-if="!fb.corrections.length" style="font-size:13px;color:#9aa0ac">아직 반영된 정정 문구가 없어요.</p>
      <template v-else>
        <p style="font-size:12px;color:#9aa0ac;margin-bottom:10px">사용자가 남긴 정정 — 이후 비슷한 질문에 우선 반영됩니다.</p>
        <div v-for="(c, i) in fb.corrections" :key="i" class="issue">
          <span class="tx"><b>{{ c.q }}</b><span>{{ c.correction }}</span></span>
        </div>
      </template>
    </template>
    <p v-else style="font-size:13.5px;color:#9aa0ac">불러오는 중…</p>
  </div>
</template>
