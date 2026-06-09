import { ref } from 'vue'
import { getBoard } from '../api.js'

// /api/board 를 앱 전체에서 1회만 fetch해 공유 (대시보드 모든 탭이 같은 데이터 소비)
const board = ref(null)
const error = ref(null)
let promise = null

export function useBoard() {
  function load() {
    if (!promise) {
      promise = getBoard()
        .then((b) => { board.value = b; return b })
        .catch((e) => { error.value = e; throw e })
    }
    return promise
  }
  return { board, error, load }
}
