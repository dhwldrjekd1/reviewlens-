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
