<script setup>
import { computed } from 'vue'
import { Info, ArrowRight, Headphones, Wrench, Tag, Package, Truck, Sparkles } from 'lucide-vue-next'
import SentIcon from '../../components/SentIcon.vue'
import { colr, TIPS, CARD_CLS, CARD_TAG } from '../../lib/viz.js'

const props = defineProps({ board: Object })
const emit = defineEmits(['go'])
const ICONS = { Info, Headphones, Wrench, Tag, Package, Truck, Sparkles }

const k = computed(() => props.board.kpi)
const a = computed(() => props.board.aspects)
const iss = computed(() => props.board.issues)
const q = computed(() => props.board.quotes)

const dash = computed(() => Math.round((k.value.pos_ratio / 100) * 339))
const PAL = { 전자: ['#bcd6f5', '#3a78c8'], 주방: ['#bfe9d7', '#1a9c79'], 패션: ['#f6c0cb', '#d23a5a'],
  생활: ['#f7dcae', '#c8870f'], 리빙: ['#c7ecdd', '#1a9c79'], 스포츠: ['#f7cdb8', '#cf6a3c'] }
const bubbles = computed(() => {
  const cats = props.board.categories
  const maxv = Math.max(...cats.map((c) => c.vol))
  return cats.map((c) => {
    const x = 70 + Math.min(Math.max((c.score - 55) / 40, 0), 1) * 330
    const y = 235 - (c.vol / maxv) * 185
    const r = 16 + (c.vol / maxv) * 24
    const co = PAL[c.name] || ['#dde', '#889']
    return { x: x.toFixed(0), y: y.toFixed(0), ty: (y + 4).toFixed(0), r: r.toFixed(0), c0: co[0], c1: co[1], name: c.name }
  })
})
const cards = computed(() => iss.value.slice(0, 3).map((x, i) => {
  const t = TIPS[x.aspect] || [x.aspect, '개선 검토', 'Info']
  return { cls: CARD_CLS[i], tagCls: CARD_TAG[i][0], tagLabel: CARD_TAG[i][1], title: t[0], desc: t[1], icon: ICONS[t[2]] || Info }
}))
const posQ = computed(() => q.value.pos.slice(0, 2))
const negQ = computed(() => q.value.neg.slice(0, 1))
</script>

