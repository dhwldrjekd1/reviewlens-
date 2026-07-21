"""의미검색 리트리버 — ko-sroberta 임베딩 + FAISS.

phase 1 챗봇은 질문에 들어간 단어가 상품명/속성과 글자 그대로 겹쳐야만 근거를 찾았다(키워드).
"이어폰 소리 어때?"처럼 표현이 다르면 '음질' 리뷰를 못 찾는 한계.

여기서는 리뷰 원문을 ko-sroberta로 임베딩해 FAISS 인덱스로 만들고,
질문을 같은 공간에 임베딩해 **의미가 가까운 리뷰**를 검색한다(코사인 유사도).
모델·인덱스는 한 번만 만들어 재사용(lazy 싱글톤)한다.
전부 CPU. 모델: jhgan/ko-sroberta-multitask (768차원, 경량).
"""
import os
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

MODEL_NAME = "jhgan/ko-sroberta-multitask"
# HF_HOME이 다른 값으로 설정된 세션(예: Docker)에서도, 이미 기본 캐시에 받아둔 모델을
# 재다운로드하지 않도록 캐시 위치를 명시 고정.
_CACHE = os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub")
_model = None


def get_model():
    """ko-sroberta 로드(최초 1회). import 시점이 아니라 호출 시점에 로드."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        kw = {"cache_folder": _CACHE} if os.path.isdir(_CACHE) else {}
        _model = SentenceTransformer(MODEL_NAME, **kw)
    return _model


class ReviewIndex:
    """리뷰 원문 FAISS 인덱스. 코사인 유사도 = 정규화 임베딩의 내적(IndexFlatIP)."""

    def __init__(self, rows):
        # rows: [(review_id, item_id, name, text), ...]
        import faiss
        self.meta = rows
        texts = [r[3] for r in rows]
        emb = get_model().encode(texts, normalize_embeddings=True).astype("float32")
        self.index = faiss.IndexFlatIP(emb.shape[1])
        self.index.add(emb)

    def search(self, query, k=3):
        qv = get_model().encode([query], normalize_embeddings=True).astype("float32")
        scores, ids = self.index.search(qv, min(k, len(self.meta)))
        out = []
        for i, s in zip(ids[0], scores[0]):
            rid, iid, name, text = self.meta[int(i)]
            out.append({"review_id": rid, "item_id": iid, "name": name,
                        "text": text, "score": float(s)})
        return out


# DB 기준 인덱스 캐시 (리뷰 수가 바뀌면 새로 빌드)
_index = None
_index_n = -1


def get_index(db):
    global _index, _index_n
    rows = db.execute(
        "select r.review_id, r.item_id, i.name, r.raw_text "
        "from review r join item i using(item_id)").fetchall()
    if _index is None or _index_n != len(rows):
        _index = ReviewIndex(rows)
        _index_n = len(rows)
    return _index


def search(db, query, k=3):
    return get_index(db).search(query, k)


# 비교용 키워드 베이스라인: 질문과 리뷰 원문의 글자 n-gram 겹침 수
def keyword_search(db, query, k=3):
    rows = db.execute("select r.review_id, i.name, r.raw_text "
                      "from review r join item i using(item_id)").fetchall()
    grams = {query[i:i+2] for i in range(len(query) - 1)}  # 2-gram
    scored = [(sum(g in text for g in grams), name, text) for _, name, text in rows]
    scored.sort(reverse=True)
    return [(s, n, t) for s, n, t in scored[:k] if s > 0]


if __name__ == "__main__":
    import sys, db
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    d = db.get_db()
    # 질문에 정답 리뷰의 단어가 안 겹치는 '표현 다른' 질문들 → 키워드는 약하고 의미검색은 강함
    for q in ["이어폰 소리 괜찮아?", "물건 늦게 오나요?", "환불 문의하면 잘 받아주나"]:
        print(f"\nQ: {q}")
        kw = keyword_search(d, q, 1)
        print(f"  [키워드 top1] {kw[0][1]+': '+kw[0][2] if kw else '(겹치는 리뷰 없음)'}")
        h = search(d, q, 1)[0]
        print(f"  [의미   top1] {h['name']}: {h['text']}  (sim {h['score']:.2f})")
