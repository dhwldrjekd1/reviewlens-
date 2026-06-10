<script setup>
import { RouterLink } from 'vue-router'
import { BarChart3, PieChart, BarChartBig, MessageSquare, LayoutGrid, ArrowRight, ShieldCheck, Lock } from 'lucide-vue-next'
</script>

<template>
  <div class="landing">
    <div class="blob b1"></div>
    <div class="blob b2"></div>
    <div class="dots"></div>

    <header class="top"><span class="ic"><BarChart3 :size="18" color="#fff" /></span><b>ReviewLens</b></header>

    <main class="wrap">
      <h1>리뷰를 읽고 분석해<br>실행으로 연결하는 <span class="hl">리뷰 인사이트 플랫폼</span></h1>
      <p class="lead">속성별 감성 분석과 직관적인 대시보드로 인사이트를 발견하고,<br>상담봇으로 고객의 목소리에 빠르게 응답하세요.</p>

      <div class="features">
        <span class="ft"><PieChart :size="17" color="#f0617e" /> 속성별 감성 분석</span>
        <i class="vd"></i>
        <span class="ft"><BarChartBig :size="17" color="#f0617e" /> 직관적인 대시보드</span>
        <i class="vd"></i>
        <span class="ft"><MessageSquare :size="17" color="#5b8def" /> 상담봇으로 즉시 응대</span>
      </div>

      <div class="cards">
        <RouterLink class="card d" to="/dashboard">
          <div class="deco">
            <svg viewBox="0 0 120 80" width="120" height="80">
              <circle cx="30" cy="34" r="20" fill="none" stroke="#f7b3c0" stroke-width="8" />
              <circle cx="30" cy="34" r="20" fill="none" stroke="#f5566f" stroke-width="8" stroke-dasharray="70 60" transform="rotate(-90 30 34)" />
              <rect x="64" y="20" width="9" height="34" rx="3" fill="#f7b3c0" />
              <rect x="80" y="10" width="9" height="44" rx="3" fill="#f5566f" />
              <rect x="96" y="30" width="9" height="24" rx="3" fill="#f7b3c0" />
            </svg>
          </div>
          <span class="badge d"><LayoutGrid :size="24" color="#fff" /></span>
          <h3>분석 대시보드</h3>
          <p>속성별 감성, 개선 이슈, 추천 전략, 인사이트 리포트를 한 화면에서 확인하세요.</p>
          <div class="tags d"><span>속성별 감성</span><span>개선 이슈</span><span>전략 추천</span><span>리포트</span></div>
          <span class="go d">대시보드 열기 <ArrowRight :size="16" /></span>
        </RouterLink>

        <RouterLink class="card c" to="/cs">
          <div class="deco">
            <svg viewBox="0 0 120 80" width="120" height="80">
              <rect x="20" y="14" width="80" height="16" rx="8" fill="#c9d6f7" />
              <rect x="40" y="34" width="60" height="16" rx="8" fill="#a9bdf2" />
              <rect x="20" y="54" width="48" height="14" rx="7" fill="#dde6fb" />
            </svg>
          </div>
          <span class="badge c"><MessageSquare :size="24" color="#fff" /></span>
          <h3>상담봇</h3>
          <p>고객 문의에 자동으로 응답하고, 필요한 정보는 빠르게 전달하세요.</p>
          <div class="tags c"><span>자동 응대</span><span>의미 검색</span><span>정보 전달</span><span>빠른 응답</span></div>
          <span class="go c">상담 시작 <ArrowRight :size="16" /></span>
        </RouterLink>
      </div>

      <div class="foot">
        <span><ShieldCheck :size="16" /> 안전한 데이터 관리</span>
        <i class="vd"></i>
        <span><Lock :size="16" /> 기업 등급 보안</span>
      </div>
    </main>
  </div>
</template>

<style scoped>
.landing{position:relative;min-height:100vh;overflow:hidden;display:flex;flex-direction:column;
  background:linear-gradient(160deg,#fff 0%,#fdf2f4 55%,#fbe9ef 100%)}
.blob{position:absolute;border-radius:50%;filter:blur(8px);opacity:.5;z-index:0}
.b1{width:420px;height:420px;left:-160px;top:60px;background:radial-gradient(circle,#fcdfe6,transparent 70%)}
.b2{width:360px;height:360px;right:-120px;bottom:-80px;background:radial-gradient(circle,#fde3d9,transparent 70%)}
.dots{position:absolute;right:48px;top:70px;width:130px;height:90px;z-index:0;opacity:.5;
  background-image:radial-gradient(#f3c3cf 1.6px,transparent 1.6px);background-size:15px 15px}
.top{position:relative;z-index:2;display:flex;align-items:center;gap:11px;padding:24px 44px}
.top .ic{width:34px;height:34px;border-radius:10px;background:linear-gradient(135deg,#f76b8a,#f99);display:flex;align-items:center;justify-content:center}
.top b{font-size:20px;font-weight:800}
.wrap{position:relative;z-index:2;flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:10px 24px 56px;text-align:center}
h1{font-size:44px;font-weight:800;line-height:1.34;color:#23262e;margin:8px 0 20px}
h1 .hl{color:#f0617e}
.lead{font-size:16px;color:#7c828f;line-height:1.75;margin-bottom:28px}
.features{display:flex;align-items:center;gap:18px;margin-bottom:46px;flex-wrap:wrap;justify-content:center}
.ft{display:flex;align-items:center;gap:8px;font-size:14.5px;font-weight:600;color:#4b5160}
.vd{width:1px;height:15px;background:#e2c9d1}
.cards{display:grid;grid-template-columns:1fr 1fr;gap:24px;width:100%;max-width:880px}
.card{position:relative;overflow:hidden;background:#fff;border:1px solid #f2e4e8;border-radius:22px;padding:32px;text-align:left;box-shadow:0 10px 34px rgba(220,120,140,.10);transition:transform .18s,box-shadow .18s;display:flex;flex-direction:column}
.card:hover{transform:translateY(-5px);box-shadow:0 18px 44px rgba(220,120,140,.16)}
.card .deco{position:absolute;right:22px;top:26px;opacity:.85}
.card .badge{width:56px;height:56px;border-radius:16px;display:flex;align-items:center;justify-content:center;margin-bottom:20px}
.badge.d{background:linear-gradient(135deg,#f5566f,#f87c7c)}
.badge.c{background:linear-gradient(135deg,#5b8def,#7c6cf0)}
.card h3{font-size:22px;font-weight:800;margin-bottom:10px;color:#23262e}
.card p{font-size:14px;color:#7c828f;line-height:1.7;flex:1;margin-bottom:18px;max-width:300px}
.tags{display:flex;flex-wrap:wrap;gap:7px;margin-bottom:22px}
.tags span{font-size:12px;font-weight:600;border-radius:8px;padding:5px 11px}
.tags.d span{background:#fdeef1;color:#d9526e}
.tags.c span{background:#eef2fd;color:#4f6fd0}
.go{align-self:flex-start;display:flex;align-items:center;gap:8px;font-weight:700;font-size:14px;border-radius:12px;padding:12px 20px;color:#fff}
.go.d{background:#f5566f}.go.c{background:#4f7cf7}
.foot{display:flex;align-items:center;gap:16px;margin-top:42px;color:#9aa0ac;font-size:13px}
.foot span{display:flex;align-items:center;gap:7px}
@media(max-width:760px){.cards{grid-template-columns:1fr}h1{font-size:30px}.card .deco{display:none}}
</style>
