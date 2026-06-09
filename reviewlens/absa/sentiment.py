import os
os.environ.setdefault("HF_HOME", r"D:\hf-cache")  # 모델 캐시는 D드라이브로
from transformers import pipeline
from absa.aspect_rules import clauses, detect, strip_conj  # 속성 추출은 공유 규칙

MODEL = "matthewburke/korean_sentiment"  # KoELECTRA, NSMC 기반 (LABEL_1=긍정)

_clf = None
def clf():
    global _clf
    if _clf is None:
        _clf = pipeline("text-classification", model=MODEL)
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