<template>
  <section class="hero">
    <div class="label">REVIEW INSIGHT</div>
    <h1>리뷰가 가리키는<br>개선 우선순위가 보입니다.</h1>
    <p>{{ a[0].name }}·{{ a[1].name }} 만족도가 높고({{ a[0].score }}점), <b>{{ a[a.length - 1].name }}·{{ iss[0].aspect }}</b> 개선 여지가 큽니다.<br>전체 긍정 응답률은 {{ k.pos_ratio }}% 입니다.</p>
    <div class="ring"><span class="t">긍정 응답률</span><span class="v">{{ k.pos_ratio }}%</span><span class="d">긍정 {{ k.pos }} / 전체 {{ k.labels }}</span></div>
  </section>

  <section class="row r3" style="align-items:start">
    <div class="panel">
      <div class="phead"><h3>속성 감성 스냅샷</h3><span class="i"><Info :size="14" /></span></div>
      <div class="snap">
        <div style="display:flex;flex-direction:column;align-items:center;flex:none">
          <div class="gauge">
            <svg width="100%" height="100%" viewBox="0 0 128 128">
              <circle cx="64" cy="64" r="54" fill="none" stroke="#f0f1f4" stroke-width="13" />
              <circle cx="64" cy="64" r="54" fill="none" stroke="url(#g)" stroke-width="13" stroke-linecap="round" :stroke-dasharray="dash + ' 339'" transform="rotate(-90 64 64)" />
              <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#1fbf8f" /><stop offset="1" stop-color="#f5566f" /></linearGradient></defs>
            </svg>
            <div class="ctr"><span class="v">{{ k.pos_ratio }}<small>%</small></span><span class="s">긍정률</span></div>
          </div>
        </div>
        <div class="alist">
          <div v-for="x in a" :key="x.name" class="arow">
            <span class="em"><SentIcon :score="x.score" :size="21" /></span>
            <span class="nm">{{ x.name }}</span>
            <span class="tr"><i :style="{ width: Math.max(x.score, 3) + '%', background: colr(x.score) }"></i></span>
            <span class="sc">{{ x.score }}</span>
            <span class="dl" :class="x.score >= 60 ? 'pos' : 'neg'">{{ x.pos }}/{{ x.neg }}</span>
          </div>
        </div>
      </div>
    </div>

    <div class="panel">
      <div class="phead"><h3>카테고리 기회 맵</h3><span class="more" style="border:0">● 버블 크기 = 리뷰 감성 수</span></div>
      <svg class="oppmap" viewBox="0 0 440 300">
        <line x1="55" y1="20" x2="55" y2="255" stroke="#e6e8ec" /><line x1="55" y1="255" x2="420" y2="255" stroke="#e6e8ec" />
        <text x="14" y="32" font-size="11" fill="#aab">많음</text><text x="14" y="250" font-size="11" fill="#aab">적음</text>
        <text transform="rotate(-90 16 150)" x="16" y="150" font-size="11" fill="#9aa0ac">리뷰 감성량</text>
        <text x="60" y="278" font-size="11" fill="#aab">낮음</text><text x="392" y="278" font-size="11" fill="#aab">높음</text>
        <text x="208" y="278" font-size="11" fill="#9aa0ac">긍정률</text>
        <g opacity=".88">
          <template v-for="b in bubbles" :key="b.name">
            <circle :cx="b.x" :cy="b.y" :r="b.r" :fill="b.c0" />
            <text :x="b.x" :y="b.ty" font-size="12" :fill="b.c1" text-anchor="middle">{{ b.name }}</text>
          </template>
        </g>
      </svg>
    </div>

    <div class="panel">
      <div class="phead"><h3>Top 개선 이슈</h3></div>
      <div class="issues">
        <div v-for="(x, i) in iss" :key="i" class="issue">
          <span class="rk">{{ i + 1 }}</span>
          <span class="tx"><b>{{ x.sample || x.aspect + ' 관련 불만' }}</b><span>{{ x.aspect }}</span></span>
          <span class="pc">{{ x.count }}건</span>
        </div>
      </div>
    </div>
  </section>

  <section class="row r2">
    <div class="panel">
      <div class="phead"><h3>추천 전략 카드</h3></div>
      <div class="scards">
        <div v-for="(c, i) in cards" :key="i" class="scard" :class="c.cls" @click="emit('go', 'market')">
          <div class="ic"><component :is="c.icon" :size="24" /></div>
          <span class="tag" :class="c.tagCls">{{ c.tagLabel }}</span>
          <h4>{{ c.title }}</h4><p>{{ c.desc }}</p>
          <span class="go">상세 전략 <ArrowRight :size="14" /></span>
        </div>
      </div>
    </div>
    <div class="panel">
      <div class="phead"><h3>리뷰 인용 <span style="font-weight:500;color:#aab">(고객 목소리)</span></h3></div>
      <div v-for="(x, i) in posQ" :key="'p' + i" class="quote g"><span class="em"><SentIcon :score="90" :size="19" /></span><div>"{{ x.text }}"<div class="meta">— {{ x.meta }}</div></div></div>
      <div v-for="(x, i) in negQ" :key="'n' + i" class="quote n"><span class="em"><SentIcon :score="20" :size="19" /></span><div>"{{ x.text }}"<div class="meta">— {{ x.meta }}</div></div></div>
    </div>
  </section>

  <div class="foot">* 모든 수치는 데모 데이터셋({{ k.items }}상품·{{ k.reviews }}리뷰·{{ k.labels }} 감성라벨)에서 실시간 산출됩니다.</div>
</template>
