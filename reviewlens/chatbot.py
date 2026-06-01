import json, urllib.request
import db, recommend

ASPECTS = ["배송", "품질", "가격", "포장", "디자인", "CS"]

# 질문에서 근거 데이터를 꺼냄 (상품 질문이면 그 상품 근거, 아니면 추천)
def ground(d, q):
    asp = [a for a in ASPECTS if a in q]
    items = [(iid, name) for iid, name in d.execute("select item_id, name from item")
             if any(w in q for w in name.split())]
    if items:  # 특정 상품 질문 → 그 상품 속성 감성 근거
        iid, name = items[0]
        rows = d.execute("select aspect,sentiment,evidence from aspect_sentiment where item_id=?", (iid,)).fetchall()
        return "\n".join(f"- [{a}/{s}] {e}" for a, s, e in rows)
    if asp or "추천" in q:  # 추천 의도 → 중시 속성으로 추천
        recs = recommend.recommend(d, {a: 1 for a in asp} or {"품질": 1})
        return "\n".join(f"- {n}: " + ", ".join(f"{a} {int(p*100)}%" for a, p in why)
                         for _, n, why in recs)
    return ""

PROMPT = """너는 쇼핑 리뷰 분석 도우미야. 아래 '근거'에만 기반해 한국어로 간결히 답해. 근거에 없는 내용은 지어내지 마.

질문: {q}
근거:
{ctx}

답변:"""

def ask(d, q):
    ctx = ground(d, q)
    if not ctx:
        return "관련 데이터를 못 찾았어요.", ""
    body = json.dumps({"model": "qwen2.5:3b", "stream": False, "options": {"temperature": 0},
                       "prompt": PROMPT.format(q=q, ctx=ctx)}).encode()
    req = urllib.request.Request("http://localhost:11434/api/generate", body, {"Content-Type": "application/json"})
    ans = json.loads(urllib.request.urlopen(req, timeout=180).read())["response"].strip()
    return ans, ctx

if __name__ == "__main__":
    d = db.get_db()
    for q in ["배송 빠르고 평 좋은 거 추천해줘", "스텐 텀블러 품질이랑 포장 어때?"]:
        ans, ctx = ask(d, q)
        print(f"\nQ: {q}")
        print(f"[근거]\n{ctx}")
        print(f"A: {ans}")
