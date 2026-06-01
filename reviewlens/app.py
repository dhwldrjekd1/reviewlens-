from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import os, db, recommend, chatbot

app = FastAPI()
d = db.get_db()
HERE = os.path.dirname(__file__)

@app.get("/", response_class=HTMLResponse)
def home():
    return open(os.path.join(HERE, "dashboard.html"), encoding="utf-8").read()

@app.get("/api/summary")
def summary():
    return [{"name": n, "aspect": a, "pos": p, "neg": g} for n, a, p, g in db.summary(d)]

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
