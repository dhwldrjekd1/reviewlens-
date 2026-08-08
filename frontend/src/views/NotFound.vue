<script setup>
import { RouterLink } from 'vue-router'
</script>

<template>
  <div class="notfound">
    <h1>404</h1>
    <p>요청하신 페이지를 찾을 수 없어요.</p>
    <RouterLink class="home" to="/">홈으로 돌아가기</RouterLink>
  </div>
</template>

<style scoped>
.notfound{min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;text-align:center;color:#333}
.notfound h1{font-size:56px;margin:0;color:#f0617e}
.notfound p{margin:0;color:#666}
.notfound .home{margin-top:10px;color:#f0617e;font-weight:600;text-decoration:none}
.notfound .home:hover{text-decoration:underline}
</style>
