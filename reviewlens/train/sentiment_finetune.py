"""감성 분류기 학습 (linear probing) — 네이버쇼핑 리뷰 200k, CPU.

ABSA 파인튜닝의 현실적 1단계. gold 39개는 *평가용*이라 학습엔 부족 → 공개 도메인 데이터로 학습.
네이버쇼핑 리뷰(평점 1~5)로 **문장 긍/부정 분류기**를 학습한다.

CPU 제약 때문에 전체 파인튜닝(인코더 weight 갱신) 대신 **linear probing**:
  · ko-sroberta로 문장 임베딩(인코더 동결) → 임베딩 캐시
  · 그 위에 가벼운 로지스틱 회귀 '헤드'만 학습
인코더 forward만 한 번 돌리면 되므로 CPU로 수 분 내 학습된다.

한계(솔직히): 이 데이터는 문장 단위 감성이라 **속성 구분은 학습 안 됨**.
즉 ABSA의 '감성 분류' 정확도를 올리는 단계이고, '속성 추출'은 규칙/LLM이 담당.
진짜 속성별 파인튜닝은 속성 라벨 데이터(CARBD-Ko 등)가 필요 — 다음 단계.
"""
import os, sys, urllib.request
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import numpy as np

HERE = os.path.dirname(os.path.dirname(__file__))
DATA = os.path.join(HERE, "data", "naver_shopping.txt")
URL = "https://raw.githubusercontent.com/bab2min/corpus/master/sentiment/naver_shopping.txt"
MODELS = os.path.join(HERE, "models")
SEED = 42


def download():
    if os.path.exists(DATA):
        return
    print("네이버쇼핑 데이터 다운로드 중...")
    os.makedirs(os.path.dirname(DATA), exist_ok=True)
    urllib.request.urlretrieve(URL, DATA)


def load(n_per_class=8000, rng=None):
    """평점 1~5 → 4·5=긍정(1), 1·2=부정(0). 클래스 균형 맞춰 표본 추출."""
    rng = rng or np.random.default_rng(SEED)
    pos, neg = [], []
    with open(DATA, encoding="utf-8") as f:
        for line in f:
            r, _, text = line.rstrip("\n").partition("\t")
            if not text:
                continue
            r = int(r)
            (pos if r >= 4 else neg if r <= 2 else []).append(text)
    pos = rng.permutation(pos)[:n_per_class]
    neg = rng.permutation(neg)[:n_per_class]
    texts = list(pos) + list(neg)
    labels = np.array([1] * len(pos) + [0] * len(neg))
    idx = rng.permutation(len(texts))
    return [texts[i] for i in idx], labels[idx]


def embed_cached(texts, tag):
    """ko-sroberta 임베딩 (인코더 동결). 캐시 있으면 재사용."""
    os.makedirs(MODELS, exist_ok=True)
    cache = os.path.join(MODELS, f"emb_{tag}_{len(texts)}.npy")
    if os.path.exists(cache):
        return np.load(cache)
    from chat import retriever  # ko-sroberta 싱글톤 재사용
    emb = retriever.get_model().encode(texts, batch_size=64, show_progress_bar=False,
                                       normalize_embeddings=True).astype("float32")
    np.save(cache, emb)
    return emb


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score, precision_recall_fscore_support
    import joblib

    download()
    texts, y = load()
    print(f"데이터: 긍정 {int(y.sum())} / 부정 {int((1-y).sum())} (균형 표본)")

    X = embed_cached(texts, "naver")
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=SEED, stratify=y)

    # 헤드(로지스틱 회귀)만 학습 — 인코더는 동결
    clf = LogisticRegression(max_iter=1000, C=1.0)
    clf.fit(Xtr, ytr)

    pred = clf.predict(Xte)
    acc = accuracy_score(yte, pred)
    p, r, f, _ = precision_recall_fscore_support(yte, pred, average="binary")
    base = max(yte.mean(), 1 - yte.mean())  # 다수클래스 베이스라인
    print(f"\n== 테스트 ({len(yte)}건) ==")
    print(f"  다수클래스 baseline 정확도 {base:.3f}")
    print(f"  linear probing 정확도 {acc:.3f}  정밀도 {p:.3f}  재현율 {r:.3f}  F1 {f:.3f}")

    os.makedirs(MODELS, exist_ok=True)
    joblib.dump(clf, os.path.join(MODELS, "sentiment_head.joblib"))
    print("\n  분류기 저장: models/sentiment_head.joblib")

    # 우리 리뷰에 적용 예시 (도메인 전이 확인)
    from store import db
    rows = db.get_db().execute("select raw_text, rating from review limit 6").fetchall()
    demo = embed_cached([t for t, _ in rows], "demo")
    probs = clf.predict_proba(demo)[:, 1]
    print("\n== 우리 리뷰 예측 예시 ==")
    for (t, rt), pr in zip(rows, probs):
        lab = "긍정" if pr >= 0.5 else "부정"
        print(f"  [{lab} {pr:.2f}] (별점{rt}) {t[:40]}")


if __name__ == "__main__":
    main()
