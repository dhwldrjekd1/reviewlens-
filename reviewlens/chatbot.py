import json, re, os, urllib.request
import numpy as np
import db, recommend, retriever, aspect_rules

ASPECTS = ["배송", "품질", "가격", "포장", "디자인", "CS"]
MODEL = "gemma3:4b"          # 라이브 챗봇(빠름). 한국어 품질 우수, 답변 캐시·사전계산으로 즉답
SUMMARY_MODEL = "gemma4:12b"  # 오프라인 상품요약 전용(품질 최상). 12B라 느리지만 빌드 1회뿐 → 라이브 무영향
_THINKING = ("gemma4", "qwen3")  # 추론(thinking) 모델 → think off 안 하면 영어 사고를 출력에 흘림
REVIEW_MIN_SCORE = 0.45  # 의미검색 폴백 관련도 하한 — 오타·미등록상품·난센스에 엉뚱한 상품 단정 방지


# 검색된 리뷰를 근거 텍스트로 (원문 + 속성 감성 라벨)
def _review_ctx(d, hits):
    lines = []
    for h in hits:
        labs = d.execute("select aspect, sentiment from aspect_sentiment where review_id=?",
                         (h["review_id"],)).fetchall()
        tag = " ".join(f"{a}/{s}" for a, s in labs)
        lines.append(f"- ({h['name']}) {h['text']}" + (f"  [{tag}]" if tag else ""))
    return "\n".join(lines)


# 질문에 특정 상품명이 언급됐나 → (item_id, name) 또는 None.
# 이름 토큰(len>=2)이 질문에 그대로 들어가면 매칭. 가장 긴 매칭 토큰의 상품을 택해 모호성 완화.
def _named_item(d, q):
    best = None
    for iid, name in d.execute("select item_id, name from item").fetchall():
        for w in name.split():
            if len(w) >= 2 and w in q and (best is None or len(w) > best[2]):
                best = (iid, name, len(w))
    return (best[0], best[1]) if best else None


# 사전계산된 상품 요약 즉답 (없으면 None → LLM 폴백 신호)
def _product_direct(d, iid):
    row = d.execute("select summary from product_summary where item_id=?", (iid,)).fetchone()
    return row[0] if row and row[0] and row[0].strip() else None


# 사전계산 요약의 근거 패널: 그 상품의 속성 긍/부정 집계 + 대표 리뷰 2건
def _product_ctx(d, iid):
    rows = d.execute("select aspect, sentiment, count(*) from aspect_sentiment "
                     "where item_id=? group by aspect, sentiment", (iid,)).fetchall()
    agg = {}
    for a, s, c in rows:
        agg.setdefault(a, {"positive": 0, "negative": 0})[s] = c
    lines = [f"- {a}: 긍정 {v['positive']} / 부정 {v['negative']}" for a, v in agg.items()]
    revs = d.execute("select raw_text from review where item_id=? limit 2", (iid,)).fetchall()
    lines += [f"- (리뷰) {t}" for (t,) in revs]
    return "상품 리뷰 집계:\n" + "\n".join(lines)


# 일반 속성 질문: 전체 긍/부정 집계 → (근거, 즉답 문장). DB에 답이 있으므로 LLM 없이 바로 생성
def _aggregate(d, asps):
    ctx_lines, ans = [], []
    for a in asps:
        c = dict(d.execute("select sentiment, count(*) from aspect_sentiment "
                           "where aspect=? group by sentiment", (a,)).fetchall())
        pos, neg = c.get("positive", 0), c.get("negative", 0)
        ctx_lines.append(f"- {a}: 긍정 {pos} / 부정 {neg}")
        tot = pos + neg
        if tot == 0:
            ans.append(f"'{a}' 항목은 아직 리뷰가 충분하지 않아요.")
        else:
            r = pos / tot
            tone = ("만족한다는 의견이 많은 편" if r >= 0.6 else
                    "아쉽다는 의견이 많은 편" if r <= 0.4 else "평가가 엇갈리는 편")
            ans.append(f"'{a}' 항목은 긍정 {pos}건, 부정 {neg}건으로 전반적으로 {tone}입니다.")
    return "속성별 리뷰 집계(전체):\n" + "\n".join(ctx_lines), " ".join(ans)


