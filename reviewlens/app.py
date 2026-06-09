import os, threading
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from store import db
from chat import chatbot
from api import board, chat as chat_api

app = FastAPI()
HERE = os.path.dirname(__file__)
DIST = os.path.normpath(os.path.join(HERE, "..", "frontend", "dist"))  # Vue(Vite) 빌드 산출물

# Vue SPA 번들 자산(JS/CSS) 서빙. SPA 라우팅(/ ·/dashboard ·/cs)은 파일 끝 폴백이 index.html 반환.
if os.path.isdir(os.path.join(DIST, "assets")):
    app.mount("/assets", StaticFiles(directory=os.path.join(DIST, "assets")), name="assets")

# 도메인별 API 라우터 — board(분석/대시보드), chat(챗봇)
app.include_router(board.router)
app.include_router(chat_api.router)


# 자주 묻는 질문(빠른칩)을 시작 시 백그라운드로 미리 생성 → 캐시 적재 → 첫 클릭부터 즉시 응답
_WARMUP = ["배송 빠른 편인가요?", "이어폰 소리 어때요?", "포장 상태 괜찮나요?", "가성비 좋은 거 추천해줘"]


def _prewarm():
    wd = db.get_db()                      # 워밍 전용 커넥션(스레드 안전)
    for q in _WARMUP:
        try:
            for _ in chatbot.ask_stream(wd, q):
                pass
        except Exception:
            pass


threading.Thread(target=_prewarm, daemon=True).start()


# SPA 폴백 — /api·/assets 외 모든 GET 경로는 Vue 앱(index.html) 반환, 클라이언트 라우터가 처리.
# (모든 API 라우트보다 뒤에 정의되어야 가로채지 않음)
@app.get("/{full_path:path}", response_class=HTMLResponse)
def spa(full_path: str):
    index = os.path.join(DIST, "index.html")
    if os.path.exists(index):
        return HTMLResponse(open(index, encoding="utf-8").read())
    return HTMLResponse("<h1>프런트엔드 빌드가 없습니다 — frontend/에서 <code>npm run build</code> 후 서버 재시작</h1>",
                        status_code=503)
