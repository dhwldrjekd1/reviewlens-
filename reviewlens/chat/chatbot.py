import json, re, os, threading, urllib.request
from store import db
from recommend import recommend_live
from chat import retriever
from absa import aspect_rules

ASPECTS = ["배송", "품질", "가격", "포장", "디자인", "CS"]
MODEL = "gemma3:4b"          # 라이브 챗봇(빠름). 한국어 품질 우수, 답변 캐시·사전계산으로 즉답
SUMMARY_MODEL = "gemma3:4b"   # 오프라인 상품요약 전용. 빌드 1회뿐 → 라이브 무영향
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


# 질문에 언급된 상품들 (0개 이상) — 이름 토큰(len>=2)이 질문에 그대로 들어가면 매칭.
def _named_items(d, q):
    return [(iid, name) for iid, name in d.execute("select item_id, name from item").fetchall()
            if any(len(w) >= 2 and w in q for w in name.split())]


# 상품 비교: 두(이상) 상품을 긍정률로 비교 ("A랑 B 중 뭐가 나아?")
def _compare(d, named):
    rows = []
    for iid, name in named[:3]:
        p, g = d.execute("select sum(sentiment='positive'), sum(sentiment='negative') "
                         "from aspect_sentiment where item_id=?", (iid,)).fetchone()
        p, g = p or 0, g or 0; t = p + g
        rows.append((name, round(100 * p / t) if t else 0, p, g))
    rows.sort(key=lambda x: -x[1])
    ctx = "상품별 만족도(긍정률):\n" + "\n".join(f"- {n}: {s}% (긍 {p}/부 {g})" for n, s, p, g in rows)
    parts = ", ".join(f"{n} {s}%" for n, s, _, _ in rows)
    return ctx, "compare", f"리뷰 만족도 기준으로 {parts}예요. '{rows[0][0]}'가 더 좋은 평가를 받았습니다."


# 특정 상품 + 특정 속성: "○○ 배송 어때?"
def _product_aspect(d, iid, name, asps):
    parts, lines = [], []
    for a in asps:
        p, g = d.execute("select sum(sentiment='positive'), sum(sentiment='negative') "
                         "from aspect_sentiment where item_id=? and aspect=?", (iid, a)).fetchone()
        p, g = p or 0, g or 0; t = p + g
        lines.append(f"- {a}: 긍정 {p} / 부정 {g}")
        if t == 0:
            parts.append(f"{a} 관련 리뷰가 적어요")
        else:
            tone = ("긍정적" if p / t >= 0.6 else
                    "아쉽다는 의견" if p / t <= 0.4 else "평가가 엇갈리는 편")
            parts.append(f"{a} {tone}(긍 {p}/부 {g})")
    return f"{name} 속성 집계:\n" + "\n".join(lines), "product_aspect", f"'{name}'의 " + ", ".join(parts) + "."


# 장점/단점만: "○○ 단점만 알려줘"
def _proscons(d, iid, name, q):
    rows = d.execute("select aspect, sum(sentiment='positive'), sum(sentiment='negative') "
                     "from aspect_sentiment where item_id=? group by aspect", (iid,)).fetchall()
    pos = [a for a, p, g in rows if (p or 0) > (g or 0)]
    neg = [a for a, p, g in rows if (g or 0) > 0 and (g or 0) >= (p or 0)]
    has_neg = any(k in q for k in ("단점", "나쁜", "안 좋", "아쉬", "약점"))
    has_pos = any(k in q for k in ("장점", "좋은", "강점", "장단"))   # '장단점'은 둘 다
    if has_neg and not has_pos:
        direct = f"'{name}'의 아쉬운 점은 " + (", ".join(neg) if neg else "두드러진 단점이 없는") + " 편이에요."
    elif has_pos and not has_neg:
        direct = f"'{name}'의 강점은 " + (", ".join(pos) if pos else "뚜렷하지 않은") + " 편이에요."
    else:
        direct = (f"'{name}'의 강점은 {', '.join(pos) or '뚜렷하지 않음'}, "
                  f"아쉬운 점은 {', '.join(neg) or '뚜렷하지 않음'} 쪽이에요.")
    return _product_ctx(d, iid), "proscons", direct


