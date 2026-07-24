"""Phase 2 추천 — 협업필터링(implicit ALS) + 감성 블렌딩 + 콜드스타트 fallback.

phase 1 recommend_live.py는 '감성 점수 스코어러'(상호작용 없이도 동작, 설명가능)였다.
여기서는 그 위에 실제 협업필터링 신호를 얹는다.

  · 따뜻한 유저(상호작용 보유) → ALS 협업필터링 (+ 감성 스코어 블렌딩)
  · 차가운 유저(상호작용 없음) → 감성 스코어러로 fallback (콜드스타트)

원래 기획은 LightFM(하이브리드)이었으나, LightFM은 유지보수가 중단돼
Python 3.12 + 최신 setuptools/numpy 2.x 환경에서 빌드가 불가능하다.
그래서 동일한 CPU-네이티브 CF를 유지보수되는 `implicit`(ALS)로 구현하고,
LightFM의 '아이템 사이드피처(감성)' 역할은 감성 스코어러를 블렌딩해 대체한다.

상호작용 로그가 없어, 잠재 취향 구조를 가진 합성 상호작용 시뮬레이터로 학습·평가한다.
(데이터 로더만 바꾸면 Amazon-Reviews-2023 같은 실데이터로 교체 가능.)
평가는 누수를 피하려 **시간 기반 분할**을 쓰고, popularity 베이스라인과 비교한다.
"""
import os, sys
# implicit(OpenBLAS)는 멀티스레드 BLAS와 충돌 경고 → 결정적·조용하게 단일 스레드로
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import numpy as np
from scipy.sparse import csr_matrix
from implicit.als import AlternatingLeastSquares

ASPECTS = ["배송", "품질", "가격", "포장", "디자인", "CS"]
CATEGORIES = ["전자", "주방", "패션"]
SEED = 42


# ---------------------------------------------------------------------------
# 1. 합성 상호작용 시뮬레이터 (문서화된 생성 과정)
# ---------------------------------------------------------------------------
def simulate(n_users=600, n_items=160, eps_pop=0.1, gamma=6.0, span=0.3, rng=None):
    """잠재 취향 → 상호작용 로그. CF가 회복해야 할 '정답 구조'를 심어 둔다.

    - 아이템: 속성별 만족도 q_i ∈ [0,1]^6 (= 긍정비율), 카테고리, 기본 인기도 b_i
    - 유저:   속성 선호 가중치 w_u (dirichlet, 소수 속성에 쏠림), 선호 카테고리, 가입시점 t0
    - 적합도 fit_ui = w_u·q_i (+ 카테고리 매치) → z-정규화 후 softmax = 개인화 분포
    - 실제 선택 = (1-ε)·개인화 + ε·전역인기  → 개인화가 주, 인기 편향이 부
      (ε만큼 인기 편향이 있어 popularity 베이스라인도 무의미하진 않게)
    - 시점: 유저 가입시점 t0_u + 짧은 활동기간. t0가 늦은 유저는 전부 test → 콜드스타트.
    """
    rng = rng or np.random.default_rng(SEED)

    q = rng.beta(2.0, 2.0, size=(n_items, len(ASPECTS)))
    item_cat = rng.integers(0, len(CATEGORIES), size=n_items)
    base_pop = rng.beta(1.6, 5.0, size=n_items)          # 소수 아이템에 인기 집중
    p_pop = base_pop / base_pop.sum()

    w = rng.dirichlet(np.full(len(ASPECTS), 0.4), size=n_users)   # 2~3개 속성에 쏠림
    user_cat = rng.integers(0, len(CATEGORIES), size=n_users)
    t0 = rng.random(n_users)                              # 유저 가입시점 ∈ [0,1)

    rows, cols, times = [], [], []
    for u in range(n_users):
        fit = w[u] @ q.T + 0.25 * (item_cat == user_cat[u])
        z = (fit - fit.mean()) / (fit.std() + 1e-9)       # 유저 내 정규화 → 개인화 대비 확보
        p_personal = np.exp(gamma * z); p_personal /= p_personal.sum()
        p = (1 - eps_pop) * p_personal + eps_pop * p_pop  # 개인화 주 + 인기 부
        n_u = int(rng.integers(6, 26))
        picks = rng.choice(n_items, size=min(n_u, n_items), replace=False, p=p)
        for it in picks:
            rows.append(u); cols.append(int(it))
            times.append(float(min(0.999, t0[u] + rng.uniform(0, span))))
    return {
        "n_users": n_users, "n_items": n_items,
        "user": np.array(rows), "item": np.array(cols), "time": np.array(times),
        "item_aspect": q, "item_cat": item_cat, "user_pref": w, "user_cat": user_cat,
    }


