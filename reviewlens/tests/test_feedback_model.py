"""FB(피드백) 요청 모델의 길이 제한 — Q(질문)엔 있는데 FB엔 없어 인증 없는 /api/feedback을
무제한 반복 호출하면 DB가 계속 커지고, correction은 매 챗봇 질문마다 전체가 재임베딩되는
구조(recall_corrections)라 거대한 값 하나가 이후 모든 응답을 느리게 만들 수 있었다.
"""
import pytest
from pydantic import ValidationError

from api.chat import FB


def test_normal_feedback_passes():
    FB(q="배송 빠른가요?", answer="네 빠른 편이에요", vote="up", correction="")


def test_overlong_q_rejected():
    with pytest.raises(ValidationError):
        FB(q="a" * 501)


def test_overlong_correction_rejected():
    with pytest.raises(ValidationError):
        FB(q="정상 질문", correction="c" * 1001)


def test_overlong_answer_rejected():
    with pytest.raises(ValidationError):
        FB(q="정상 질문", answer="a" * 4001)
