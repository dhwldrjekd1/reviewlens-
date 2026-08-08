document.addEventListener('contextmenu', e => e.preventDefault())

import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import './assets/base.css'

import Landing from './views/Landing.vue'
import Dashboard from './views/Dashboard.vue'
import Chat from './views/Chat.vue'
import NotFound from './views/NotFound.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: Landing },
    { path: '/dashboard', component: Dashboard },
    { path: '/cs', component: Chat },
    // 등록 안 된 경로는 app.py가 SPA 폴백으로 index.html을 내려주지만, 클라이언트 라우터엔
    // 매칭되는 라우트가 없어 <router-view />가 빈 화면을 렌더링하고 있었음
    { path: '/:pathMatch(.*)*', component: NotFound },
  ],
  scrollBehavior: () => ({ top: 0 }),
})

createApp(App).use(router).mount('#app')