# 추천 결과 → 즉답 문장 (추천 순위·이유가 이미 계산돼 있으므로 LLM 불필요)
def _recommend_answer(recs):
    if not recs:
        return "추천할 만한 상품을 아직 찾지 못했어요."
    def lvl(p):  # 긍정 비율 → 정성 표현 (인위적인 % 대신)
        return "매우 높음" if p >= 0.85 else "높음" if p >= 0.6 else "보통"
    parts = []
    for _, n, why in recs[:2]:
        rs = ", ".join(f"{a} 만족도 {lvl(p)}" for a, p in why[:2])
        parts.append(f"{n}({rs})" if rs else n)
    return "리뷰 분석 결과, 추천 상품은 " + ", ".join(parts) + " 입니다."


# 질문 → (근거, 모드, 즉답). 즉답이 있으면(집계·추천) LLM 생략 → 신규 질문도 즉시.
# 즉답이 None이면(자유서술형 리뷰) LLM으로 생성.
def ground(d, q):
    if "추천" in q:  # 추천 의도 → 중시 속성으로 추천
        asp = [a for a in ASPECTS if a in q]
        recs = recommend.recommend(d, {a: 1 for a in asp} or {"품질": 1})
        ctx = "\n".join(f"- {n}: " + ", ".join(f"{a} {int(p*100)}%" for a, p in why)
                        for _, n, why in recs)
        return ctx, "recommend", _recommend_answer(recs)
    named = _named_item(d, q)              # 특정 상품 언급? → (item_id, name) or None
    asps = aspect_rules.detect(q)
    if asps and not named:                 # 상품 안 정한 일반 속성 질문 → 전체 집계로 즉답
        ctx, direct = _aggregate(d, asps)
        return ctx, "aggregate", direct
    if named:                              # 특정 상품 → 사전계산 요약이 있으면 즉답
        direct = _product_direct(d, named[0])
        if direct:
            return _product_ctx(d, named[0]), "product", direct
        # 사전계산 없음(미빌드) → 아래 LLM 폴백
    hits = retriever.search(d, q, k=2)     # 자유서술형 / 미빌드 폴백 → 의미검색 + LLM
    if not hits or hits[0]["score"] < REVIEW_MIN_SCORE:  # 관련 리뷰 없음 → 엉뚱한 상품 단정 회피
        return "", "review", None
    return _review_ctx(d, hits), "review", None


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
    if correction and correction.strip():
        _CACHE.clear(); _EXACT.clear()   # 정정이 들어오면 캐시 무효화 → 다음엔 정정 반영해 재생성


# --- 답변 캐시: 같은/비슷한 질문은 생성 결과를 재사용 → 즉시 응답(품질 동일, CPU 생성 생략) ---
# 1) 완전일치(_EXACT): 임베딩 없이 dict 즉시 조회 (칩 등 동일 질문)
# 2) 의미유사(_CACHE): 표현이 달라도 임베딩 코사인 ≥ 임계치면 재사용
_EXACT = {}          # 정규화 질문 → (answer, evidence)
_CACHE = []          # [{"emb": 질문벡터, "answer": 답변, "evidence": 근거}]
_CACHE_THR = 0.94    # 의미 유사도 임계치(높게 → 엉뚱한 재사용 방지)


def _norm(q):
    return re.sub(r"\s+", "", q.strip()).lower()


def _cache_get(q):
    e = _EXACT.get(_norm(q))             # 완전일치 → 임베딩 없이 즉시
    if e:
        return {"answer": e[0], "evidence": e[1]}
    if not _CACHE:
        return None
    qe = retriever.get_model().encode([q], normalize_embeddings=True)[0]
    best, score = None, 0.0
    for c in _CACHE:
        s = float(c["emb"] @ qe)
        if s > score:
            score, best = s, c
    return best if score >= _CACHE_THR else None