# ---------------------------------------------------------------------------
# 1b. 실데이터 로더 — CF 백본을 공개 벤치마크로 검증 (합성 과적합이 아님을 확인)
#     MovieLens엔 '속성 만족도' 라벨이 없어 감성 블렌딩은 검증 불가 → CF(pop vs ALS)만.
#     (속성 사이드피처가 있는 공개 쇼핑 데이터가 없어서, 블렌딩은 합성으로 유지한다.)
# ---------------------------------------------------------------------------
def load_movielens(path=None):
    import csv
    path = path or os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "ml",
                                "ml-latest-small", "ratings.csv")
    uid, iid, ts = [], [], []
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if float(r["rating"]) >= 4.0:            # 평점>=4를 암묵 양성 피드백으로
                uid.append(r["userId"]); iid.append(r["movieId"]); ts.append(float(r["timestamp"]))
    umap = {u: k for k, u in enumerate(sorted(set(uid)))}   # 0..n-1 재색인
    imap = {i: k for k, i in enumerate(sorted(set(iid)))}
    t = np.array(ts, dtype=float)
    return {
        "n_users": len(umap), "n_items": len(imap),
        "user": np.array([umap[u] for u in uid]),
        "item": np.array([imap[i] for i in iid]),
        "time": (t - t.min()) / (t.max() - t.min() + 1e-9),  # [0,1]로 정규화
        "item_aspect": None, "user_pref": None, "item_cat": None, "user_cat": None,
    }


# ---------------------------------------------------------------------------
# 2. 시간 기반 분할 (랜덤 분할은 미래→과거 누수)
# ---------------------------------------------------------------------------
def time_split(data, q=0.8):
    cut = np.quantile(data["time"], q)
    train = data["time"] <= cut
    test = ~train
    return train, test


def loo_split(data):
    """유저별 leave-last-out — 각 유저의 '시간순 마지막' 상호작용을 test로.
    CF 표준 평가. 실데이터(MovieLens)는 유저가 특정 시점에 몰려, 전역 시간분할이면
    유저 전체가 train/test로 쏠려 warm 유저가 거의 안 남기 때문에 이 방식을 쓴다."""
    order = np.argsort(data["time"], kind="stable")     # 시간 오름차순
    last = {}
    for idx in order:
        last[int(data["user"][idx])] = int(idx)         # 각 유저의 마지막 인덱스로 덮어씀
    test = np.zeros(len(data["user"]), dtype=bool)
    test[list(last.values())] = True
    return ~test, test


def build_csr(data, mask, alpha=20.0):
    # implicit ALS는 행렬값을 신뢰도(confidence)로 해석 → 암묵 피드백은 가중을 키운다
    vals = np.full(mask.sum(), alpha, dtype=np.float32)
    return csr_matrix((vals, (data["user"][mask], data["item"][mask])),
                      shape=(data["n_users"], data["n_items"]))


# ---------------------------------------------------------------------------
# 3. 스코어러들
# ---------------------------------------------------------------------------
def sentiment_scores(prefs_vec, item_aspect):
    """감성 스코어러: 유저 속성 선호 · 아이템 속성 만족도. recommend_live.py의 일반화."""
    return item_aspect @ prefs_vec


def _minmax(x):
    lo, hi = x.min(), x.max()
    return (x - lo) / (hi - lo) if hi > lo else np.zeros_like(x)


def blended_scores(als_row, prefs_vec, item_aspect, alpha=0.7):
    """ALS(협업) + 감성(콘텐츠) 블렌딩. alpha=협업 비중."""
    return alpha * _minmax(als_row) + (1 - alpha) * _minmax(sentiment_scores(prefs_vec, item_aspect))


# ---------------------------------------------------------------------------
# 4. 평가 지표 (Recall@K, NDCG@K)
# ---------------------------------------------------------------------------
def recall_at_k(ranked, relevant, k):
    hits = sum(1 for i in ranked[:k] if i in relevant)
    return hits / len(relevant) if relevant else 0.0


def ndcg_at_k(ranked, relevant, k):
    dcg = sum(1.0 / np.log2(rank + 2) for rank, i in enumerate(ranked[:k]) if i in relevant)
    ideal = sum(1.0 / np.log2(rank + 2) for rank in range(min(k, len(relevant))))
    return dcg / ideal if ideal else 0.0


def topk(scores, exclude, k):
    s = scores.copy()
    s[list(exclude)] = -np.inf
    return np.argpartition(-s, k)[:k][np.argsort(-s[np.argpartition(-s, k)[:k]])]


