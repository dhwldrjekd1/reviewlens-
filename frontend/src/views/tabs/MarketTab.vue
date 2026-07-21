<script setup>
import { computed } from 'vue'
import { ArrowRight, Info, Quote, Headphones, Wrench, Tag, Package, Truck, Sparkles } from 'lucide-vue-next'
import Bar from '../../components/Bar.vue'
import { TIPS, CARD_CLS, CARD_TAG } from '../../lib/viz.js'

const props = defineProps({ board: Object })
const emit = defineEmits(['go'])
const ICONS = { Info, Headphones, Wrench, Tag, Package, Truck, Sparkles }
const iss = computed(() => props.board.issues)
const a = computed(() => props.board.aspects)
const copies = computed(() => props.board.products.filter((p) => p.copy).slice(0, 6).map((p) => {
  const tags = (p.basis || '').split(/[·,]/).map((t) => t.trim()).filter(Boolean).slice(0, 2)
  const bang = p.copy.indexOf('!')
  const head = bang >= 0 ? p.copy.slice(0, bang + 1) : p.copy
  const tail = bang >= 0 ? p.copy.slice(bang + 1).trim() : ''
  return { name: p.name, tags, head, tail }
}))
const cards = computed(() => iss.value.slice(0, 3).map((x, i) => {
  const t = TIPS[x.aspect] || [x.aspect, '개선 검토', 'Info']
  return { cls: CARD_CLS[i], tagCls: CARD_TAG[i][0], tagLabel: CARD_TAG[i][1], title: t[0], desc: t[1], count: x.count, icon: ICONS[t[2]] || Info }
}))
const strong = computed(() => a.value.slice(0, 3))
const pri = computed(() => iss.value.slice(0, 4))
</script>

<template>
  <div class="tabhead"><h2>마케팅 추천</h2><p>리뷰에서 발견한 고객의 언어로 더 설득력 있는 메시지를 만들어보세요.</p></div>

  <div v-if="copies.length" class="panel">
    <div class="phead"><h3>리뷰 기반 카피 추천</h3></div>
    <p class="psub">실제 리뷰에서 추출한 고객 표현을 바탕으로 한 마케팅 메시지 제안입니다.</p>
    <div class="copies">
      <div v-for="(p, i) in copies" :key="i" class="crow">
        <span class="cic"><Quote :size="14" color="#fff" /></span>
        <span class="cname">{{ p.name }}</span>
        <span class="ctags"><span v-for="t in p.tags" :key="t">{{ t }}</span></span>
        <span class="ctext">{{ p.head }}<b v-if="p.tail"> {{ p.tail }}</b></span>
      </div>
    </div>
  </div>

  <div class="panel">
    <div class="phead"><h3>추천 전략 (부정 이슈 기반)</h3></div>
    <div class="scards">
      <div v-for="(c, i) in cards" :key="i" class="scard" :class="c.cls" @click="emit('go', 'review')">
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

<style scoped>
.psub{font-size:13px;color:#9aa0ac;margin:-8px 0 16px}
.copies{display:flex;flex-direction:column}
.crow{display:flex;align-items:center;gap:12px;padding:13px 6px;border-bottom:1px solid #f3f4f7;font-size:14px}
.crow:last-child{border:0}
.cic{width:26px;height:26px;border-radius:50%;background:linear-gradient(135deg,#f76b8a,#f99);display:flex;align-items:center;justify-content:center;flex:none}
.cname{font-weight:700;color:#2b2f38;width:130px;flex:none;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ctags{display:flex;gap:5px;flex:none}
.ctags span{font-size:11px;color:#8a90a0;background:#f2f3f6;border-radius:6px;padding:3px 8px;white-space:nowrap}
.ctext{flex:1;color:#3a3f48;line-height:1.5}
.ctext b{color:#e0517a;font-weight:700}
@media(max-width:900px){.crow{flex-wrap:wrap}.cname{width:auto}.ctext{flex-basis:100%}}
@media(max-width:540px){
  .crow{gap:8px;padding:11px 4px;font-size:13px}
  .ctags{flex-wrap:wrap}
}
</style>