def _cache_put(q, answer, evidence):
    if not answer or _bad_lang(answer):     # 깨진 답변은 캐시하지 않음
        return
    _EXACT[_norm(q)] = (answer, evidence)
    emb = retriever.get_model().encode([q], normalize_embeddings=True)[0]
    _CACHE.append({"emb": emb, "answer": answer, "evidence": evidence})
    if len(_CACHE) > 200:
        _CACHE.pop(0)


_RULES = "한국어로만(한자·영어 금지) 1~2문장으로 답해."


def _build(q, ctx, corr, mode="review"):
    if corr:  # 정정이 있으면 '근거에만 기반' 대신 '정정 우선'으로 — 안 그러면 정정을 무시함
        head = ("아래 '정정'을 최우선으로 반영하고 '근거'도 참고해 " + _RULES + "\n"
                "정정:\n" + "\n".join(f"- {c}" for c in corr) + "\n")
    elif mode == "recommend":
        head = "아래 '추천 목록'을 바탕으로 " + _RULES + " 추천 상품과 이유를 자연스럽게 알려줘.\n"
    elif mode == "aggregate":  # 일반 속성 질문: 특정 상품 단정 금지, 전반적 경향으로
        head = ("아래 '근거'(여러 상품 리뷰의 전체 집계)를 바탕으로 " + _RULES +
                " 특정 상품명을 단정하지 말고 전반적인 경향으로 답해. 근거에 없으면 지어내지 마.\n")
    else:
        head = ("아래 '근거'에만 기반해 " + _RULES +
                " 질문에 없는 상품을 새로 단정하지 말고, 근거에 없으면 지어내지 마.\n")
    return head + f"질문: {q}\n근거:\n{ctx}\n답변:"


# --- 한자/불필요 영어 탐지 (삭제 대신 재생성 판정) ---
def _has_hanja(s):  # 코드포인트로 판정 (리터럴 범위는 한글 AC00–D7A3을 삼킬 위험)
    return any(0x3400 <= ord(c) <= 0x9fff or 0xf900 <= ord(c) <= 0xfaff for c in s)


# 제품 약어·단위는 한국어 문장에 섞여도 정상 (LED 스탠드, 500ml 등)
_OK_EN = {"CS", "LED", "OLED", "QLED", "USB", "TV", "PC", "AS", "IT",
          "GB", "MB", "TB", "ML", "L", "KG", "G", "CM", "MM", "W", "V", "HZ"}


def _bad_lang(s):
    if _has_hanja(s):
        return True
    for tok in s.split():
        for en in re.findall(r"[A-Za-z]+", tok):     # 토큰 속 라틴 덩어리만 검사(한글 조사·숫자 무시)
            if en.upper() not in _OK_EN:             # 허용 약어/단위 외 영어 → 비정상(영어 누출·깨짐)
                return True
    return False


OLLAMA = "http://localhost:11434/api/generate"
# 백엔드 전환: 둘 다 내부 엔진은 llama.cpp. RL_BACKEND=llamacpp 면 llama-server로 직접 호출.
BACKEND = os.environ.get("RL_BACKEND", "ollama")            # ollama | llamacpp
LLAMACPP = os.environ.get("RL_LLAMACPP", "http://localhost:8080")  # llama-server 주소