# 상품 목록: "어떤 상품 있어?"
def _product_list(d):
    cats = {}
    for name, cat in d.execute("select name, category from item").fetchall():
        cats.setdefault(cat, []).append(name)
    ctx = "취급 상품:\n" + "\n".join(f"- [{c}] {', '.join(ns)}" for c, ns in cats.items())
    direct = ("취급 상품은 — " + " / ".join(f"{c}: {', '.join(ns)}" for c, ns in cats.items())
              + " 입니다. 궁금한 상품을 물어보세요!")
    return ctx, "list", direct


def _wants_list(q):
    s = q.replace(" ", "")
    return any(k in s for k in ("상품목록", "상품리스트", "어떤상품", "무슨상품", "뭐팔", "뭐있", "상품뭐", "품목", "목록"))


def _wants_proscons(q):
    return any(k in q for k in ("장점", "단점", "좋은점", "나쁜점", "강점", "약점", "좋은 점", "나쁜 점"))


def _wants_repurchase(q):                   # "재구매 의사 있나요?" 류
    s = q.replace(" ", "")
    return any(k in s for k in ("재구매", "재구입", "다시살", "또살", "또구매", "다시구매", "또사", "충성도", "재방문"))


def _wants_overview(q):                     # "전체 리뷰 알려줘" 류 → 전반 개요
    s = q.replace(" ", "")
    if any(k in s for k in ("전체리뷰", "리뷰전체", "모든리뷰", "리뷰전부", "리뷰요약",
                            "리뷰개요", "전체평가", "총평", "전반적")):
        return True
    # 앞에 다른 명사(상품·카테고리) 없이 '리뷰 알려/보여/줘'로 시작할 때만 (그 외엔 RAG로)
    return s.startswith("리뷰") and any(k in s for k in ("알려", "보여", "줘", "어때", "말해"))


def _wants_improve(q):                      # "개선점/문제점이 뭐야?" / "부정이 가장 많은 항목은?"
    s = q.replace(" ", "")
    if any(k in s for k in ("개선점", "개선할", "문제점", "뭘고쳐", "어디고쳐", "보완", "취약", "고칠점", "약한부분", "불만이많")):
        return True
    return "부정" in s and any(k in s for k in ("많", "가장", "제일", "1위", "최다"))


def _wants_strength(q):                     # "강점/셀링포인트가 뭐야?" (상품 미지정 일반)
    s = q.replace(" ", "")
    return any(k in s for k in ("셀링포인트", "강점이", "강점은", "강점뭐", "강조할", "어필", "마케팅포인트", "잘하는", "내세울"))


def _wants_copy(q):                         # "광고 문구/카피 추천"
    s = q.replace(" ", "")
    return any(k in s for k in ("광고문구", "광고카피", "카피", "마케팅문구", "마케팅메시지", "홍보문구", "광고만들", "문구추천"))


def _wants_reply(q):                        # "부정 리뷰 답글/대응"
    s = q.replace(" ", "")
    return any(k in s for k in ("답글", "답변초안", "사과문", "대응문구", "리뷰대응", "답변써", "답글써"))


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


# 스몰토크: 인사·감사·작별·도움요청 → 친근한 정형 응답 (검색·LLM 불필요). 도우미다운 대화감.
_GREET = ("안녕", "하이", "헬로", "hello", "hi", "방가", "반가", "ㅎㅇ")
_THANKS = ("고마", "감사", "thank", "ㄳ", "굿")
_BYE = ("잘가", "바이", "bye", "수고", "이만", "들어가")
_HELP = ("도와", "도움", "뭐할", "뭘할", "뭐물어", "뭘물어", "무엇을", "어떻게써", "어떻게사용",
         "사용법", "기능", "할수있", "할수잇", "누구", "정체", "어떤거")


