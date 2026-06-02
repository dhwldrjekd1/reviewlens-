import json, urllib.request
import db, recommend, retriever

ASPECTS = ["배송", "품질", "가격", "포장", "디자인", "CS"]


# 검색된 리뷰를 근거 텍스트로 (원문 + 속성 감성 라벨)
def _review_ctx(d, hits):
    lines = []
    for h in hits:
        labs = d.execute("select aspect, sentiment from aspect_sentiment where review_id=?",
                         (h["review_id"],)).fetchall()
        tag = " ".join(f"{a}/{s}" for a, s in labs)
        lines.append(f"- ({h['name']}) {h['text']}" + (f"  [{tag}]" if tag else ""))
    return "\n".join(lines)


# 질문에서 근거를 꺼냄: 추천 의도면 추천, 아니면 의미검색(ko-sroberta+FAISS)으로 근거 리뷰
def ground(d, q):
    if "추천" in q:  # 추천 의도 → 중시 속성으로 추천
        asp = [a for a in ASPECTS if a in q]
        recs = recommend.recommend(d, {a: 1 for a in asp} or {"품질": 1})
        return "\n".join(f"- {n}: " + ", ".join(f"{a} {int(p*100)}%" for a, p in why)
                         for _, n, why in recs)
    hits = retriever.search(d, q, k=3)  # 의미가 가까운 리뷰 Top-K (키워드 불일치도 검색)
    return _review_ctx(d, hits)


PROMPT = """너는 쇼핑 리뷰 분석 도우미야. 아래 '근거'에만 기반해 한국어로 간결히 답해. 근거에 없는 내용은 지어내지 마.

질문: {q}
근거:
{ctx}

답변:"""


def ask(d, q):
    ctx = ground(d, q)
    if not ctx:
        return "관련 데이터를 못 찾았어요.", ""
    try:
        body = json.dumps({"model": "qwen2.5:3b", "stream": False, "options": {"temperature": 0},
                           "prompt": PROMPT.format(q=q, ctx=ctx)}).encode()
        req = urllib.request.Request("http://localhost:11434/api/generate", body,
                                     {"Content-Type": "application/json"})
        ans = json.loads(urllib.request.urlopen(req, timeout=180).read())["response"].strip()
        return ans, ctx
    except Exception as e:
        # 의미검색은 LLM 없이도 동작 → Ollama 미가동/모델 미설치여도 근거는 반환
        return f"(LLM 응답 생성을 건너뜀: {e})\n검색된 근거 리뷰:\n{ctx}", ctx


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    d = db.get_db()
    for q in ["이어폰 소리 어때?", "물건 늦게 오는 편이야?", "배송 빠른 거 추천해줘"]:
        ans, ctx = ask(d, q)
        print(f"\nQ: {q}")
        print(f"[근거]\n{ctx}")
        print(f"A: {ans}")