def _generate(prompt, temp=0.0, seed=0, model=None):
    if BACKEND == "llamacpp":                              # llama-server는 기동 시 GGUF 1개 서빙(model 무시)
        body = {"prompt": prompt, "n_predict": 200, "temperature": temp, "stream": False}
        if seed:
            body["seed"] = seed
        req = urllib.request.Request(LLAMACPP + "/completion", json.dumps(body).encode(),
                                     {"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(req, timeout=300).read())["content"].strip()
    m = model or MODEL
    opts = {"temperature": temp, "num_predict": 200}   # 답변 길이 제한 → 과생성 방지
    if seed:
        opts["seed"] = seed
    body = {"model": m, "stream": False, "keep_alive": "30m",     # 모델 상시 로드
            "prompt": prompt, "options": opts}
    if any(m.startswith(t) for t in _THINKING):
        body["think"] = False                          # 추론모델: 사고 off → 깔끔한 한국어 즉답
    req = urllib.request.Request(OLLAMA, json.dumps(body).encode(), {"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=300).read())["response"].strip()


# 토큰 스트림(백엔드 공통) — 토큰 문자열을 순서대로 yield
def _stream_tokens(prompt):
    if BACKEND == "llamacpp":
        body = {"prompt": prompt, "n_predict": 200, "temperature": 0.0, "stream": True}
        req = urllib.request.Request(LLAMACPP + "/completion", json.dumps(body).encode(),
                                     {"Content-Type": "application/json"})
        for line in urllib.request.urlopen(req, timeout=300):
            line = line.strip()
            if not line:
                continue
            if line.startswith(b"data: "):       # llama-server SSE: 'data: ' prefix 제거
                line = line[6:]
            o = json.loads(line)
            if o.get("content"):
                yield o["content"]
            if o.get("stop"):
                break
        return
    body_d = {"model": MODEL, "stream": True, "keep_alive": "30m",
              "prompt": prompt, "options": {"temperature": 0.0, "num_predict": 200}}
    if any(MODEL.startswith(t) for t in _THINKING):
        body_d["think"] = False                  # 추론모델이면 사고 off
    req = urllib.request.Request(OLLAMA, json.dumps(body_d).encode(), {"Content-Type": "application/json"})
    for line in urllib.request.urlopen(req, timeout=180):    # Ollama NDJSON 청크
        line = line.strip()
        if not line:
            continue
        o = json.loads(line)
        if o.get("response"):
            yield o["response"]
        if o.get("done"):
            break


# 스트리밍 답변: 토큰을 그대로 흘려보냄(체감 속도↑). 단 사후 자기검증/재생성은 불가 →
# 강한 한국어 프롬프트 + temp 0에 의존. 견고함이 필요하면 비스트리밍 ask()를 쓸 것.
def ask_stream(d, q):
    hit = _cache_get(q)
    if hit:                                  # 캐시 적중 → 생성 생략, 즉시 응답
        yield {"token": hit["answer"]}
        yield {"evidence": hit["evidence"], "done": True}
        return
    ctx, mode, direct = ground(d, q)
    if not ctx:
        yield {"token": "질문과 관련된 리뷰를 찾지 못했어요. 상품명이나 배송·품질 같은 속성으로 물어봐 주세요."}
        yield {"evidence": "", "done": True}
        return
    corr = recall_corrections(d, q)
    if direct and not corr:                  # 집계·추천 즉답(LLM 생략) → 신규 질문도 즉시
        yield {"token": direct}
        _cache_put(q, direct, ctx)
        yield {"evidence": ctx, "done": True}
        return
    prompt = _build(q, ctx, corr, mode)
    full = ""
    try:
        for tok in _stream_tokens(prompt):      # 백엔드(ollama/llamacpp) 공통
            full += tok
            yield {"token": tok}
    except Exception as e:
        yield {"token": f"(LLM 응답 생성을 건너뜀: {e})"}
        yield {"evidence": ctx, "done": True}
        return
    # 스트리밍은 사후 언어검증을 못 하므로, 끝난 뒤 한자/영어가 섞였으면 깨끗하게 재생성해 교체
    final = full
    if _bad_lang(full):
        clean = _generate(prompt + "\n주의: 한자나 영어를 쓰지 말고 한국어 문장으로만.", 0.6, 1)
        if not _bad_lang(clean):
            yield {"replace": clean}
            final = clean
    _cache_put(q, final, ctx)               # 다음 동일/유사 질문은 즉시 응답
    yield {"evidence": ctx, "done": True}


# 자기검증: 답변이 근거에 충실한지 모델 스스로 판정 (근거 없는 환각 자동 차단)
def _grounded(ans, ctx):
    judge = ("다음 '답변'이 '근거'에 실제로 있는 내용만 말하는지 판정해. "
             "근거에 없는 사실을 지어냈으면 NO, 충실하면 YES. 한 단어로만.\n"
             f"근거:\n{ctx}\n답변: {ans}\n판정(YES/NO):")
    r = _generate(judge).upper()
    return "NO" not in r and "아니" not in r


def ask(d, q):
    hit = _cache_get(q)
    if hit:                                   # 캐시 적중 → 즉시 응답
        return hit["answer"], hit["evidence"]
    ctx, mode, direct = ground(d, q)
    if not ctx:
        return "질문과 관련된 리뷰를 찾지 못했어요. 상품명이나 배송·품질 같은 속성으로 물어봐 주세요.", ""
    corr = recall_corrections(d, q)           # 교정 메모리 반영
    if direct and not corr:                   # 집계·추천 즉답(LLM 생략)
        _cache_put(q, direct, ctx)
        return direct, ctx
    prompt = _build(q, ctx, corr, mode)
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
        _cache_put(q, ans, ctx)
        return ans, ctx
    except Exception as e:
        return f"(LLM 응답 생성을 건너뜀: {e})\n검색된 근거 리뷰:\n{ctx}", ctx


# --- 오프라인 사전계산: 상품별 자연스러운 한국어 요약 (빌드 시 1회, ~상품 수만큼 LLM) ---
# 질의-시점 LLM 비용을 빌드-시점으로 옮김 → 특정 상품 질문도 즉답.
def _summary_prompt(name, agg_lines, revs):
    body = "\n".join(agg_lines + [f"- (리뷰) {t}" for t in revs])
    return ("아래 '근거'(특정 상품의 속성별 긍/부정 집계와 실제 리뷰)를 바탕으로 "
            + _RULES.replace("1~2문장", "2~3문장") +
            f" 상품명 '{name}'을 주어로, 주요 속성의 장단점을 자연스럽게 엮어 설명해. "
            "근거에 없는 내용은 지어내지 말고, 리뷰가 적으면 단정하지 마.\n"
            f"상품: {name}\n근거:\n{body}\n요약:")


def build_product_summaries(d, model=None):
    model = model or SUMMARY_MODEL          # 기본: 오프라인 고품질 모델
    n = 0
    for iid, name in d.execute("select item_id, name from item").fetchall():
        rows = d.execute("select aspect, sentiment, count(*) from aspect_sentiment "
                         "where item_id=? group by aspect, sentiment", (iid,)).fetchall()
        agg = {}
        for a, s, c in rows:
            agg.setdefault(a, {"positive": 0, "negative": 0})[s] = c
        agg_lines = []
        for a, v in agg.items():                         # _aggregate tone 로직 재사용
            pos, neg = v["positive"], v["negative"]; tot = pos + neg
            tone = ("만족" if tot and pos / tot >= 0.6 else
                    "아쉬움" if tot and pos / tot <= 0.4 else "혼재")
            agg_lines.append(f"- {a}: 긍정 {pos} / 부정 {neg} ({tone})")
        revs = [t for (t,) in d.execute(
            "select raw_text from review where item_id=? limit 3", (iid,)).fetchall()]

        if not agg_lines and not revs:                   # 리뷰 0건 → 정적 안내(LLM 생략)
            text = f"'{name}'은 아직 리뷰가 충분하지 않아 정확한 평가를 드리기 어려워요."
        else:
            p = _summary_prompt(name, agg_lines, revs)
            text = _generate(p, temp=0.2, seed=7, model=model)
            tries = 0
            while _bad_lang(text) and tries < 2:         # 한자/영어 → 재생성
                tries += 1
                text = _generate(p + "\n주의: 한자/영어 쓰지 말고 한국어로만.", 0.4, tries, model=model)
            if _bad_lang(text):                          # 끝내 실패 → 집계 폴백
                text = "리뷰 분석 결과, " + " ".join(
                    f"{a} 항목은 " + ("긍정적인" if v["positive"] >= v["negative"] else "아쉽다는")
                    + " 의견이 많아요." for a, v in agg.items())
        d.execute("insert or replace into product_summary(item_id, summary) values(?,?)",
                  (iid, text))
        n += 1
    d.commit()
    return n


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
