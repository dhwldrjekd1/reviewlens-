"""ABSA 분석기 — 규칙 속성 추출 + 학습된 감성 분류기.

sentiment.py(규칙+KoELECTRA)와 '속성 추출'은 동일(aspect_rules 공유)하지만,
'감성 판정'을 sentiment_finetune.py로 학습한 분류기(ko-sroberta 임베딩 + 로지스틱 헤드)로 교체.
→ 속성 추출을 고정한 채 감성 모델만 바꿔 eval로 직접 비교할 수 있다.

학습 분류기가 없으면(models/sentiment_head.joblib) 안내 후 종료.
analyze()는 다른 분석기와 같은 형식 (aspect, sentiment, confidence, evidence)을 반환.
"""
import os
from absa import aspect_rules
from chat import retriever

HEAD = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models", "sentiment_head.joblib")
_head = None


def head():
    global _head
    if _head is None:
        if not os.path.exists(HEAD):
            raise FileNotFoundError("학습 분류기 없음 → 먼저 (reviewlens/ 에서) `python -m train.sentiment_finetune` 실행")
        import joblib
        _head = joblib.load(HEAD)
    return _head


def _predict(texts):
    emb = retriever.get_model().encode(texts, normalize_embeddings=True).astype("float32")
    return head().predict_proba(emb)[:, 1]  # 긍정 확률


def analyze(text):
    # 1) 규칙으로 속성 있는 절만 추림
    items = []
    for s in aspect_rules.clauses(text):
        hit = aspect_rules.detect(s)
        if hit:
            items.append((s, aspect_rules.strip_conj(s) or s, hit))
    if not items:
        return []
    # 2) 학습 분류기로 절 감성 일괄 예측
    probs = _predict([clean for _, clean, _ in items])
    res = []
    for (s, _, hit), p in zip(items, probs):
        senti = "positive" if p >= 0.5 else "negative"
        for a in hit:
            res.append((a, senti, round(float(p), 3), s))
    return res


if __name__ == "__main__":
    import sys
    from store import db
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    for t, in db.get_db().execute("select raw_text from review limit 5"):
        print(f"\n{t}")
        for a, s, c, ev in analyze(t):
            print(f"  {a}/{s} ({c})  ← {ev}")
