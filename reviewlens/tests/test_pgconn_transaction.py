"""store/db.py의 Postgres 어댑터(_PgConn) 동시성/트랜잭션 계약 검증(psycopg는 목으로 대체).

이 파일은 한 번 뒤집힌 설계다: 처음엔 _PgConn을 autocommit=False로 바꿔 "여러 문장이 한
커밋 안에서 원자적으로 끝남"을 만들려 했는데, 이 커넥션은 api/deps.py에서 프로세스 전역으로
공유되고 잠금은 문장 하나 단위였다. 그 결과 요청 A가 커밋 안 하고 있는 사이 요청 B의 쓰기가
같은(아직 안 끝난) 트랜잭션에 끼어들었다가, 요청 C의 문장 실패로 인한 롤백에 B의 쓰기까지
같이 날아갈 수 있었다(교차검증에서 발견). 그래서 공유 커넥션은 다시 autocommit=True(문장
하나 = 커밋 하나, 요청 간 절대 안 섞임)로 되돌리고, 진짜 원자성이 필요한 곳(pipeline.py의
리뷰별 delete+insert)만 transaction()으로 명시적 트랜잭션 블록을 쓰게 분리했다.
"""
import threading

import pytest

from store.db import _PgConn


class _FakeTxnCtx:
    """psycopg Connection.transaction()의 컨텍스트 매니저 흉내."""
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        self.conn.txn_depth += 1
        return self

    def __exit__(self, exc_type, exc, tb):
        self.conn.txn_depth -= 1
        if exc_type is None:
            self.conn.committed += 1
        else:
            self.conn.rolled_back += 1
        return False   # 예외를 삼키지 않고 그대로 전파(실제 psycopg와 동일)


class _FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.description = None

    def execute(self, sql, params=None):
        if self.conn.fail_next:
            self.conn.fail_next = False
            raise RuntimeError("boom")
        self.conn.executed.append(sql)

    def fetchall(self):
        return []

    def close(self):
        pass


class _FakeConn:
    def __init__(self):
        self.executed = []
        self.committed = 0
        self.rolled_back = 0
        self.fail_next = False
        self.txn_depth = 0

    def cursor(self):
        return _FakeCursor(self)

    def transaction(self):
        return _FakeTxnCtx(self)


def test_pgconn_connects_with_autocommit(monkeypatch):
    fake = _FakeConn()
    calls = {}

    def fake_connect(dsn, **kw):
        calls["kwargs"] = kw
        return fake

    monkeypatch.setattr("psycopg.connect", fake_connect)
    _PgConn("postgresql://x")
    # 프로세스 전역 공유 커넥션이라 문장 하나 = 커밋 하나여야 요청 간 트랜잭션이 안 섞인다
    assert calls["kwargs"].get("autocommit") is True


def test_pgconn_commit_is_harmless_noop(monkeypatch):
    fake = _FakeConn()
    monkeypatch.setattr("psycopg.connect", lambda dsn, **kw: fake)
    conn = _PgConn("postgresql://x")
    conn.commit()   # autocommit=True라 이미 매 문장이 커밋된 상태 — 예외 없이 그냥 넘어가야 함
    assert fake.committed == 0


def test_pgconn_transaction_commits_once_for_whole_block(monkeypatch):
    fake = _FakeConn()
    monkeypatch.setattr("psycopg.connect", lambda dsn, **kw: fake)
    conn = _PgConn("postgresql://x")
    with conn.transaction():
        conn.execute("delete from aspect_sentiment where review_id=%s", (1,))
        conn.execute("insert into aspect_sentiment(...) values(...)")
    assert fake.committed == 1
    assert fake.rolled_back == 0
    assert len(fake.executed) == 2


def test_pgconn_transaction_rolls_back_whole_block_on_failure(monkeypatch):
    fake = _FakeConn()
    monkeypatch.setattr("psycopg.connect", lambda dsn, **kw: fake)
    conn = _PgConn("postgresql://x")
    fake.fail_next = True
    with pytest.raises(RuntimeError):
        with conn.transaction():
            conn.execute("delete from aspect_sentiment where review_id=%s", (1,))   # 여기서 실패
    assert fake.rolled_back == 1
    assert fake.committed == 0


def test_pgconn_execute_inside_transaction_does_not_deadlock(monkeypatch):
    # transaction()이 잠금을 쥔 채로 블록 안에서 execute()가 같은 잠금을 다시 요구한다.
    # 일반 Lock이면 같은 스레드에서도 데드락 — RLock이어야 통과한다.
    fake = _FakeConn()
    monkeypatch.setattr("psycopg.connect", lambda dsn, **kw: fake)
    conn = _PgConn("postgresql://x")
    done = threading.Event()

    def run():
        with conn.transaction():
            conn.execute("select 1")
        done.set()

    t = threading.Thread(target=run)
    t.start()
    t.join(timeout=2)
    assert done.is_set()   # 2초 안에 못 끝나면 데드락
