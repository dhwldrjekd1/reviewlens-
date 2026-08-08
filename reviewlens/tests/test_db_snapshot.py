"""d.snapshot() — board() 같은 다중 SELECT가 전부 같은 시점 데이터를 보게 하는 기능 검증.
SQLite는 실제 파일로 동시 커밋을 재현, Postgres는 psycopg를 목으로 대체해 REPEATABLE READ
격상/원복 시퀀스를 검증(이 샌드박스는 docker 네트워크가 막혀 있어 실제 Postgres는 못 씀).
"""
import pytest

from store import db
from store.db import _PgConn


def test_sqlite_snapshot_hides_concurrent_commit(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB", str(tmp_path / "t.db"))
    d = db.get_db()
    d.execute("insert into feedback(question, answer, vote, correction) values(?,?,?,?)",
              ("q1", "", "up", ""))
    d.commit()

    with d.snapshot():
        first = d.execute("select count(*) from feedback").fetchone()[0]

        other = db.get_db()   # board() 조회 도중 파이프라인 등 다른 커넥션이 쓰는 상황을 흉내
        other.execute("insert into feedback(question, answer, vote, correction) values(?,?,?,?)",
                      ("q2", "", "up", ""))
        other.commit()

        second = d.execute("select count(*) from feedback").fetchone()[0]
        assert second == first   # 스냅샷 안에서는 그 사이 커밋이 안 보여야 함

    after = d.execute("select count(*) from feedback").fetchone()[0]
    assert after == first + 1   # 스냅샷이 끝나면 다시 최신값을 봐야 함


class _FakeTxnCtx:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.description = None

    def execute(self, sql, params=None):
        self.conn.executed.append(sql)

    def fetchall(self):
        return []

    def close(self):
        pass


class _FakeConn:
    def __init__(self):
        self.executed = []
        self.isolation_level = None
        self.isolation_level_history = []

    def cursor(self):
        return _FakeCursor(self)

    def transaction(self):
        # 진입 시점의 isolation_level을 기록 — REPEATABLE READ로 격상된 채로 트랜잭션에
        # 들어갔는지 확인하기 위함(실제 psycopg는 이 값으로 BEGIN ISOLATION LEVEL을 구성함)
        self.isolation_level_history.append(self.isolation_level)
        return _FakeTxnCtx(self)


def test_pgconn_snapshot_uses_repeatable_read_then_restores(monkeypatch):
    import psycopg
    fake = _FakeConn()
    monkeypatch.setattr("psycopg.connect", lambda dsn, **kw: fake)
    conn = _PgConn("postgresql://x")

    assert fake.isolation_level is None   # 평소엔 서버 기본값(READ COMMITTED)
    with conn.snapshot():
        conn.execute("select 1")
        conn.execute("select 2")
    assert fake.isolation_level_history == [psycopg.IsolationLevel.REPEATABLE_READ]
    assert fake.isolation_level is None   # 블록이 끝나면 다시 기본값으로 원복돼야 함
    assert len(fake.executed) == 2


def test_pgconn_snapshot_restores_isolation_level_even_on_failure(monkeypatch):
    fake = _FakeConn()
    monkeypatch.setattr("psycopg.connect", lambda dsn, **kw: fake)
    conn = _PgConn("postgresql://x")

    with pytest.raises(RuntimeError):
        with conn.snapshot():
            raise RuntimeError("boom")
    assert fake.isolation_level is None   # 블록 안에서 예외가 나도 격리수준은 원복돼야 함
