import json, re, urllib.request
import numpy as np
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


# --- 교정 메모리: 과거 사용자 정정 중 '의미가 비슷한 질문'의 정정을 불러옴 ---
# 모델 가중치를 안 건드리고 외부 메모리에 쌓음 → 즉시 반영 + 지식 보존(망가질 게 없음)
def recall_corrections(d, q, k=2, thr=0.55):
    rows = d.execute("select question, correction from feedback "
                     "where correction is not null and trim(correction)!=''").fetchall()
    if not rows:
        return []
    m = retriever.get_model()
    qe = m.encode([q], normalize_embeddings=True)[0]
    me = m.encode([r[0] for r in rows], normalize_embeddings=True)
    sims = me @ qe
    hits = sorted(((float(s), rows[i][1]) for i, s in enumerate(sims) if s >= thr), reverse=True)
    return [c for _, c in hits[:k]]


def record_feedback(d, q, answer="", vote="", correction=""):
    d.execute("insert into feedback(question, answer, vote, correction) values(?,?,?,?)",
              (q, answer, vote, correction))
    d.commit()


PROMPT = """너는 한국 쇼핑몰의 리뷰 분석 도우미야. 아래 '근거'에만 기반해 답해.

규칙:
- 반드시 자연스럽고 문법에 맞는 한국어로만 답한다. 한자나 영어 단어를 절대 섞지 않는다.
- 근거에 없는 내용은 지어내지 않는다.
- 1~3문장으로 간결하게.
{corr}질문: {q}
근거:
{ctx}

답변(한국어):"""


def _build(q, ctx, corr):
    block = ""
    if corr:
        block = "확인된 정정(사용자 피드백 — 근거보다 우선 적용):\n" + \
                "\n".join(f"- {c}" for c in corr) + "\n\n"
    return PROMPT.format(corr=block, q=q, ctx=ctx)


# --- 한자/불필요 영어 탐지 (삭제 대신 재생성 판정) ---
def _has_hanja(s):  # 코드포인트로 판정 (리터럴 범위는 한글 AC00–D7A3을 삼킬 위험)
    return any(0x3400 <= ord(c) <= 0x9fff or 0xf900 <= ord(c) <= 0xfaff for c in s)


def _bad_lang(s):
    if _has_hanja(s):
        return True
    for tok in s.split():
        if not re.search(r"[A-Za-z]", tok):
            continue
        if re.search(r"[가-힣]", tok):              # 한글+영어 혼합 단어 (괜shaw)
            return True
        bare = tok.strip(".,!?()[]\"'·").upper()
        if bare == "CS" or re.search(r"\d", tok):    # 허용: CS, 500ml 등
            continue
        return True                                  # 그 외 순수 영어 단어
    return False


OLLAMA = "http://localhost:11434/api/generate"


def _generate(prompt, temp=0.0, seed=0):
    opts = {"temperature": temp, "num_predict": 200}   # 답변 길이 제한 → 과생성 방지
    if seed:
        opts["seed"] = seed
    body = json.dumps({"model": "qwen2.5:3b", "stream": False, "keep_alive": "30m",
                       "prompt": prompt, "options": opts}).encode()   # 모델 상시 로드
    req = urllib.request.Request(OLLAMA, body, {"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=180).read())["response"].strip()


# 스트리밍 답변: 토큰을 그대로 흘려보냄(체감 속도↑). 단 사후 자기검증/재생성은 불가 →
# 강한 한국어 프롬프트 + temp 0에 의존. 견고함이 필요하면 비스트리밍 ask()를 쓸 것.
def ask_stream(d, q):
    ctx = ground(d, q)
    if not ctx:
        yield {"token": "관련 데이터를 못 찾았어요."}
        yield {"evidence": "", "done": True}
        return
    corr = recall_corrections(d, q)
    prompt = _build(q, ctx, corr)
    body = json.dumps({"model": "qwen2.5:3b", "stream": True, "keep_alive": "30m",
                       "prompt": prompt, "options": {"temperature": 0.0, "num_predict": 200}}).encode()
    try:
        req = urllib.request.Request(OLLAMA, body, {"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=180)
        for line in resp:                       # Ollama는 NDJSON 청크 스트림
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if obj.get("response"):
                yield {"token": obj["response"]}
            if obj.get("done"):
                break
    except Exception as e:
        yield {"token": f"(LLM 응답 생성을 건너뜀: {e})"}
    yield {"evidence": ctx, "done": True}


# 자기검증: 답변이 근거에 충실한지 모델 스스로 판정 (근거 없는 환각 자동 차단)
def _grounded(ans, ctx):
    judge = ("다음 '답변'이 '근거'에 실제로 있는 내용만 말하는지 판정해. "
             "근거에 없는 사실을 지어냈으면 NO, 충실하면 YES. 한 단어로만.\n"
             f"근거:\n{ctx}\n답변: {ans}\n판정(YES/NO):")
    r = _generate(judge).upper()
    return "NO" not in r and "아니" not in r


def ask(d, q):
    ctx = ground(d, q)
    if not ctx:
        return "관련 데이터를 못 찾았어요.", ""
    corr = recall_corrections(d, q)           # 교정 메모리 반영
    prompt = _build(q, ctx, corr)
    try:
        ans = _generate(prompt)                                  # 1차(결정적)
        tries = 0
        while _bad_lang(ans) and tries < 2:                      # 언어 검증 → 재생성
            tries += 1
            ans = _generate(prompt + "\n주의: 한자/영어 쓰지 말고 한국어로만.", 0.6, tries)
        # 자기검증(근거 충실성) 1회 — 실패 시 1회 재생성
        if not _bad_lang(ans) and not _grounded(ans, ctx):
            cand = _generate(prompt + "\n주의: 근거에 있는 내용만 사용해 다시 답하라.", 0.4, 7)
            if not _bad_lang(cand):
                ans = cand
        if _bad_lang(ans):  # 끝내 실패: 깨진 문장 대신 근거 폴백
            return "깔끔한 한국어 답변을 만들지 못했어요. 아래 근거 리뷰를 참고해주세요.\n" + ctx, ctx
        return ans, ctx
    except Exception as e:
        return f"(LLM 응답 생성을 건너뜀: {e})\n검색된 근거 리뷰:\n{ctx}", ctx


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    d = db.get_db()
    # 교정 메모리 데모: 일부러 정정 하나 심고 비슷한 질문을 던져 반영되는지 확인
    record_feedback(d, "백팩 배송 어때?", correction="베이직 백팩은 배송이 느린 편이라고 안내해야 한다.")
    for q in ["이어폰 소리 어때?", "백팩 배송 빠른가요?"]:
        ans, ctx = ask(d, q)
        print(f"\nQ: {q}\nA: {ans}\n한자·영어 없음? {'O' if not _bad_lang(ans) else 'X'}")
