import os
os.environ.setdefault("HF_HOME", r"D:\hf-cache")  # 모델 캐시는 D드라이브로
import re
from transformers import pipeline

MODEL = "matthewburke/korean_sentiment"  # KoELECTRA, NSMC 기반 (LABEL_1=긍정)

aspects = {
    "배송": ["배송", "도착", "택배", "하루만"],
    "품질": ["품질", "성능", "음질", "튼튼", "내구", "마감", "보온", "밑창", "연결"],
    "가격": ["가격", "가성비", "비싸", "저렴", "값", "부담"],
    "포장": ["포장", "박스", "흠집", "파손"],
    "디자인": ["디자인", "예쁘", "예뻐", "이쁘", "색상", "깔끔"],
    "CS": ["문의", "응대", "교환", "환불", "고객"],
}

_clf = None
def clf():
    global _clf
    if _clf is None:
        _clf = pipeline("text-classification", model=MODEL)
    return _clf

# 문장 → 절 단위로 쪼갬 (지만/는데/고 등에서 끊어 속성별 감성이 안 섞이게)
def clauses(text):
    out = []
    for s in re.split(r"[.!?\n]", text):
        for c in re.split(r"(?<=지만)\s*|(?<=는데)\s*|(?<=으나)\s*|(?<=고)\s+|(?<=며)\s+", s):
            if c.strip():
                out.append(c.strip())
    return out

def analyze(text):
    res = []
    for s in clauses(text):
        hit = [a for a, kws in aspects.items() if any(k in s for k in kws)]
        if not hit:
            continue
        clean = re.sub(r"(지만|는데|으나|고|며)$", "", s)  # 끝 연결어미 떼고 분류
        r = clf()(clean or s)[0]
        senti = "positive" if "pos" in r["label"].lower() or r["label"].endswith("1") else "negative"
        for a in hit:
            res.append((a, senti, round(r["score"], 3), s))
    return res
