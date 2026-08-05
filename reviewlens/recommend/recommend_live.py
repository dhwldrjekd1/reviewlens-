from store import db

# 상품별 속성 긍정비율 = 감성 저장소에서 뽑은 추천 피처
def item_aspects(d):
    s = {}
    for iid, asp, pr in d.execute("""
        select item_id, aspect, sum(sentiment='positive')*1.0/count(*)
        from aspect_sentiment group by item_id, aspect""").fetchall():
        s.setdefault(iid, {})[asp] = pr
    return s

# 유저가 중시하는 속성 가중치로 점수화 (구매기록 없어도 됨 = 콜드스타트 OK)
def recommend(d, prefs, k=3):
    names = dict(d.execute("select item_id, name from item").fetchall())
    items = item_aspects(d)
    out = []
    for iid, asp in items.items():
        if iid not in names:   # item 테이블엔 없는데 aspect_sentiment엔 남아있는 상품(재적재 등) — 건너뜀
            continue
        score = sum(w * asp.get(a, 0.5) for a, w in prefs.items())  # 없는 속성은 0.5(중립)
        why = [(a, asp[a]) for a in sorted(prefs, key=lambda a: -prefs[a]) if a in asp][:2]
        out.append((score, names[iid], why))
    out.sort(reverse=True)
    return out[:k]

if __name__ == "__main__":
    d = db.get_db()
    users = {"배송·가격 중시": {"배송": 1, "가격": 1},
             "품질·디자인 중시": {"품질": 1, "디자인": 1}}
    for u, prefs in users.items():
        print(f"\n[{u}] 추천")
        for score, name, why in recommend(d, prefs):
            reason = ", ".join(f"{a} 만족도 {int(p*100)}%" for a, p in why)
            print(f"  {name:<16} score {score:.2f}  — {reason}")
