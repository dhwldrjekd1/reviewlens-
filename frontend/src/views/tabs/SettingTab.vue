<script setup>
defineProps({ board: Object })
const ROWS = [
  ['데이터베이스', 'SQLite (기본) · Postgres 전환 가능 (RL_DB)'],
  ['라이브 챗봇 LLM', 'gemma3:4b (Ollama, CPU)'],
  ['오프라인 요약 LLM', 'gemma4:12b (Ollama, 빌드 시 1회)'],
  ['ABSA 추출 LLM', 'qwen2.5:3b (JSON 스키마 강제)'],
  ['임베딩', 'jhgan/ko-sroberta-multitask (768d) + FAISS'],
  ['감성 분류기', '네이버쇼핑 200k linear probing (F1 0.914)'],
]
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
</template>
