document.addEventListener('contextmenu', e => e.preventDefault())

import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import './assets/base.css'

import Landing from './views/Landing.vue'
import Dashboard from './views/Dashboard.vue'
import Chat from './views/Chat.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: Landing },
    { path: '/dashboard', component: Dashboard },
    { path: '/cs', component: Chat },
  ],
  scrollBehavior: () => ({ top: 0 }),
})

createApp(App).use(router).mount('#app')
