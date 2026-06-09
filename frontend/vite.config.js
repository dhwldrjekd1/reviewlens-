import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 개발: Vite 데브서버(5173)가 /api 를 FastAPI(8000)로 프록시
// 빌드: dist/ 로 산출 → FastAPI가 정적 서빙
export default defineConfig({
  plugins: [vue()],
  build: { outDir: 'dist', emptyOutDir: true },
  server: {
    proxy: { '/api': 'http://localhost:8000' },
  },
})