def _smalltalk(q):
    s = q.strip().lower().replace(" ", "").replace("?", "").replace("!", "")
    if any(g.replace(" ", "") in s for g in _GREET):
        return ("안녕하세요! 실제 리뷰를 근거로 답해드리는 리뷰 인사이트 도우미예요 🙂 "
                "상품·배송·품질·추천 등 무엇이든 물어보세요. 예) \"배송 빠른가요?\", \"가성비 추천해줘\"")
    if any(t in s for t in _THANKS):
        return "도움이 되었다니 기뻐요! 더 궁금한 점 있으면 언제든 물어보세요."
    if any(b in s for b in _BYE):
        return "이용해 주셔서 감사합니다. 좋은 하루 보내세요! 👋"
    if any(h.replace(" ", "") in s for h in _HELP):
        return ("리뷰를 근거로 상품을 안내해드려요. 이렇게 물어보세요 — "
                "속성(\"배송·품질·가격 어때요?\"), 특정 상품(\"아쿠아 무선이어폰 어때요?\"), 추천(\"가성비 추천해줘\").")
    return None


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


def _overview(d):                           # 전체 리뷰 개요 — 규모·긍정률·속성집계·강점/개선
    items = d.execute("select count(*) from item").fetchone()[0]
    revs = d.execute("select count(*) from review").fetchone()[0]
    agg = {}
    for a, s, c in d.execute("select aspect, sentiment, count(*) from aspect_sentiment "
                             "group by aspect, sentiment").fetchall():
        agg.setdefault(a, {"positive": 0, "negative": 0})[s] = c
    order = sorted(agg.items(), key=lambda kv: -(kv[1]["positive"] + kv[1]["negative"]))
    ctx = (f"전체 리뷰 개요 (상품 {items} · 리뷰 {revs}):\n"
           + "\n".join(f"- {a}: 긍정 {v['positive']} / 부정 {v['negative']}" for a, v in order))
    tot_pos = sum(v["positive"] for v in agg.values())
    tot = tot_pos + sum(v["negative"] for v in agg.values())
    if tot == 0:
        return ctx, "overview", "아직 분석된 리뷰가 충분하지 않아요."
    ratio = round(tot_pos / tot * 100)
    rated = [(a, v["positive"] / (v["positive"] + v["negative"]))
             for a, v in agg.items() if (v["positive"] + v["negative"])]
    strong, weak = max(rated, key=lambda x: x[1])[0], min(rated, key=lambda x: x[1])[0]
    ans = (f"전체 {items}개 상품·{revs}개 리뷰 기준 긍정 비율은 약 {ratio}%입니다. "
           f"강점은 '{strong}', 개선이 필요한 항목은 '{weak}'이에요. "
           f"특정 상품이나 속성(배송·품질 등)을 물어보면 더 자세히 알려드릴게요.")
    return ctx, "overview", ans


def _repurchase(d, iid=None):               # 재구매 의향 — 리뷰 직접 언급이 적어 만족도로 추정 (iid 있으면 그 상품만)
    where = "where item_id=?" if iid else ""
    params = (iid,) if iid else ()
    agg = {}
    for a, s, c in d.execute(f"select aspect, sentiment, count(*) from aspect_sentiment {where} "
                             "group by aspect, sentiment", params).fetchall():
        agg.setdefault(a, {"positive": 0, "negative": 0})[s] = c
    tot_pos = sum(v["positive"] for v in agg.values())
    tot = tot_pos + sum(v["negative"] for v in agg.values())
    ratio = round(tot_pos / tot * 100) if tot else 0
    rated = sorted([(a, v["positive"] / (v["positive"] + v["negative"]))
                    for a, v in agg.items() if (v["positive"] + v["negative"])], key=lambda x: -x[1])
    strong = ", ".join(a for a, _ in rated[:2]) or "여러 속성"
    tone = "높은 편" if ratio >= 60 else "낮은 편" if ratio <= 40 else "보통"
    ctx = f"재구매 의향 추정 근거:\n- 전체 긍정률 {ratio}%\n- 강점 속성: {strong}"
    ans = (f"리뷰에 '재구매'를 직접 언급한 경우는 많지 않지만, 전체 만족도(긍정률 {ratio}%)와 "
           f"강점({strong})으로 보면 재구매 의향은 {tone}으로 추정됩니다. "
           f"만족도가 높은 속성일수록 재구매로 이어질 가능성이 큽니다.")
    return ctx, "repurchase", ans


