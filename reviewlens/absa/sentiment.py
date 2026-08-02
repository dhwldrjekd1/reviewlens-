from transformers import pipeline
from absa.aspect_rules import clauses, detect, strip_conj  # 속성 추출은 공유 규칙

MODEL = "matthewburke/korean_sentiment"  # KoELECTRA, NSMC 기반 (LABEL_1=긍정)

_clf = None
def clf():
    global _clf
    if _clf is None:
        # truncation=True 없으면 문장부호 없는 긴 텍스트(스팸성 리뷰 등)가 모델의 최대
        # 토큰 길이(512)를 넘겨 RuntimeError로 죽음 — SentenceTransformer 쪽은
        # max_seq_length로 이미 안전하게 잘리는 것과 동일하게 맞춤
        _clf = pipeline("text-classification", model=MODEL, truncation=True)
    return _clf

def analyze(text):
    res = []
    for s in clauses(text):
        hit = detect(s)
        if not hit:
            continue
        clean = strip_conj(s)  # 끝 연결어미 떼고 분류
        r = clf()(clean or s)[0]
        senti = "positive" if "pos" in r["label"].lower() or r["label"].endswith("1") else "negative"
        for a in hit:
            res.append((a, senti, round(r["score"], 3), s))
    return res
