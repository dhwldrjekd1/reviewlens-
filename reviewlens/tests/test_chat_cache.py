"""ask()가 캐시에 저장할 때 mode(intent)를 빠뜨리지 않는지 검증(ground/모델은 목으로 대체).
빠지면 _cache_put이 기본값 "review"로 저장해, 이후 캐시 조회 시(예: ask_stream) intent가
실제 의도(추천/집계 등)와 다르게 표시되는 회귀가 있었다.
"""
import chat.chatbot as chatbot


class _FakeModel:
    def encode(self, texts, normalize_embeddings=True):
        return [0.0] * len(texts)


def _reset_cache(monkeypatch):
    monkeypatch.setattr(chatbot, "_EXACT", {})
    monkeypatch.setattr(chatbot, "_CACHE", [])
    monkeypatch.setattr(chatbot.retriever, "get_model", lambda: _FakeModel())


def test_ask_caches_direct_answer_with_correct_mode(monkeypatch):
    _reset_cache(monkeypatch)
    monkeypatch.setattr(chatbot, "ground", lambda d, q: ("근거", "recommend", "추천 답변입니다"))
    monkeypatch.setattr(chatbot, "recall_corrections", lambda d, q: [])   # direct 즉답 경로를 타게 함

    chatbot.ask(None, "가성비 좋은거 추천해줘")

    cached = chatbot._EXACT[chatbot._norm("가성비 좋은거 추천해줘")]
    assert cached[2] == "recommend"   # mode 누락 시 기본값 "review"로 잘못 저장됐었음


def test_ask_caches_llm_answer_with_correct_mode(monkeypatch):
    _reset_cache(monkeypatch)
    # direct가 있어도 corr(정정 메모리)이 있으면 LLM 생성 경로로 빠짐 — 두 번째 _cache_put 호출부
    monkeypatch.setattr(chatbot, "ground", lambda d, q: ("근거 리뷰", "aggregate", "집계 즉답"))
    monkeypatch.setattr(chatbot, "recall_corrections", lambda d, q: ["예전 정정"])
    monkeypatch.setattr(chatbot, "_generate", lambda *a, **kw: "생성된 한국어 답변")
    monkeypatch.setattr(chatbot, "_grounded", lambda ans, ctx: True)

    chatbot.ask(None, "부정이 가장 많은 항목이 뭐야?")

    cached = chatbot._EXACT[chatbot._norm("부정이 가장 많은 항목이 뭐야?")]
    assert cached[2] == "aggregate"   # mode 누락 시 기본값 "review"로 잘못 저장됐었음


def test_ask_survives_recall_corrections_failure(monkeypatch):
    # ask_stream()은 recall_corrections() 실패를 보호하는데 ask()는 무방비였던 회귀(교차검증에서 발견)
    _reset_cache(monkeypatch)
    monkeypatch.setattr(chatbot, "ground", lambda d, q: ("근거", "recommend", "추천 답변입니다"))

    def _boom(d, q):
        raise RuntimeError("임베딩 모델 오류")
    monkeypatch.setattr(chatbot, "recall_corrections", _boom)

    ans, ctx = chatbot.ask(None, "가성비 좋은거 추천해줘")   # 예외 없이 direct 답변을 그대로 반환해야 함
    assert ans == "추천 답변입니다"


def _boom_cache_put(*a, **kw):
    raise RuntimeError("임베딩 모델 오류")


def test_ask_direct_path_survives_cache_put_failure(monkeypatch):
    # ask()/ask_stream() 둘 다 즉답 경로의 _cache_put()이 무방비였던 회귀(교차검증에서 발견) —
    # 캐시 저장이 실패해도 이미 만든 즉답은 그대로 반환돼야 함
    _reset_cache(monkeypatch)
    monkeypatch.setattr(chatbot, "ground", lambda d, q: ("근거", "recommend", "추천 답변입니다"))
    monkeypatch.setattr(chatbot, "recall_corrections", lambda d, q: [])
    monkeypatch.setattr(chatbot, "_cache_put", _boom_cache_put)

    ans, ctx = chatbot.ask(None, "가성비 좋은거 추천해줘")
    assert ans == "추천 답변입니다"


def test_ask_llm_path_survives_cache_put_failure(monkeypatch):
    # ask()의 LLM 경로는 _generate()와 _cache_put()이 같은 try 블록이라, 이미 정상 생성된 답변이
    # 캐시 저장 실패 때문에 "LLM 생성 실패" 오답으로 버려지던 회귀(교차검증에서 발견)
    _reset_cache(monkeypatch)
    monkeypatch.setattr(chatbot, "ground", lambda d, q: ("근거 리뷰", "aggregate", "집계 즉답"))
    monkeypatch.setattr(chatbot, "recall_corrections", lambda d, q: ["예전 정정"])
    monkeypatch.setattr(chatbot, "_generate", lambda *a, **kw: "정상적으로 생성된 좋은 한국어 답변")
    monkeypatch.setattr(chatbot, "_grounded", lambda ans, ctx: True)
    monkeypatch.setattr(chatbot, "_cache_put", _boom_cache_put)

    ans, ctx = chatbot.ask(None, "부정이 가장 많은 항목이 뭐야?")
    assert ans == "정상적으로 생성된 좋은 한국어 답변"   # "답변을 생성하는 중 문제가 생겼어요"로 대체되면 안 됨


def test_ask_stream_direct_path_survives_cache_put_failure(monkeypatch):
    _reset_cache(monkeypatch)
    monkeypatch.setattr(chatbot, "ground", lambda d, q: ("근거", "recommend", "추천 답변입니다"))
    monkeypatch.setattr(chatbot, "recall_corrections", lambda d, q: [])
    monkeypatch.setattr(chatbot, "_cache_put", _boom_cache_put)

    events = list(chatbot.ask_stream(None, "가성비 좋은거 추천해줘"))
    tokens = "".join(e["token"] for e in events if "token" in e)
    assert tokens == "추천 답변입니다"
    assert events[-1] == {"evidence": "근거", "done": True}   # done 신호가 반드시 나가야 함
