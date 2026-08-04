"""store/db.py의 Postgres 어댑터(_PgConn)가 autocommit 없이 실제 트랜잭션을 쓰는지 검증(psycopg는 목으로 대체).
"""
import pytest

from store.db import _PgConn


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

    def cursor(self):
        return _FakeCursor(self)

    def commit(self):
        self.committed += 1

    def rollback(self):
        self.rolled_back += 1


def test_pgconn_does_not_force_autocommit(monkeypatch):
    fake = _FakeConn()
    calls = {}

    def fake_connect(dsn, **kw):
        calls["kwargs"] = kw
        return fake

    monkeypatch.setattr("psycopg.connect", fake_connect)
    _PgConn("postgresql://x")
    # autocommit=True를 강제하면 각 문장이 즉시 개별 커밋돼, 호출부(pipeline.py 등)가 기대하는
    # "여러 문장이 한 커밋 안에서 원자적으로 끝남"이 성립하지 않는다.
    assert "autocommit" not in calls["kwargs"]


def test_pgconn_commit_actually_commits(monkeypatch):
    fake = _FakeConn()
    monkeypatch.setattr("psycopg.connect", lambda dsn, **kw: fake)
    conn = _PgConn("postgresql://x")
    conn.commit()
    assert fake.committed == 1   # 예전엔 autocommit=True라 commit()이 아무 일도 안 하는 no-op이었음


def test_pgconn_rolls_back_on_failed_statement(monkeypatch):
    fake = _FakeConn()
    monkeypatch.setattr("psycopg.connect", lambda dsn, **kw: fake)
    conn = _PgConn("postgresql://x")
    fake.fail_next = True
    with pytest.raises(RuntimeError):
        conn.execute("select 1")
    # Postgres는 문장 하나가 실패하면 트랜잭션 전체가 aborted 상태로 잠겨 이후 문장도 거부한다.
    # 즉시 롤백해야 이 커넥션(서버 전역 커넥션)을 다음 요청에서도 계속 쓸 수 있다.
    assert fake.rolled_back == 1


def test_pgconn_executescript_commits_ddl(monkeypatch):
    fake = _FakeConn()
    monkeypatch.setattr("psycopg.connect", lambda dsn, **kw: fake)
    conn = _PgConn("postgresql://x")
    conn.executescript("create table t(id int); create table u(id int);")
    assert fake.committed == 1   # autocommit이 꺼졌으니 DDL도 명시적으로 커밋해야 반영됨
