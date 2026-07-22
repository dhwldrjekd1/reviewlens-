<script setup>
import { ref } from 'vue'
import { RouterLink } from 'vue-router'
import {
  BarChart3, LayoutDashboard, MessageSquare, Package, Users, TrendingUp,
  Megaphone, Bot, Bell, Database, Settings, Download, ArrowRight, ChevronDown, Menu, X,
} from 'lucide-vue-next'

defineProps({ active: String, period: String })
const emit = defineEmits(['go', 'download'])

const mobOpen = ref(false)

const NAV = [
  { v: 'strategy', label: '전략 보드', icon: LayoutDashboard },
  { v: 'review', label: '리뷰 분석', icon: MessageSquare },
  { v: 'product', label: '상품 분석', icon: Package },
  { v: 'customer', label: '고객 인사이트', icon: Users },
  { v: 'rival', label: '경쟁사 분석', icon: TrendingUp },
  { v: 'market', label: '마케팅 추천', icon: Megaphone },
]
const NAV2 = [
  { v: 'alert', label: '알림 센터', icon: Bell },
]
const NAV3 = [
  { v: 'data', label: '데이터 관리', icon: Database },
  { v: 'setting', label: '설정', icon: Settings },
]

function goTab(v) {
  emit('go', v)
  mobOpen.value = false
}
</script>

<template>
  <aside class="side" :class="{ 'mob-open': mobOpen }">
    <RouterLink class="logo" to="/"><span class="ic"><BarChart3 :size="16" color="#fff" /></span>ReviewLens</RouterLink>
    <button class="mob-ham" @click="mobOpen = !mobOpen">
      <X v-if="mobOpen" :size="20" />
      <Menu v-else :size="20" />
    </button>
    <nav class="nav">
      <a v-for="n in NAV" :key="n.v" :class="{ on: active === n.v }" @click="goTab(n.v)">
        <component :is="n.icon" :size="18" /> {{ n.label }}
      </a>
      <RouterLink to="/cs"><Bot :size="18" /> CS 챗봇 ↗</RouterLink>
      <a v-for="n in NAV2" :key="n.v" :class="{ on: active === n.v }" @click="goTab(n.v)">
        <component :is="n.icon" :size="18" /> {{ n.label }}
      </a>
      <div class="sep"></div>
      <a v-for="n in NAV3" :key="n.v" :class="{ on: active === n.v }" @click="goTab(n.v)">
        <component :is="n.icon" :size="18" /> {{ n.label }}
      </a>
    </nav>
    <div class="grow"></div>
    <div class="ucard"><span class="av">M</span><span class="uinfo"><small>마케팅팀</small><b>Marketing Team</b></span><span class="ch"><ChevronDown :size="16" /></span></div>
    <div class="period">데이터셋<b>{{ period || '데모 · 로딩중…' }}</b>분석 엔진<b>ABSA + 감성 분류기</b></div>
    <div class="dlbtn" @click="emit('download')"><Download :size="15" /> 보고서 다운로드 <ArrowRight :size="15" /></div>
  </aside>
</template>
