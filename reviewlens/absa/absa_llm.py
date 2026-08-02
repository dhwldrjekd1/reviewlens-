import json, urllib.request

MODEL = "qwen2.5:3b"
ASPECTS = ["배송", "품질", "가격", "포장", "디자인", "CS"]

# LLM에게 JSON 스키마 강제 (Ollama format)
SCHEMA = {
    "type": "object",
    "properties": {"results": {"type": "array", "items": {
        "type": "object",
        "properties": {"aspect": {"type": "string"},
                       "sentiment": {"type": "string"},
                       "evidence": {"type": "string"}},
        "required": ["aspect", "sentiment", "evidence"]}}},
    "required": ["results"],
}

PROMPT = """다음 상품 리뷰에서 언급된 속성별 감성을 빠짐없이 분석해줘. 아래 속성 중에서만 고르고, 정의를 지켜.
- 배송: 도착 속도, 배송 과정
- 품질: 성능·내구성·음질·연결·마감·보온 등 제품 자체
- 가격: 가격, 가성비
- 포장: 박스, 포장 상태
- 디자인: 색상·외관·예쁨
- CS: 문의·응대·교환·환불
감성은 positive 또는 negative, 근거(evidence)는 원문에서 그대로 뽑아.

리뷰: {text}"""

def analyze(text):
    body = json.dumps({
        "model": MODEL,
        "prompt": PROMPT.format(text=text),
        "stream": False, "format": SCHEMA,
        "options": {"temperature": 0},
    }).encode()
    req = urllib.request.Request("http://localhost:11434/api/generate", body,
                                 {"Content-Type": "application/json"})
    res = json.loads(urllib.request.urlopen(req, timeout=180).read())
    out = []
    # format=SCHEMA로 JSON 스키마를 강제해도 모델/Ollama 버전에 따라 빈 응답이나
    # 스키마를 어긴 응답이 나올 수 있어, 원인을 알 수 있는 메시지로 바꿔서 올린다
    # (호출부인 pipeline.py/eval.py가 리뷰 단위로 이 예외를 잡아 건너뛴다)
    try:
        parsed = json.loads(res["response"]).get("results", [])
    except (json.JSONDecodeError, AttributeError) as e:
        raise RuntimeError(f"LLM 응답이 JSON 스키마를 따르지 않음: {res.get('response', '')[:200]!r}") from e
    for it in parsed:
        a, s = it.get("aspect"), it.get("sentiment")
        if a in ASPECTS and s in ("positive", "negative"):  # neutral은 노이즈라 버림
            out.append((a, s, None, it.get("evidence", "")))
    return out
