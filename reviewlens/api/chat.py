import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from chat import chatbot
from api.deps import d

# 챗봇 API (질의·스트리밍·피드백)
router = APIRouter(prefix="/api", tags=["chat"])


class Q(BaseModel):
    # 길이 제한 없이 매우 긴 문자열이 그대로 임베딩 계산·LLM 프롬프트에 들어가면
    # 응답 지연·리소스 낭비로 이어질 수 있어 상한을 둠(자연어 질문엔 충분히 넉넉한 길이)
    q: str = Field(min_length=1, max_length=500)


class FB(BaseModel):
    # Q와 같은 이유로 상한을 둠 — 인증 없이 누구나 호출 가능한 엔드포인트라 제한이 없으면
    # DB가 무한정 커지고, correction은 매 챗봇 질문마다 recall_corrections()가 전체를
    # 다시 임베딩하는 구조라(chat/chatbot.py) 거대한 값 하나가 이후 모든 응답을 느리게 만듦
    q: str = Field(max_length=500)
    answer: str = Field(default="", max_length=4000)
    vote: str = Field(default="", max_length=10)           # up | down
    correction: str = Field(default="", max_length=1000)   # 사용자 정정 (선택)


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


# 지금까지 쌓인 👍/👎 집계 + 실제 반영된(정정 문구 있는) 최근 교정 목록 — 설정 탭에서 조회용
@router.get("/feedback/stats")
def feedback_stats():
    up = down = 0
    for vote, c in d.execute("select vote, count(*) from feedback group by vote").fetchall():
        if vote == "up":
            up = c
        elif vote == "down":
            down = c
    rows = d.execute(
        "select question, correction, created from feedback "
        "where correction is not null and trim(correction)!='' "
        "order by created desc limit 20"
    ).fetchall()
    return {
        "up": up, "down": down,
        "corrections": [{"q": q, "correction": c, "created": t} for q, c, t in rows],
    }