def _agg_aspect(d):                         # 속성별 긍/부정 집계 dict (여러 핸들러 공유)
    agg = {}
    for a, s, c in d.execute("select aspect, sentiment, count(*) from aspect_sentiment "
                             "group by aspect, sentiment").fetchall():
        agg.setdefault(a, {"positive": 0, "negative": 0})[s] = c
    return agg


def _strength(d):                           # 강점/셀링포인트 — 긍정률 상위 속성
    agg = _agg_aspect(d)
    rated = sorted([(a, round(v["positive"] / (v["positive"] + v["negative"]) * 100))
                    for a, v in agg.items() if v["positive"] + v["negative"]], key=lambda x: -x[1])[:3]
    if not rated:
        return "", "strength", "아직 강점을 판단할 리뷰가 부족해요."
    ctx = "강점 속성(긍정률):\n" + "\n".join(f"- {a}: {s}%" for a, s in rated)
    parts = ", ".join(f"{a}({s}%)" for a, s in rated)
    ans = (f"리뷰 기준 강점(셀링포인트)은 {parts} 순이에요. "
           f"광고·상세페이지에서 이 속성을 전면에 내세우면 설득력이 높아집니다.")
    return ctx, "strength", ans


def _improve(d):                            # 개선 우선순위 — 부정 건수 상위 속성
    rows = d.execute("select aspect, count(*) from aspect_sentiment where sentiment='negative' "
                     "group by aspect order by count(*) desc").fetchall()[:3]
    if not rows:
        return "", "improve", "현재 두드러진 부정 이슈가 없어요."
    ctx = "개선 우선순위(부정 건수):\n" + "\n".join(f"- {a}: 부정 {c}건" for a, c in rows)
    parts = ", ".join(f"{a}(부정 {c}건)" for a, c in rows)
    ans = (f"개선 우선순위는 {parts} 순입니다. "
           f"부정이 가장 많은 항목부터 대응하면 만족도 개선 효과가 큽니다.")
    return ctx, "improve", ans


def _copy_suggest(d, iid=None):             # 광고 카피 — 사전계산된 product_copy 노출 (iid 있으면 그 상품만)
    if iid:
        rows = d.execute("select i.name, p.copy from product_copy p join item i using(item_id) "
                         "where p.item_id=? and p.copy is not null and trim(p.copy)!='' limit 1", (iid,)).fetchall()
    else:
        rows = d.execute("select i.name, p.copy from product_copy p join item i using(item_id) "
                         "where p.copy is not null and trim(p.copy)!='' limit 3").fetchall()
    if not rows:
        return "", "copy", "광고 카피가 아직 생성되지 않았어요. (빌드 시 자동 생성됩니다)"
    ctx = "리뷰 강점 기반 광고 카피:\n" + "\n".join(f"- ({n}) {c}" for n, c in rows)
    ans = ("리뷰 강점으로 자동 생성한 광고 카피 예시예요 — "
           + " / ".join(f"\"{c}\"({n})" for n, c in rows[:2])
           + ". 대시보드 '마케팅 추천' 탭에서 상품별 전체 카피를 볼 수 있어요.")
    return ctx, "copy", ans


