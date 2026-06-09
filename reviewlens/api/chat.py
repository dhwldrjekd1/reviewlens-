import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from chat import chatbot
from api.deps import d

# 챗봇 API (질의·스트리밍·피드백)
router = APIRouter(prefix="/api", tags=["chat"])


class Q(BaseModel):
    q: str


class FB(BaseModel):
    q: str
    answer: str = ""
    vote: str = ""          # up | down
    correction: str = ""    # 사용자 정정 (선택)


@router.post("/chat")
def chat(body: Q):
    ans, ctx = chatbot.ask(d, body.q)
    return {"answer": ans, "evidence": ctx}


@router.post("/chat/stream")
def chat_stream(body: Q):  # 토큰 스트리밍(NDJSON) — 체감 속도↑
    def gen():
        for obj in chatbot.ask_stream(d, body.q):
            yield json.dumps(obj, ensure_ascii=False) + "\n"
    return StreamingResponse(gen(), media_type="application/x-ndjson")


@router.post("/feedback")
def feedback(body: FB):
    chatbot.record_feedback(d, body.q, body.answer, body.vote, body.correction)
    return {"ok": True}
