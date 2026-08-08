<script setup>
import { ref, computed, onMounted } from 'vue'
import SideNav from '../components/SideNav.vue'
import TopBar from '../components/TopBar.vue'
import { useBoard } from '../composables/useBoard.js'
import '../assets/dashboard.css'

import StrategyTab from './tabs/StrategyTab.vue'
import ReviewTab from './tabs/ReviewTab.vue'
import ProductTab from './tabs/ProductTab.vue'
import CustomerTab from './tabs/CustomerTab.vue'
import RivalTab from './tabs/RivalTab.vue'
import MarketTab from './tabs/MarketTab.vue'
import AlertTab from './tabs/AlertTab.vue'
import DataTab from './tabs/DataTab.vue'
import SettingTab from './tabs/SettingTab.vue'

const TABS = { strategy: StrategyTab, review: ReviewTab, product: ProductTab, customer: CustomerTab,
  rival: RivalTab, market: MarketTab, alert: AlertTab, data: DataTab, setting: SettingTab }
const TAB_KEYS = Object.keys(TABS)

const { board, error, load } = useBoard()
const active = ref('strategy')
const toastMsg = ref('')

const period = computed(() => board.value?.kpi ? `${board.value.kpi.items}상품 · ${board.value.kpi.reviews}리뷰` : '')
const dsLabel = computed(() => board.value?.kpi ? `데모 데이터셋 · ${board.value.kpi.items}상품 · ${board.value.kpi.reviews}리뷰` : '데모 데이터셋')
const bellCount = computed(() => {
  if (!board.value?.aspects) return '·'
  return board.value.aspects.filter((a) => a.score <= 40).length || '·'
})
const activeComp = computed(() => TABS[active.value] || StrategyTab)

function go(v) {
  if (!TAB_KEYS.includes(v)) return
  active.value = v
  if (location.hash.slice(1) !== v) history.replaceState(null, '', '#' + v)
  window.scrollTo(0, 0)
}
let toastTimer = null
function toast(msg) {
  clearTimeout(toastTimer)   // 연달아 호출 시 이전 타이머가 새 토스트를 조기에 지우는 것 방지
  toastMsg.value = msg
  toastTimer = setTimeout(() => { toastMsg.value = '' }, 1900)
}
function downloadReport() {
  const b = board.value
  if (!b?.kpi) { toast('데이터 로딩 중입니다'); return }
  const k = b.kpi
  const L = ['ReviewLens 인사이트 리포트',
    `데이터셋: 데모 ${k.items}상품 · ${k.reviews}리뷰 · ${k.labels} 감성라벨`,
    `전체 긍정 응답률: ${k.pos_ratio}% (긍정 ${k.pos}/${k.labels})`, '', '[속성별 만족도]']
  b.aspects.forEach((x) => L.push(`- ${x.name}: ${x.score}점 (긍정 ${x.pos}/부정 ${x.neg})`))
  L.push('', '[개선 우선순위 이슈]')
  b.issues.slice(0, 5).forEach((x, i) => L.push(`${i + 1}. ${x.aspect} — 부정 ${x.count}건${x.sample ? ` ("${x.sample}")` : ''}`))
  const url = URL.createObjectURL(new Blob([L.join('\n')], { type: 'text/plain;charset=utf-8' }))
  const a = document.createElement('a')
  a.href = url; a.download = 'reviewlens_report.txt'; a.click(); URL.revokeObjectURL(url)
  toast('보고서를 다운로드했어요')
}
async function shareInsight() {
  const b = board.value
  if (!b?.kpi) { toast('데이터 로딩 중입니다'); return }
  const k = b.kpi, a = b.aspects, iss = b.issues[0]
  const top = [...a].sort((x, y) => y.score - x.score).slice(0, 2).map((x) => `${x.name} ${x.score}점`).join(', ')
  const low = [...a].sort((x, y) => x.score - y.score).slice(0, 2).map((x) => `${x.name} ${x.score}점`).join(', ')
  const txt = ['[ReviewLens 인사이트 요약]', `데모 ${k.items}상품·${k.reviews}리뷰 · 긍정 응답률 ${k.pos_ratio}%`,
    `강점: ${top}`, `개선: ${low}`, iss ? `최다 이슈: ${iss.aspect} 부정 ${iss.count}건` : '', location.href].filter(Boolean).join('\n')
  try { await navigator.clipboard.writeText(txt); toast('인사이트 요약을 복사했어요') }
  catch (e) { toast('복사 권한을 확인하세요') }
}

async function retryLoad() {
  try { await load() } catch (e) { /* error는 useBoard()의 error ref로 이미 반영됨 */ }
}

onMounted(async () => {
  const h = location.hash.slice(1)
  if (TAB_KEYS.includes(h)) active.value = h
  await retryLoad()
})
</script>

<template>
  <div class="app">
    <SideNav :active="active" :period="period" @go="go" @download="downloadReport" />
    <div class="main">
      <TopBar :ds-label="dsLabel" :bell-count="bellCount" @bell="go('alert')" @share="shareInsight" />
      <div class="wrap">
        <component v-if="board" :is="activeComp" :board="board" @go="go" />
        <div v-else-if="error" class="panel err-panel">
          <p>데이터를 불러오지 못했어요. 서버 상태를 확인한 뒤 다시 시도해주세요.</p>
          <button class="retry-btn" @click="retryLoad">다시 시도</button>
        </div>
        <div v-else class="panel">데이터를 불러오는 중…</div>
      </div>
    </div>
    <div v-if="toastMsg" class="toast">{{ toastMsg }}</div>
  </div>
</template>