def _reply_suggest(d, iid=None):            # 부정 리뷰 답글 초안 노출 (iid 있으면 그 상품 리뷰만)
    if iid:
        rows = d.execute("select r.raw_text, rr.reply from review_reply rr join review r using(review_id) "
                         "where r.item_id=? and rr.reply is not null and trim(rr.reply)!='' limit 2", (iid,)).fetchall()
    else:
        rows = d.execute("select r.raw_text, rr.reply from review_reply rr join review r using(review_id) "
                         "where rr.reply is not null and trim(rr.reply)!='' limit 2").fetchall()
    if not rows:
        return "", "reply", "리뷰 답글이 아직 생성되지 않았어요. (빌드 시 자동 생성됩니다)"
    ctx = "부정 리뷰 답글 초안:\n" + "\n".join(f"- 리뷰: {t}\n  답글: {rp}" for t, rp in rows)
    ans = (f"부정 리뷰에 정중한 답글 초안을 자동으로 만들어요. 예) \"{rows[0][0][:28]}…\" → "
           f"\"{rows[0][1][:48]}…\". 대시보드 '리뷰 분석' 탭에서 전체 답글을 볼 수 있어요.")
    return ctx, "reply", ans


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
    if "추천" in q and not _wants_copy(q):  # 추천 의도 → 중시 속성으로 추천 ('카피 추천'은 제외)
        asp = [a for a in ASPECTS if a in q]
        recs = recommend_live.recommend(d, {a: 1 for a in asp} or {"품질": 1})
        ctx = "\n".join(f"- {n}: " + ", ".join(f"{a} {int(p*100)}%" for a, p in why)
                        for _, n, why in recs)
        return ctx, "recommend", _recommend_answer(recs)
    if _wants_list(q):                     # "어떤 상품 있어?" → 상품 목록
        return _product_list(d)
    named = _named_items(d, q)             # 언급된 상품들 (0개 이상)
    asps = aspect_rules.detect(q)
    if len(named) >= 2:                    # 두 상품 이상 → 비교
        return _compare(d, named)
    if len(named) == 1:                    # 특정 상품 한 개
        iid, name = named[0]
        if _wants_proscons(q):             # 장점/단점만
            return _proscons(d, iid, name, q)
        if asps:                           # 특정 상품 + 속성 ("○○ 배송 어때?")
            return _product_aspect(d, iid, name, asps)
        if _wants_repurchase(q):           # 특정 상품 + "재구매 의사 있나요?" → 그 상품 기준 추정
            return _repurchase(d, iid)
        if _wants_copy(q):                 # 특정 상품 + "광고 문구/카피 추천" → 그 상품 카피
            return _copy_suggest(d, iid)
        if _wants_reply(q):                # 특정 상품 + "부정 리뷰 답글" → 그 상품 리뷰 답글
            return _reply_suggest(d, iid)
        direct = _product_direct(d, iid)   # 그 외 → 사전계산 요약
        if direct:
            return _product_ctx(d, iid), "product", direct
        # 사전계산 없음(미빌드) → 아래 LLM 폴백
    if asps and not named:                 # 상품 안 정한 일반 속성 질문 → 전체 집계로 즉답
        ctx, direct = _aggregate(d, asps)
        return ctx, "aggregate", direct
    if _wants_overview(q) and not named:   # "전체 리뷰 알려줘" → 전반 개요로 즉답
        return _overview(d)
    if _wants_repurchase(q) and not named: # 상품 안 정한 "재구매 의사 있나요?" → 전체 기준 추정
        return _repurchase(d)
    if _wants_copy(q) and not named:       # 상품 안 정한 "광고 문구/카피 추천" → 전체 사전생성 카피
        return _copy_suggest(d)
    if _wants_reply(q) and not named:      # 상품 안 정한 "부정 리뷰 답글" → 전체 답글 초안
        return _reply_suggest(d)
    if _wants_improve(q) and not named:    # "개선점/문제점" → 개선 우선순위
        return _improve(d)
    if _wants_strength(q) and not named:   # "강점/셀링포인트" → 강점 속성
        return _strength(d)
    st = _smalltalk(q)                     # 인사·감사·도움요청 → 도우미다운 정형 응답(검색·LLM 불필요)
    if st:
        return "", "smalltalk", st
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
        with _CACHE_LOCK:                # clear 두 단계가 요청 스레드끼리 끼어들지 않도록
            _CACHE.clear(); _EXACT.clear()   # 정정이 들어오면 캐시 무효화 → 다음엔 정정 반영해 재생성


