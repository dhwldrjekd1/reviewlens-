import csv, os
from absa import sentiment

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

def clf_preds():  # 규칙 속성 + 학습된 감성 분류기 (속성 추출은 규칙과 동일)
    from absa import absa_clf
    rows = load("reviews.csv", ["review_id", "text"])
    return {(int(rid), a, s) for rid, t in rows for a, s, _, _ in absa_clf.analyze(t)}

def llm_preds():  # LLM(Ollama) 직접 실행 — 느려서 'llm' 인자 줄 때만
    from absa import absa_llm
    out = set()
    for rid, t in load("reviews.csv", ["review_id", "text"]):
        try:  # 리뷰 1건 실패해도 전체가 죽지 않게
            for a, s, _, _ in absa_llm.analyze(t):
                out.add((int(rid), a, s))
        except Exception as e:
            print(f"[리뷰 {rid} 분석 실패, 건너뜀: {e}]")  # 원인 없이 조용히 건너뛰면 인프라 실패를
            # 모델 품질 저하로 오인하기 쉬움(pipeline.py와 동일 패턴)
    return out

if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    g = gold()
    print(f"정답(gold): {len(g)}개\n")
    runs = [("규칙+KoELECTRA", rule_preds), ("규칙+학습분류기", clf_preds)]
    if "llm" in sys.argv:  # python eval.py llm  → LLM까지 (CPU에서 느림)
        runs.append(("LLM qwen2.5:3b", llm_preds))
    for name, fn in runs:
        try:
            pred = fn()
        except Exception as e:
            print(f"{name:<16} 건너뜀: {e}")
            continue
        p, r, f = prf(pred, g)
        print(f"{name:<16} 예측 {len(pred):>3}개  정밀도 {p:.2f}  재현율 {r:.2f}  F1 {f:.2f}")
