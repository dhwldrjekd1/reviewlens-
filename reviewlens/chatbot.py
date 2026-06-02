import json, re, urllib.request
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


PROMPT = """너는 한국 쇼핑몰의 리뷰 분석 도우미야. 아래 '근거'에만 기반해 답해.

규칙:
- 반드시 자연스럽고 문법에 맞는 한국어로만 답한다. 한자나 영어 단어를 절대 섞지 않는다.
- 근거에 없는 내용은 지어내지 않는다.
- 1~3문장으로 간결하게.

질문: {q}
근거:
{ctx}

답변(한국어):"""


# --- 한자/불필요 영어 탐지 (삭제하지 않고, 깨끗할 때까지 재생성하기 위한 판정) ---
# 한자는 코드포인트로 판정 (리터럴 한자 범위를 쓰면 한글 AC00–D7A3까지 삼킬 위험)
def _has_hanja(s):
    return any(0x3400 <= ord(c) <= 0x9fff or 0xf900 <= ord(c) <= 0xfaff for c in s)


def _bad_lang(s):
    if _has_hanja(s):              # 한자
        return True
    for tok in s.split():          # 토큰 단위로 영어 검사
        if not re.search(r"[A-Za-z]", tok):
            continue
        if re.search(r"[가-힣]", tok):                 # 한글+영어 혼합 단어 (괜shaw)
            return True
        bare = tok.strip(".,!?()[]\"'·").upper()
        if bare == "CS":                               # 허용: 속성명 CS
            continue
        if re.search(r"\d", tok):                       # 허용: 500ml, X10 등 숫자 결합
            continue
        return True                                     # 그 외 순수 영어 단어 (good 등)
    return False


def _generate(prompt, temp=0.0, seed=0):
    opts = {"temperature": temp}
    if seed:
        opts["seed"] = seed
    body = json.dumps({"model": "qwen2.5:3b", "stream": False,
                       "prompt": prompt, "options": opts}).encode()
    req = urllib.request.Request("http://localhost:11434/api/generate", body,
                                 {"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=180).read())["response"].strip()


def ask(d, q):
    ctx = ground(d, q)
    if not ctx:
        return "관련 데이터를 못 찾았어요.", ""
    try:
        ans = _generate(PROMPT.format(q=q, ctx=ctx))            # 1차: 결정적(temp 0)
        tries = 0
        # 한자/영어 섞이면 '삭제'가 아니라 '재생성'(샘플링, seed 변경)으로 깨끗한 문장 확보
        while _bad_lang(ans) and tries < 3:
            tries += 1
            ans = _generate(PROMPT.format(q=q, ctx=ctx) +
                            "\n\n주의: 한자나 영어를 섞지 말고 한국어 문장으로만 다시 답하라.",
                            temp=0.6, seed=tries)
        if _bad_lang(ans):  # 끝내 실패하면 깨진 문장 대신 근거로 안전 폴백 (문법 보존)
            return "깔끔한 한국어 답변을 만들지 못했어요. 아래 근거 리뷰를 참고해주세요.\n" + ctx, ctx
        return ans, ctx
    except Exception as e:
        # 의미검색은 LLM 없이도 동작 → Ollama 미가동/모델 미설치여도 근거는 반환
        return f"(LLM 응답 생성을 건너뜀: {e})\n검색된 근거 리뷰:\n{ctx}", ctx


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    d = db.get_db()
    for q in ["스텐 텀블러 후기 어때?", "이어폰 소리 어때?", "고객 응대(CS)는 괜찮아?", "배송 빠른 거 추천해줘"]:
        ans, ctx = ask(d, q)
        print(f"\nQ: {q}")
        print(f"A: {ans}")
        print(f"한자·영어 없음? {'O' if not _bad_lang(ans) else 'X'}")
