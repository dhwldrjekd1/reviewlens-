<script setup>
import { Database, Bell, Share2 } from 'lucide-vue-next'
defineProps({ dsLabel: String, bellCount: [String, Number] })
const emit = defineEmits(['bell', 'share'])
</script>

<template>
  <header class="top">
    <div class="pill"><Database :size="15" /> <span>{{ dsLabel || '데모 데이터셋' }}</span></div>
    <div class="pill">카테고리 전체</div>
    <div class="grow"></div>
    <div class="bell" @click="emit('bell')"><Bell :size="19" /><span class="b">{{ bellCount || '·' }}</span></div>
    <button class="share" @click="emit('share')"><Share2 :size="15" /> 인사이트 요약 공유</button>
  </header>
</template>
