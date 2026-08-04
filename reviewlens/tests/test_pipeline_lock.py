"""pipeline.py가 리뷰 1건의 느린 분석(analyze()) 도중 DB 쓰기 락을 쥐고 있지 않는지 검증.
analyze() 전에 delete를 먼저 열어두던 예전 순서였다면, 이 테스트의 동시 쓰기가 analyze()의
sleep이 끝날 때까지 블로킹돼 elapsed가 커진다.
"""
import threading
import time

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