# --- 답변 캐시: 같은/비슷한 질문은 생성 결과를 재사용 → 즉시 응답(품질 동일, CPU 생성 생략) ---
# 1) 완전일치(_EXACT): 임베딩 없이 dict 즉시 조회 (칩 등 동일 질문)
# 2) 의미유사(_CACHE): 표현이 달라도 임베딩 코사인 ≥ 임계치면 재사용
_EXACT = {}          # 정규화 질문 → (answer, evidence)
_CACHE = []          # [{"emb": 질문벡터, "answer": 답변, "evidence": 근거}]
_CACHE_THR = 0.94    # 의미 유사도 임계치(높게 → 엉뚱한 재사용 방지)
_CACHE_LOCK = threading.Lock()   # _EXACT/_CACHE는 요청 스레드끼리 동시 접근 → 읽기/쓰기/clear 전부 이 락으로 직렬화


def _norm(q):
    return re.sub(r"\s+", "", q.strip()).lower()


def _cache_get(q):
    with _CACHE_LOCK:
        e = _EXACT.get(_norm(q))             # 완전일치 → 임베딩 없이 즉시
        if e:
            return {"answer": e[0], "evidence": e[1], "intent": e[2] if len(e) > 2 else "review"}
        if not _CACHE:
            return None
        cache_snapshot = list(_CACHE)
    qe = retriever.get_model().encode([q], normalize_embeddings=True)[0]   # 임베딩 계산은 락 밖에서(오래 걸림)
    best, score = None, 0.0
    for c in cache_snapshot:
        s = float(c["emb"] @ qe)
        if s > score:
            score, best = s, c
    return best if score >= _CACHE_THR else None


def _cache_put(q, answer, evidence, intent="review"):
    if not answer or _bad_lang(answer):     # 깨진 답변은 캐시하지 않음
        return
    emb = retriever.get_model().encode([q], normalize_embeddings=True)[0]
    with _CACHE_LOCK:
        _EXACT[_norm(q)] = (answer, evidence, intent)
        _CACHE.append({"emb": emb, "answer": answer, "evidence": evidence, "intent": intent})
        if len(_CACHE) > 200:
            _CACHE.pop(0)
        if len(_EXACT) > 200:      # _CACHE와 항상 같이 채워지는데 상한이 없어 무한정 늘어나던 것을 맞춤
            del _EXACT[next(iter(_EXACT))]   # dict는 삽입 순서를 보존하므로 가장 오래된 항목부터 제거


