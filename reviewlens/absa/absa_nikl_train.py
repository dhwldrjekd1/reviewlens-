"""NIKL 속성 카테고리 탐지(ACD) 학습 — 진짜 '속성 추출'을 데이터로 학습.

우리 phase 1~2의 속성 추출은 키워드 규칙(aspect_rules)이었다. 한계: 사전에 없는 표현은 못 잡음.
여기서는 국립국어원 ABSA 말뭉치(쇼핑)로 **'엔티티#속성' 카테고리 자체를 학습**한다(멀티라벨).
CPU 제약상 전체 파인튜닝 대신 linear probing: ko-sroberta 임베딩(동결) → OneVsRest 로지스틱.

데이터는 라이선스상 비공개(.gitignore). 결과(F1)와 코드만 공개.
"""
import os, sys
os.environ.setdefault("HF_HUB_OFFLINE", "1")
import numpy as np
from absa import absa_nikl
from chat import retriever

SEED = 42
MIN_COUNT = 20   # 표본 너무 적은 카테고리는 제외
MODELS = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    from collections import Counter
    from sklearn.multiclass import OneVsRestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import MultiLabelBinarizer
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import f1_score
    import joblib

    docs = absa_nikl.load_docs()
    cc = Counter(c for d in docs for c, _ in d["opinions"])
    cats = sorted(c for c, n in cc.items() if n >= MIN_COUNT)
    catset = set(cats)

    texts, labels = [], []
    for d in docs:
        lab = {c for c, _ in d["opinions"] if c in catset}
        if lab:
            texts.append(d["text"])
            labels.append(lab)
    print(f"문서 {len(texts)}  카테고리 {len(cats)}개 (출현 {MIN_COUNT}회 이상)")

    mlb = MultiLabelBinarizer(classes=cats)
    Y = mlb.fit_transform(labels)

    os.makedirs(MODELS, exist_ok=True)
    cache = os.path.join(MODELS, f"nikl_emb_{len(texts)}.npy")
    if os.path.exists(cache):
        X = np.load(cache)
    else:
        X = retriever.get_model().encode(texts, batch_size=64, normalize_embeddings=True,
                                         show_progress_bar=False).astype("float32")
        np.save(cache, X)

    Xtr, Xte, Ytr, Yte = train_test_split(X, Y, test_size=0.2, random_state=SEED)
    clf = OneVsRestClassifier(LogisticRegression(max_iter=1000, C=1.0))
    clf.fit(Xtr, Ytr)
    pred = clf.predict(Xte)

    micro = f1_score(Yte, pred, average="micro", zero_division=0)
    macro = f1_score(Yte, pred, average="macro", zero_division=0)

    # 불균형 보정판(class_weight=balanced): 희소 카테고리(macro)↑ ↔ 전체(micro)↓ 트레이드오프
    clf_b = OneVsRestClassifier(LogisticRegression(max_iter=1000, class_weight="balanced")).fit(Xtr, Ytr)
    pb = clf_b.predict(Xte)
    bmi = f1_score(Yte, pb, average="micro", zero_division=0)
    bma = f1_score(Yte, pb, average="macro", zero_division=0)

    # 베이스라인: train에서 가장 빈번한 2개 카테고리를 모든 문서에 예측
    freq = Ytr.sum(axis=0)
    top2 = np.argsort(-freq)[:2]
    base = np.zeros_like(Yte)
    base[:, top2] = 1
    bmicro = f1_score(Yte, base, average="micro", zero_division=0)

    print(f"\n== 속성 카테고리 탐지(ACD), 테스트 {len(Yte)}문서 ==")
    print(f"  빈도 베이스라인(top2)       micro-F1 {bmicro:.3f}")
    print(f"  linear probing            micro-F1 {micro:.3f}  macro-F1 {macro:.3f}")
    print(f"  linear probing(balanced)  micro-F1 {bmi:.3f}  macro-F1 {bma:.3f}  (희소 카테고리 보정)")

    joblib.dump((clf, mlb), os.path.join(MODELS, "absa_acd.joblib"))
    print("\n  저장: models/absa_acd.joblib")

    # 예시 예측
    print("\n== 예측 예시 ==")
    for i in range(min(3, len(Xte))):
        got = [cats[j] for j in range(len(cats)) if pred[i][j]]
        true = [cats[j] for j in range(len(cats)) if Yte[i][j]]
        print(f"  정답 {true}\n  예측 {got}\n")


if __name__ == "__main__":
    main()
