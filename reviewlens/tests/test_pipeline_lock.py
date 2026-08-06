"""pipeline.py가 리뷰 1건의 느린 분석(analyze()) 도중 DB 쓰기 락을 쥐고 있지 않는지 검증.
analyze() 전에 delete를 먼저 열어두던 예전 순서였다면, 이 테스트의 동시 쓰기가 analyze()의
sleep이 끝날 때까지 블로킹돼 elapsed가 커진다.
"""
import threading
import time

import pytest

import pipeline
from store import db


class _SlowAnalyzer:
    def __init__(self, delay):
        self.delay = delay

    def analyze(self, text):
        time.sleep(self.delay)
        return [("품질", "positive", 0.9, text[:20])]


def test_slow_analyze_does_not_block_concurrent_write(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB", str(tmp_path / "t.db"))
    monkeypatch.setattr(pipeline, "reviews",
                         lambda: [{"review_id": "1", "item_id": "P1", "text": "좋아요", "rating": "5"}])
    # 이 테스트의 관심사는 analyze() 구간의 락 보유 여부뿐이라, 뒤이은 LLM 후처리는 생략
    monkeypatch.setattr(pipeline.chatbot, "build_product_summaries", lambda d: 0)
    monkeypatch.setattr(pipeline.chatbot, "build_marketing", lambda d: 0)
    monkeypatch.setattr(pipeline.chatbot, "build_replies", lambda d: 0)

    done = threading.Event()

    def run_pipeline():
        pipeline.run(_SlowAnalyzer(delay=1.0))
        done.set()

    t = threading.Thread(target=run_pipeline)
    t.start()
    time.sleep(0.2)   # analyze()가 sleep 중인 시점을 노림(리뷰 원문은 이미 커밋된 뒤)

    start = time.time()
    other = db.get_db()   # 서버의 /api/feedback처럼 별도 커넥션으로 쓰기 시도
    other.execute("insert into feedback(question, answer, vote, correction) values(?,?,?,?)",
                  ("동시쓰기 테스트", "", "up", ""))
    other.commit()
    elapsed = time.time() - start

    t.join(timeout=5)
    assert done.is_set()
    assert elapsed < 0.5   # 락 경합 없이 즉시 끝나야 함


def test_item_seeding_survives_first_review_transaction_failure(tmp_path, monkeypatch):
    # SQLite는 커밋 없이 실행한 쓰기가 암묵적 트랜잭션에 계속 쌓인다. item 시딩 루프에
    # 자체 커밋이 없으면, 뒤이은 첫 리뷰의 d.transaction() 블록이 실패해 롤백될 때
    # 무관한 item insert까지 같이 날아갈 수 있었다(교차검증에서 발견).
    monkeypatch.setattr(db, "DB", str(tmp_path / "t.db"))
    monkeypatch.setattr(pipeline, "reviews",
                         lambda: [{"review_id": "1", "item_id": "P1", "text": "x", "rating": "숫자아님"}])

    with pytest.raises(ValueError):   # int("숫자아님")이 리뷰 insert 트랜잭션 안에서 실패
        pipeline.run(_SlowAnalyzer(delay=0))

    fresh = db.get_db()   # 새 커넥션으로 재확인 — 이전 커넥션의 캐시된 상태가 아니라 실제 디스크 상태
    count = fresh.execute("select count(*) from item").fetchone()[0]
    assert count == len(pipeline.items)   # 15개 상품이 롤백 안 되고 그대로 남아있어야 함
