"""국립국어원 속성 기반 감성 분석 말뭉치(2021) 로더 + 통계.

진짜 속성별 ABSA 학습용 — 우리 규칙 기반 속성 추출의 한계를 넘어,
'엔티티#속성' 카테고리 자체를 데이터로 학습하기 위한 실데이터.

라이선스: 국립국어원 배포(재배포 금지). 원본은 저장소에 미포함(.gitignore).
형식: document[] → 각 문서에 sentence[](문장)와 opinions[]={category, "opinion polarity"}.
우리 프로젝트(쇼핑)와 맞추기 위해 제품 도메인만 사용.
"""
import os, json, glob

# json/ 위치 후보 (루트 또는 reviewlens/data 아래)
_HERE = os.path.dirname(os.path.dirname(__file__))
JSON_DIRS = [os.path.join(_HERE, "..", "json"), os.path.join(_HERE, "data", "json"),
             os.path.join(_HERE, "json")]
SHOP_DOMAINS = {"제품 기타", "전자기기", "화장품/세정제"}  # 쇼핑 도메인만


def _files():
    for d in JSON_DIRS:
        fs = glob.glob(os.path.join(d, "*.json"))
        if fs:
            return fs
    raise FileNotFoundError("말뭉치 json을 찾지 못함 — json/ 폴더에 EXSA*.json을 넣어주세요")


def load_docs(domains=SHOP_DOMAINS):
    """[{text, opinions:[(category, polarity)]}] — 지정 도메인만."""
    out = []
    for f in _files():
        data = json.load(open(f, encoding="utf-8"))
        for doc in data["document"]:
            if domains and doc.get("domain") not in domains:
                continue
            text = " ".join(s.get("sentence_form", "") for s in doc.get("sentence", [])).strip()
            ops = [(o.get("category"), o.get("opinion polarity"))
                   for o in doc.get("opinions", []) if o.get("category")]
            if text and ops:
                out.append({"text": text, "opinions": ops})
    return out


if __name__ == "__main__":
    import sys
    from collections import Counter
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    docs = load_docs()
    cats = Counter(c for d in docs for c, _ in d["opinions"])
    pols = Counter(p for d in docs for _, p in d["opinions"])
    print(f"쇼핑 도메인 문서: {len(docs)}  | 의견(opinion) 총 {sum(len(d['opinions']) for d in docs)}")
    print(f"극성 분포: {dict(pols)}")
    print(f"카테고리 수: {len(cats)}")
    print("상위 카테고리:")
    for c, n in cats.most_common(15):
        print(f"  {c:<20} {n}")
    print(f"문서당 평균 의견 수: {sum(len(d['opinions']) for d in docs)/len(docs):.2f}")
