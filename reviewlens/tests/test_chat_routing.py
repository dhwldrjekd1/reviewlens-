"""챗봇 의도 감지 헬퍼 (순수 함수, 모델·DB 불필요).

ground() 전체는 임베딩 모델·DB가 필요해 여기선 라우팅을 가르는 순수 헬퍼만 검증한다.
"""
from chat.chatbot import (
    _wants_overview, _wants_list, _wants_proscons,
    _smalltalk, _bad_lang, _ev_count, _norm,
)


def test_wants_overview_positive():
    assert _wants_overview("전체리뷰알려줘")
    assert _wants_overview("리뷰 요약해줘")
    assert _wants_overview("전반적으로 어때")
    assert _wants_overview("리뷰 알려줘")


def test_wants_overview_negative_when_named_product():
    # 앞에 상품/카테고리 명사가 있으면 개요가 아니라 RAG로 가야 함
    assert not _wants_overview("이어폰 리뷰 알려줘")
    assert not _wants_overview("배송 어때")


def test_wants_list():
    assert _wants_list("상품 목록 보여줘")
    assert _wants_list("어떤 상품 있어?")
    assert not _wants_list("배송 빠른가요?")


def test_wants_proscons():
    assert _wants_proscons("장단점 알려줘")
    assert _wants_proscons("좋은점 나쁜점 정리해줘")
    assert not _wants_proscons("가격 어때요")


def test_smalltalk():
    assert _smalltalk("안녕") is not None
    assert _smalltalk("고마워") is not None
    assert _smalltalk("배송 빠른가요?") is None


def test_bad_lang():
    assert not _bad_lang("배송이 정말 빠릅니다")        # 순수 한국어 OK
    assert _bad_lang("this is an english sentence")     # 영어 누출 → 비정상


def test_ev_count():
    assert _ev_count("- 배송: 긍정 10 / 부정 2\n- 품질: 긍정 5 / 부정 1") == 2
    assert _ev_count("헤더줄\n- a\n- b\n- c") == 3       # 헤더 제외, '-' 항목만
    assert _ev_count("") == 0


def test_norm():
    assert _norm("  배송 어때? ") == "배송어때?"
    assert _norm("배송  어때") == _norm("배 송 어때")    # 공백 무시 → 같은 캐시 키
