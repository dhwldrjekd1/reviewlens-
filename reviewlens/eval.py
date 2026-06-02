import csv, os
import db, sentiment

D = os.path.dirname(__file__)

def load(name, cols):
    with open(os.path.join(D, "data", name), encoding="utf-8") as f:
        return [tuple(r[c] for c in cols) for r in csv.DictReader(f)]

def gold():
    return {(int(rid), a, s) for rid, a, s in load("gold.csv", ["review_id", "aspect", "sentiment"])}

# (리뷰id, 속성, 감성) 삼중일치 기준 P/R/F1
def prf(pred, g):
    tp = len(pred & g)
    p = tp / len(pred) if pred else 0
    r = tp / len(g) if g else 0
    return p, r, (2*p*r/(p+r) if p+r else 0)

def rule_preds():
    rows = load("reviews.csv", ["review_id", "text"])
    return {(int(rid), a, s) for rid, t in rows for a, s, _, _ in sentiment.analyze(t)}

def llm_preds(d):  # 이미 적재된 LLM 결과 재사용
    return {(rid, a, s) for rid, a, s in d.execute("select review_id, aspect, sentiment from aspect_sentiment")}

def clf_preds():  # 규칙 속성 + 학습된 감성 분류기 (속성 추출은 규칙과 동일)
    import absa_clf
    rows = load("reviews.csv", ["review_id", "text"])
    return {(int(rid), a, s) for rid, t in rows for a, s, _, _ in absa_clf.analyze(t)}

if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    g = gold()
    d = db.get_db()
    print(f"정답(gold): {len(g)}개\n")
    for name, fn in [("규칙+KoELECTRA", rule_preds),
                     ("LLM qwen2.5:3b", lambda: llm_preds(d)),
                     ("규칙+학습분류기", clf_preds)]:
        try:
            pred = fn()
        except Exception as e:
            print(f"{name:<16} 건너뜀: {e}")
            continue
        p, r, f = prf(pred, g)
        print(f"{name:<16} 예측 {len(pred):>2}개  정밀도 {p:.2f}  재현율 {r:.2f}  F1 {f:.2f}")
