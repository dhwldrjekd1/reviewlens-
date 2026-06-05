from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import os, json, db, recommend, chatbot

app = FastAPI()
d = db.get_db()
HERE = os.path.dirname(__file__)
# 대시보드 정적 파일(css)·탭 partial 제공 — 가벼운 정적 서빙(새 의존성 없음)
app.mount("/static", StaticFiles(directory=os.path.join(HERE, "static")), name="static")
app.mount("/tabs", StaticFiles(directory=os.path.join(HERE, "tabs")), name="tabs")

def _page(name):  # no-store: 수정이 새로고침에 바로 반영되게
    html = open(os.path.join(HERE, name), encoding="utf-8").read()
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})

@app.get("/", response_class=HTMLResponse)
def home():
    return _page("index.html")            # 랜딩(두 제품 진입)

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    return _page("dashboard.html")         # 분석 대시보드

@app.get("/cs", response_class=HTMLResponse)
def cs():
    return _page("cs.html")                # CS 챗봇 (독립)

@app.get("/api/summary")
def summary():
    return [{"name": n, "aspect": a, "pos": p, "neg": g} for n, a, p, g in db.summary(d)]

@app.get("/api/stats")
def stats():  # 대시보드 KPI용 실데이터 집계
    n_rev = d.execute("select count(*) from review").fetchone()[0]
    n_item = d.execute("select count(*) from item").fetchone()[0]
    pos, tot = d.execute("select sum(sentiment='positive'), count(*) from aspect_sentiment").fetchone()
    neg = d.execute("select count(*) from aspect_sentiment where sentiment='negative'").fetchone()[0]
    return {"reviews": n_rev, "items": n_item,
            "pos_ratio": round(100 * pos / tot, 1) if tot else 0, "neg": neg}

@app.get("/api/recommend")
def rec(prefs: str = "배송,가격"):
    pr = {a: 1 for a in prefs.split(",") if a}
    return [{"name": n, "score": round(s, 2), "why": [{"aspect": a, "pos": int(p*100)} for a, p in w]}
            for s, n, w in recommend.recommend(d, pr)]

class Q(BaseModel):
    q: str

@app.post("/api/chat")
def chat(body: Q):
    ans, ctx = chatbot.ask(d, body.q)
    return {"answer": ans, "evidence": ctx}

@app.post("/api/chat/stream")
def chat_stream(body: Q):  # 토큰 스트리밍(NDJSON) — 체감 속도↑
    def gen():
        for obj in chatbot.ask_stream(d, body.q):
            yield json.dumps(obj, ensure_ascii=False) + "\n"
    return StreamingResponse(gen(), media_type="application/x-ndjson")

class FB(BaseModel):
    q: str
    answer: str = ""
    vote: str = ""          # up | down
    correction: str = ""    # 사용자 정정 (선택)

@app.post("/api/feedback")
def feedback(body: FB):
    chatbot.record_feedback(d, body.q, body.answer, body.vote, body.correction)
    return {"ok": True}
