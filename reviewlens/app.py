from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import os, json, threading
from store import db
from recommend import recommend_live
from chat import chatbot

app = FastAPI()
d = db.get_db()
HERE = os.path.dirname(__file__)
DIST = os.path.normpath(os.path.join(HERE, "..", "frontend", "dist"))  # Vue(Vite) 빌드 산출물

# Vue SPA 번들 자산(JS/CSS) 서빙. SPA 라우팅(/ ·/dashboard ·/cs)은 파일 끝 폴백이 index.html 반환.
if os.path.isdir(os.path.join(DIST, "assets")):
    app.mount("/assets", StaticFiles(directory=os.path.join(DIST, "assets")), name="assets")

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


@app.get("/api/board")
def board():  # 대시보드 전 탭이 쓰는 실데이터 집계(가공 0, 전부 55리뷰에서 산출)
    pos, tot = d.execute("select sum(sentiment='positive'), count(*) from aspect_sentiment").fetchone()
    pos = pos or 0
    kpi = {"reviews": d.execute("select count(*) from review").fetchone()[0],
           "items": d.execute("select count(*) from item").fetchone()[0],
           "labels": tot, "pos": pos, "neg": tot - pos,
           "pos_ratio": round(100 * pos / tot, 1) if tot else 0}
    # 속성별 긍/부정 + 점수(긍정률)
    asp = [{"name": a, "pos": p, "neg": g, "score": round(100 * p / (p + g)) if p + g else 0}
           for a, p, g in d.execute("select aspect, sum(sentiment='positive'), sum(sentiment='negative') "
                                    "from aspect_sentiment group by aspect")]
    asp.sort(key=lambda x: -x["score"])
    # 카테고리별(기회 맵용): 감성량(vol)·긍정률(score)
    cats = [{"name": c, "pos": p, "neg": g, "vol": p + g, "score": round(100 * p / (p + g)) if p + g else 0}
            for c, p, g in d.execute("select i.category, sum(a.sentiment='positive'), sum(a.sentiment='negative') "
                                     "from aspect_sentiment a join item i using(item_id) group by i.category")]
    cats.sort(key=lambda x: -x["vol"])
    # 상위 부정 이슈(속성별 부정 수 + 대표 근거)
    issues = []
    for a, cnt in d.execute("select aspect, count(*) from aspect_sentiment where sentiment='negative' "
                            "group by aspect order by count(*) desc"):
        ev = d.execute("select evidence from aspect_sentiment where aspect=? and sentiment='negative' "
                       "and evidence is not null and trim(evidence)!='' limit 1", (a,)).fetchone()
        issues.append({"aspect": a, "count": cnt, "sample": ev[0] if ev else ""})
    # 상품별 만족도(긍정률) — 점수순
    prods = []
    for iid, name, cat in d.execute("select item_id, name, category from item"):
        p, g = d.execute("select sum(sentiment='positive'), sum(sentiment='negative') "
                         "from aspect_sentiment where item_id=?", (iid,)).fetchone()
        p, g = p or 0, g or 0
        cp = d.execute("select copy, basis from product_copy where item_id=?", (iid,)).fetchone()
        prods.append({"name": name, "category": cat, "pos": p, "neg": g, "n": p + g,
                      "score": round(100 * p / (p + g)) if p + g else 0,
                      "copy": cp[0] if cp else "", "basis": cp[1] if cp else ""})
    prods.sort(key=lambda x: -x["score"])
    # 카테고리 평균(상품 점수 평균)
    cg = {}
    for pr in prods:
        if pr["n"]:
            cg.setdefault(pr["category"], []).append(pr["score"])
    cat_avg = sorted([{"name": c, "score": round(sum(v) / len(v))} for c, v in cg.items()],
                     key=lambda x: -x["score"])
    # 인용: 부정(부정 속성 보유 리뷰) + AI 답글 초안, 긍정(부정 0인 리뷰)
    negq = []
    for rid, t, c in d.execute(
            "select distinct r.review_id, r.raw_text, i.category from aspect_sentiment a join review r using(review_id) "
            "join item i using(item_id) where a.sentiment='negative' limit 4"):
        rep = d.execute("select reply from review_reply where review_id=?", (rid,)).fetchone()
        negq.append({"text": t, "meta": c, "reply": rep[0] if rep else ""})
    posq = [{"text": t, "meta": c} for t, c in d.execute(
        "select r.raw_text, i.category from review r join item i using(item_id) where r.review_id in "
        "(select review_id from aspect_sentiment group by review_id having sum(sentiment='negative')=0) limit 3")]
    return {"kpi": kpi, "aspects": asp, "categories": cats, "issues": issues,
            "products": prods, "cat_avg": cat_avg, "quotes": {"pos": posq, "neg": negq}}

@app.get("/api/recommend")
def rec(prefs: str = "배송,가격"):
    pr = {a: 1 for a in prefs.split(",") if a}
    return [{"name": n, "score": round(s, 2), "why": [{"aspect": a, "pos": int(p*100)} for a, p in w]}
            for s, n, w in recommend_live.recommend(d, pr)]

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