# ---------------------------------------------------------------------------
# 5. 학습 + 평가
# ---------------------------------------------------------------------------
def evaluate(data, train, test, k=10):
    train_csr = build_csr(data, train)

    model = AlternatingLeastSquares(factors=48, regularization=0.05,
                                    iterations=25, random_state=SEED)
    model.fit(train_csr, show_progress=False)
    U, V = model.user_factors, model.item_factors          # (users,f), (items,f)

    # 인기도 베이스라인: train 상호작용 수
    pop = np.asarray(train_csr.sum(axis=0)).ravel()

    # 유저별 train/test 아이템 집합
    tr_items = [set() for _ in range(data["n_users"])]
    for u, i in zip(data["user"][train], data["item"][train]):
        tr_items[u].add(int(i))
    te_items = [set() for _ in range(data["n_users"])]
    for u, i in zip(data["user"][test], data["item"][test]):
        te_items[u].add(int(i))

    has_aspect = data.get("item_aspect") is not None    # 실데이터는 속성 라벨 없음 → 블렌딩 생략
    warm, cold = {"pop": [], "als": [], "blend": []}, {"pop": [], "sent": []}

    for u in range(data["n_users"]):
        # test 정답 = test 상호작용 중 train에 없던 신규 아이템
        rel = te_items[u] - tr_items[u]
        if not rel:
            continue
        prefs = data["user_pref"][u] if has_aspect else None
        if tr_items[u]:  # 따뜻한 유저 → CF
            als_row = U[u] @ V.T
            scorers = [("pop", pop), ("als", als_row)]
            if has_aspect:
                scorers.append(("blend", blended_scores(als_row, prefs, data["item_aspect"])))
            for name, sc in scorers:
                r = topk(sc, tr_items[u], k)
                warm[name].append((recall_at_k(r, rel, k), ndcg_at_k(r, rel, k)))
        else:            # 차가운 유저 → 감성 fallback vs 인기도
            scorers = [("pop", pop)]
            if has_aspect:
                scorers.append(("sent", sentiment_scores(prefs, data["item_aspect"])))
            for name, sc in scorers:
                r = topk(sc, set(), k)
                cold[name].append((recall_at_k(r, rel, k), ndcg_at_k(r, rel, k)))

    return model, train_csr, warm, cold


def _avg(rows):
    a = np.array(rows)
    return (a[:, 0].mean(), a[:, 1].mean()) if len(a) else (0.0, 0.0)


# ---------------------------------------------------------------------------
# 6. 데모
# ---------------------------------------------------------------------------
def main(source="synthetic"):
    if hasattr(sys.stdout, "reconfigure"):   # Windows 콘솔(cp949) 한글/대시 깨짐 방지
        sys.stdout.reconfigure(encoding="utf-8")
    K = 10
    data = load_movielens() if source == "movielens" else simulate()
    has_aspect = data.get("item_aspect") is not None
    # 실데이터는 유저별 leave-last-out(시간순), 합성은 전역 시간분할(설계상 유저 활동기간이 컷을 가로지름)
    train, test = loo_split(data) if source == "movielens" else time_split(data, q=0.8)
    tag = "MovieLens-small 실데이터" if source == "movielens" else "합성 시뮬레이션"
    print(f"[{tag}] 유저 {data['n_users']}  아이템 {data['n_items']}  "
          f"상호작용 {len(data['user'])}  (train {int(train.sum())} / test {int(test.sum())})")

    model, train_csr, warm, cold = evaluate(data, train, test, k=K)

    print(f"\n== 따뜻한 유저 (상호작용 보유) — Recall@{K} / NDCG@{K} ==")
    warm_labels = [("pop", "popularity (baseline)"), ("als", "implicit ALS (CF)")]
    if has_aspect:
        warm_labels.append(("blend", "ALS + 감성 블렌딩"))
    for name, label in warm_labels:
        r, n = _avg(warm[name])
        print(f"  {label:<26} Recall {r:.3f}  NDCG {n:.3f}  (n={len(warm[name])})")

    print(f"\n== 차가운 유저 (상호작용 0, 콜드스타트) — Recall@{K} / NDCG@{K} ==")
    cold_labels = [("pop", "popularity (baseline)")]
    if has_aspect:
        cold_labels.append(("sent", "감성 스코어러 fallback"))
    for name, label in cold_labels:
        r, n = _avg(cold[name])
        print(f"  {label:<26} Recall {r:.3f}  NDCG {n:.3f}  (n={len(cold[name])})")

    if not has_aspect:   # 실데이터: 속성 라벨이 없어 CF 백본만 검증
        print("\n(MovieLens엔 속성 만족도 라벨이 없어 CF 백본만 검증 — 감성 블렌딩은 합성 데이터에서 평가)")
        return

    # 설명가능 추천 예시 (따뜻한 유저 1명)
    u = next(i for i in range(data["n_users"]) if train_csr[i].nnz)
    prefs = data["user_pref"][u]
    als_row = model.user_factors[u] @ model.item_factors.T
    seen = set(train_csr[u].indices)
    recs = topk(blended_scores(als_row, prefs, data["item_aspect"]), seen, 3)
    top_asp = [ASPECTS[a] for a in np.argsort(-prefs)[:2]]
    print(f"\n== 추천 예시 (유저 {u}, 중시 속성: {', '.join(top_asp)}) ==")
    for it in recs:
        q = data["item_aspect"][it]
        why = ", ".join(f"{ASPECTS[a]} 만족도 {int(q[a]*100)}%" for a in np.argsort(-prefs)[:2])
        print(f"  아이템 {it:>3} ({CATEGORIES[data['item_cat'][it]]})  — {why}")


if __name__ == "__main__":
    # reviewlens/ 에서 python -m recommend.recommender            → 합성(감성 블렌딩까지)
    # reviewlens/ 에서 python -m recommend.recommender movielens  → 실데이터 CF 백본 검증(pop vs ALS)
    src = "movielens" if (len(sys.argv) > 1 and sys.argv[1] == "movielens") else "synthetic"
    main(src)
