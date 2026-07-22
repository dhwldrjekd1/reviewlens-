from fastapi import APIRouter
from api.deps import d

# 대시보드·분석 API (실데이터 집계)
router = APIRouter(prefix="/api", tags=["board"])


@router.get("/board")
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
            "select distinct r.review_id, r.raw_text, i.category from aspect_sentiment a "
            "join review r on a.review_id=r.review_id "
            "join item i on a.item_id=i.item_id where a.sentiment='negative' limit 4"):
        rep = d.execute("select reply from review_reply where review_id=?", (rid,)).fetchone()
        negq.append({"text": t, "meta": c, "reply": rep[0] if rep else ""})
    posq = [{"text": t, "meta": c} for t, c in d.execute(
        "select r.raw_text, i.category from review r join item i using(item_id) where r.review_id in "
        "(select review_id from aspect_sentiment group by review_id having sum(sentiment='negative')=0) limit 3")]
    return {"kpi": kpi, "aspects": asp, "categories": cats, "issues": issues,
            "products": prods, "cat_avg": cat_avg, "quotes": {"pos": posq, "neg": negq}}