# 근거 항목 수(배지용): '- '로 시작하는 줄, 없으면 비어있지 않은 줄 수
def _ev_count(ctx):
    if not ctx:
        return 0
    items = sum(1 for l in ctx.split("\n") if l.strip().startswith("-"))
    return items or len([l for l in ctx.split("\n") if l.strip()])


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
        yield {"meta": {"intent": hit.get("intent", "review"), "evidence_n": _ev_count(hit["evidence"]), "cached": True}}
        yield {"token": hit["answer"]}
        yield {"evidence": hit["evidence"], "done": True}
        return
    try:  # ground() 내부(추천/집계 등)에서 데이터 정합성이 어긋나면 KeyError 등이 날 수 있음
        ctx, mode, direct = ground(d, q)
    except Exception as e:
        print(f"[ground() 처리 실패: {e!r}]")  # 서버 로그에만 원인 남기고, 사용자에겐 내부 구현 노출 안 함
        yield {"token": "질문을 처리하는 중 문제가 생겼어요. 잠시 후 다시 시도해주세요."}
        yield {"evidence": "", "done": True}
        return
    yield {"meta": {"intent": mode, "evidence_n": _ev_count(ctx)}}  # 처리 의도·근거수(시스템 가시화)
    try:  # 정정 메모리 조회 실패(DB/임베딩 오류 등)해도 스트림이 done 없이 끊기지 않게
        corr = recall_corrections(d, q) if (ctx or direct) else []
    except Exception as e:
        print(f"[recall_corrections() 처리 실패: {e!r}]")
        corr = []
    if direct and not corr:                  # 즉답(스몰토크/집계/추천/상품) — LLM 생략
        yield {"token": direct}
        if ctx:                              # 스몰토크(ctx 없음)는 캐시·근거 생략
            _cache_put(q, direct, ctx, mode)
        yield {"evidence": ctx, "done": True}
        return
    if not ctx:                              # 관련 리뷰 못 찾음(엉뚱한 단정 회피)
        yield {"token": "질문과 관련된 리뷰를 찾지 못했어요. 상품명이나 배송·품질 같은 속성으로 물어봐 주세요."}
        yield {"evidence": "", "done": True}
        return
    prompt = _build(q, ctx, corr, mode)
    full = ""
    try:
        for tok in _stream_tokens(prompt):      # 백엔드(ollama/llamacpp) 공통
            full += tok
            yield {"token": tok}
    except Exception as e:
        print(f"[LLM 스트리밍 생성 실패: {e!r}]")  # 서버 로그에만 원인 남기고, 사용자에겐 내부 구현 노출 안 함
        yield {"token": "답변을 생성하는 중 문제가 생겼어요. 잠시 후 다시 시도해주세요."}
        yield {"evidence": ctx, "done": True}
        return
    # 스트리밍은 사후 언어검증을 못 하므로, 끝난 뒤 한자/영어가 섞였으면 깨끗하게 재생성해 교체
    final = full
    if _bad_lang(full):
        try:
            clean = _generate(prompt + "\n주의: 한자나 영어를 쓰지 말고 한국어 문장으로만.", 0.6, 1)
            if not _bad_lang(clean):
                yield {"replace": clean}
                final = clean
        except Exception:
            pass  # 정리용 재생성 실패는 무시 — 이미 스트리밍한 원래 답변을 그대로 씀
    try:  # 캐시 저장 실패해도 이미 스트리밍한 답변은 유효하므로 done은 반드시 보냄
        _cache_put(q, final, ctx, mode)     # 다음 동일/유사 질문은 즉시 응답
    except Exception as e:
        print(f"[_cache_put() 처리 실패: {e!r}]")
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
    try:  # ground() 내부(추천/집계 등)에서 데이터 정합성이 어긋나면 KeyError 등이 날 수 있음
        ctx, mode, direct = ground(d, q)
    except Exception as e:
        print(f"[ground() 처리 실패: {e!r}]")  # 서버 로그에만 원인 남기고, 사용자에겐 내부 구현 노출 안 함
        return "질문을 처리하는 중 문제가 생겼어요. 잠시 후 다시 시도해주세요.", ""
    corr = recall_corrections(d, q) if (ctx or direct) else []   # 교정 메모리 반영
    if direct and not corr:                   # 즉답(스몰토크/집계/추천/상품) — LLM 생략
        if ctx:
            _cache_put(q, direct, ctx, mode)
        return direct, ctx
    if not ctx:                               # 관련 리뷰 못 찾음
        return "질문과 관련된 리뷰를 찾지 못했어요. 상품명이나 배송·품질 같은 속성으로 물어봐 주세요.", ""
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
        _cache_put(q, ans, ctx, mode)
        return ans, ctx
    except Exception as e:
        print(f"[LLM 생성 실패: {e!r}]")  # 서버 로그에만 원인 남기고, 사용자에겐 내부 구현 노출 안 함
        return "답변을 생성하는 중 문제가 생겼어요. 아래 근거 리뷰를 참고해주세요.\n" + ctx, ctx


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
            # 근거충실 자기검증(빌드 시): 요약이 근거(집계·리뷰)에만 기반하는지 모델이 판정 → 실패 시 재생성
            ev = "\n".join(agg_lines + [f"- (리뷰) {t}" for t in revs])
            if not _bad_lang(text) and not _grounded(text, ev):
                cand = _generate(p + "\n주의: 근거(집계·리뷰)에 있는 내용만 쓰고 지어내지 마라.",
                                 0.3, 9, model=model)
                if not _bad_lang(cand):
                    text = cand
            if _bad_lang(text):                          # 끝내 실패 → 집계 폴백
                text = "리뷰 분석 결과, " + " ".join(
                    f"{a} 항목은 " + ("긍정적인" if v["positive"] >= v["negative"] else "아쉽다는")
                    + " 의견이 많아요." for a, v in agg.items())
        d.execute("insert or replace into product_summary(item_id, summary) values(?,?)",
                  (iid, text))
        d.commit()   # 상품마다 커밋 — 루프 전체(LLM 호출 다건)가 끝날 때까지 쓰기 락을 쥐지 않게
        n += 1
    return n


