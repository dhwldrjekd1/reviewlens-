<script setup>
import { computed } from 'vue'
import { ArrowRight, Info, Headphones, Wrench, Tag, Package, Truck, Sparkles } from 'lucide-vue-next'
import Bar from '../../components/Bar.vue'
import { TIPS, CARD_CLS, CARD_TAG } from '../../lib/viz.js'

const props = defineProps({ board: Object })
const ICONS = { Info, Headphones, Wrench, Tag, Package, Truck, Sparkles }
const iss = computed(() => props.board.issues)
const a = computed(() => props.board.aspects)
const copies = computed(() => props.board.products.filter((p) => p.copy).slice(0, 6))
const cards = computed(() => iss.value.slice(0, 3).map((x, i) => {
  const t = TIPS[x.aspect] || [x.aspect, '개선 검토', 'Info']
  return { cls: CARD_CLS[i], tagCls: CARD_TAG[i][0], tagLabel: CARD_TAG[i][1], title: t[0], desc: t[1], count: x.count, icon: ICONS[t[2]] || Info }
}))
const strong = computed(() => a.value.slice(0, 3))
const pri = computed(() => iss.value.slice(0, 4))
</script>

<template>
  <div v-if="copies.length" class="panel">
    <div class="phead"><h3>✨ AI 광고 카피 <span style="font-weight:500;color:#aab">(리뷰 강점 → 문구 자동 생성)</span></h3></div>
    <div v-for="(p, i) in copies" :key="i" class="quote g" style="border-left-color:#f0617e;flex-direction:column;gap:4px">
      <div style="font-size:12px;color:#9aa0ac"><b style="color:#2b2f38">{{ p.name }}</b> · {{ p.basis }} 강점</div>
      <div style="font-size:15.5px;font-weight:700;color:#c23258;line-height:1.5">{{ p.copy }}</div>
    </div>
  </div>

  <div class="panel">
    <div class="phead"><h3>추천 전략 (부정 이슈 기반)</h3></div>
    <div class="scards">
      <div v-for="(c, i) in cards" :key="i" class="scard" :class="c.cls">
        <div class="ic"><component :is="c.icon" :size="24" /></div>
        <span class="tag" :class="c.tagCls">{{ c.tagLabel }}</span>
        <h4>{{ c.title }}</h4><p>{{ c.desc }} (부정 {{ c.count }}건)</p>
        <span class="go">실행하기 <ArrowRight :size="14" /></span>
      </div>
    </div>
  </div>

  <div class="row r2">
    <div class="panel">
      <div class="phead"><h3>강점 속성 (셀링포인트)</h3></div>
      <div class="alist"><Bar v-for="x in strong" :key="x.name" :name="x.name" :value="x.score" suffix="점" /></div>
    </div>
    <div class="panel">
      <div class="phead"><h3>개선 우선순위</h3></div>
      <div class="issues">
        <div v-for="(x, i) in pri" :key="i" class="issue">
          <span class="rk">{{ i + 1 }}</span>
          <span class="tx"><b>{{ x.aspect }}</b><span>부정 {{ x.count }}건</span></span>
        </div>
      </div>
    </div>
  </div>
</template>
