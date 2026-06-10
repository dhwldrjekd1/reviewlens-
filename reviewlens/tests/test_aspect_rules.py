"""속성 추출 규칙 (절 분리·속성 감지·연결어미 제거). 순수 텍스트 처리."""
from absa.aspect_rules import detect, clauses, strip_conj


def test_detect_basic():
    assert "배송" in detect("배송이 정말 빨라요")
    assert "디자인" in detect("색상이 예뻐요")


def test_detect_synonyms_map_to_aspect():
    # 서로 다른 표현이 같은 속성으로 ("택배"·"도착" → 배송)
    assert "배송" in detect("택배 일찍 도착했어요")


def test_detect_multiple_aspects():
    got = detect("가성비 좋고 디자인도 예뻐요")
    assert "가격" in got and "디자인" in got


def test_detect_none():
    assert detect("그냥 평범한 문장입니다") == []


def test_clauses_split_on_connective():
    # '지만'에서 절이 끊겨 속성별 감성이 안 섞이게
    cs = clauses("맛은 좋지만 가격이 비싸요")
    assert len(cs) >= 2
    assert any("좋" in c for c in cs) and any("비싸" in c for c in cs)


def test_strip_conj():
    assert strip_conj("좋지만") == "좋"
    assert strip_conj("빠르고") == "빠르"
    assert strip_conj("좋아요") == "좋아요"   # 연결어미 아니면 그대로