# --- 오프라인 사전계산: 리뷰 강점 → AI 광고 카피 (마케팅 산출물 자동 생성) ---
def _ad_prompt(name, strengths):
    return ("아래 상품의 '강점'을 살린 짧고 임팩트 있는 한국어 광고 문구 2개를 만들어. "
            + _RULES.replace("1~2문장으로 답해.", "각 문구는 한 줄·15자 내외로.") +
            " 과장·허위 없이 강점에 근거하고, 번호·따옴표 없이 한 줄에 하나씩 써.\n"
            f"상품: {name}\n강점: {strengths}\n광고 문구:")


def build_marketing(d, model=None):
    model = model or MODEL                      # 가볍게: 빠른 gemma3:4b
    n = 0
    for iid, name in d.execute("select item_id, name from item").fetchall():
        rows = d.execute("select aspect, sum(sentiment='positive'), sum(sentiment='negative') "
                         "from aspect_sentiment where item_id=? group by aspect", (iid,)).fetchall()
        strong = sorted(((a, p or 0, g or 0) for a, p, g in rows),
                        key=lambda x: (-(x[1] / (x[1] + x[2]) if x[1] + x[2] else 0), -x[1]))
        strong = [a for a, p, g in strong if p > g][:2]
        if not strong:
            continue
        basis = ", ".join(strong)
        text = _generate(_ad_prompt(name, basis), temp=0.7, seed=3, model=model)
        tries = 0
        while _bad_lang(text) and tries < 2:
            tries += 1
            text = _generate(_ad_prompt(name, basis) + "\n주의: 한국어로만.", 0.8, tries + 3, model=model)
        if _bad_lang(text):
            continue
        parts = []
        for l in text.splitlines():
            l = re.sub(r"^\s*\d+\s*[.)]\s*", "", l.strip(" -·\"'“”"))   # 앞 번호(1. 2.) 제거
            if l:
                parts.append(l)
        copy = " · ".join(parts[:2])
        d.execute("insert or replace into product_copy(item_id, copy, basis) values(?,?,?)",
                  (iid, copy, basis))
        d.commit()   # 상품마다 커밋 — 루프 전체(LLM 호출 다건)가 끝날 때까지 쓰기 락을 쥐지 않게
        n += 1
    return n


# --- 오프라인 사전계산: 부정 리뷰 → AI 답글 초안 (평판관리 자동화) ---
def _reply_prompt(name, text):
    return ("아래는 한 고객의 부정적인 리뷰야. 판매자 입장에서 정중하고 공감 어린 한국어 답글을 1~2문장으로 써. "
            "사과와 개선 의지를 담되 과장하지 말고, 한자·영어는 쓰지 마.\n"
            f"상품: {name}\n리뷰: {text}\n답글:")


def build_replies(d, model=None):
    model = model or MODEL          # 답글은 짧으니 빠른 gemma3:4b
    n, seen = 0, set()
    rows = d.execute("select distinct r.review_id, i.name, r.raw_text "
                     "from aspect_sentiment a join review r on a.review_id=r.review_id "
                     "join item i on a.item_id=i.item_id "
                     "where a.sentiment='negative'").fetchall()
    for rid, name, text in rows:
        if rid in seen:
            continue
        seen.add(rid)
        rep = _generate(_reply_prompt(name, text), temp=0.4, seed=5, model=model)
        tries = 0
        while _bad_lang(rep) and tries < 2:
            tries += 1
            rep = _generate(_reply_prompt(name, text) + "\n주의: 한국어로만.", 0.5, tries + 5, model=model)
        if _bad_lang(rep):
            continue
        d.execute("insert or replace into review_reply(review_id, reply) values(?,?)", (rid, rep))
        d.commit()   # 리뷰마다 커밋 — 루프 전체(LLM 호출 다건)가 끝날 때까지 쓰기 락을 쥐지 않게
        n += 1
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
