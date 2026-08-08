import sqlite3, os, re, threading
from contextlib import contextmanager

DB = os.path.join(os.path.dirname(os.path.dirname(__file__)), "db", "reviewlens.db")
# 백엔드 선택: 기본 SQLite(임베디드·제로셋업·로컬), RL_DB=postgres면 Postgres(다중서버 프로덕션용)
BACKEND = os.environ.get("RL_DB", "sqlite").lower()
PG_DSN = os.environ.get("RL_PG_DSN",
                        "postgresql://reviewlens:reviewlens@localhost:5432/reviewlens")

# 스키마는 SQLite 기준으로 한 벌만 둔다. Postgres는 _to_pg_ddl이 자동 변환.
SCHEMA = """
create table if not exists item(
    item_id text primary key, name text, category text
);
create table if not exists review(
    review_id integer primary key, item_id text, raw_text text, rating integer
);
create table if not exists aspect_sentiment(
    id integer primary key autoincrement,
    review_id integer, item_id text,
    aspect text, sentiment text, confidence real, evidence text
);
create table if not exists feedback(
    id integer primary key autoincrement,
    question text, answer text, vote text, correction text,
    created text default current_timestamp
);
create table if not exists product_summary(
    item_id text primary key, summary text, generated text default current_timestamp
);
create table if not exists product_copy(
    item_id text primary key, copy text, basis text
);
create table if not exists review_reply(
    review_id integer primary key, reply text
);
"""


# --- SQLite 방언 → Postgres 자동 변환 (코드의 SQL은 전부 SQLite 기준으로 작성) ---
def _to_pg(sql):
    # 1) 불리언 합계: SQLite는 비교(=)가 1/0이라 sum()이 카운트로 동작 → Postgres는 ::int 캐스팅
    sql = re.sub(r"sum\(\s*([\w.]+\s*=\s*'[^']*')\s*\)", r"sum((\1)::int)", sql)
    # 2) upsert: insert or replace into T(c1,c2,..) values(..) → on conflict(c1) do update
    m = re.match(r"\s*insert\s+or\s+replace\s+into\s+(\w+)\s*\(([^)]+)\)(.*)",
                 sql, re.IGNORECASE | re.DOTALL)
    if m:
        t, cols = m.group(1), [c.strip() for c in m.group(2).split(",")]
        rest, pk, others = m.group(3), cols[0], cols[1:]
        setc = ", ".join(f"{c}=excluded.{c}" for c in (others or [pk]))
        sql = f"insert into {t} ({', '.join(cols)}){rest} on conflict ({pk}) do update set {setc}"
    return sql.replace("?", "%s")                          # 3) 플레이스홀더 ?→%s


def _to_pg_ddl(stmt):
    return (stmt.replace("integer primary key autoincrement", "serial primary key")
                .replace("default current_timestamp", "default (current_timestamp::text)"))


def _dec(v):
    """psycopg3 3.3+ 에서 text 컬럼이 bytes로 반환되는 경우 str로 디코드."""
    if isinstance(v, (bytes, memoryview)):
        return bytes(v).decode("utf-8")
    return v


class _Result:
    """잠금 안에서 미리 fetch한 행을 들고, sqlite 커서처럼 fetchall/fetchone/순회를 지원."""
    def __init__(self, rows): self._rows = rows
    def fetchall(self): return self._rows
    def fetchone(self): return self._rows[0] if self._rows else None
    def __iter__(self): return iter(self._rows)


class _SqliteConn:
    """sqlite3.Connection 래핑 — Postgres 경로(_PgConn)는 스레드 간 동시 사용을 잠금으로
    직렬화하는데, 기본 백엔드인 이쪽엔 그 보호가 빠져 있었다. FastAPI 동기 핸들러는
    스레드풀에서 실행되므로(check_same_thread=False로 스레드 자체는 허용해도), 잠금 없이
    같은 커넥션에 여러 스레드가 동시에 execute를 호출하면 sqlite3 공식 문서가 경고하는
    데이터 손상 위험이 있다. RLock인 이유: transaction()이 잠금을 쥔 채로 블록 안에서
    다시 execute()를 호출하므로(같은 스레드의 재진입) 일반 Lock이면 데드락이 난다."""
    def __init__(self, path):
        self._c = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.RLock()
        with self._lock:
            self._c.execute("PRAGMA journal_mode=WAL")
            self._c.execute("PRAGMA busy_timeout=5000")

    def execute(self, sql, params=None):
        with self._lock:
            cur = self._c.execute(sql, params or ())
            rows = cur.fetchall() if cur.description else []
            return _Result(rows)

    def executescript(self, script):
        with self._lock:
            self._c.executescript(script)

    def commit(self):
        with self._lock:
            self._c.commit()

    @contextmanager
    def transaction(self):
        """여러 execute()를 하나의 원자적 단위로 묶음(예: pipeline.py의 리뷰별 delete+insert) —
        블록 전체 동안 잠금을 쥐고 있어 다른 스레드의 문장이 끼어들지 않고, 끝에 커밋(실패 시 롤백)."""
        with self._lock:
            try:
                yield
                self._c.commit()
            except Exception:
                self._c.rollback()
                raise

    @contextmanager
    def snapshot(self):
        """여러 SELECT가 전부 같은 시점의 데이터를 보게 함(board()의 다중 집계 조회용) —
        기본(autocommit) 모드에서는 SELECT가 트랜잭션을 안 열어 문장마다 최신값을 따로 봄.
        명시적으로 BEGIN을 열면 WAL 모드에서 그 시점의 스냅샷이 트랜잭션 끝까지 유지되어,
        그 사이 다른 커넥션이 커밋해도 이 블록 안에서는 안 보인다(직접 재현 검증함)."""
        with self._lock:
            self._c.execute("BEGIN")
            try:
                yield
            finally:
                self._c.commit()   # 읽기 전용이라 commit/rollback 의미 차이 없음 — 스냅샷 종료 목적


class _PgConn:
    """sqlite3.Connection 흉내 — 코드의 d.execute(sql, params).fetchall() 패턴을 Postgres에서 그대로.
    psycopg 연결은 스레드 동시 사용이 불가하므로 잠금으로 직렬화한다(이 규모엔 충분).

    autocommit=True — 이 커넥션은 api/deps.py에서 프로세스 전역으로 공유되고, FastAPI 동기
    핸들러는 스레드풀에서 동시 실행되므로 요청 여러 개의 문장이 같은 커넥션에 뒤섞여 들어온다.
    한때 autocommit=False로 바꿔 "여러 문장을 한 커밋으로 묶는" 걸 시도했었는데, 잠금은 문장
    하나 단위였던 반면 트랜잭션은 커밋 전까지 여러 문장(=여러 요청)에 걸쳐 열려있게 되어, 한
    요청의 문장 실패로 인한 rollback이 커밋 전인 다른 요청의 쓰기까지 함께 날려버릴 수 있었다
    (예: A가 board() 조회 중 커밋 안 하고 있는 사이 B의 feedback insert가 같은 트랜잭션에
    끼어들었다가, 그 사이 C의 문장 실패로 롤백되면 B의 쓰기가 에러 없이 조용히 사라짐).
    autocommit=True로 되돌려 문장 하나 = 커밋 하나로 만들면 이 경합이 사라진다. 여러 문장을
    진짜 원자적으로 묶어야 하는 곳(pipeline.py)은 아래 transaction()을 명시적으로 쓴다."""
    def __init__(self, dsn):
        import psycopg
        self._c = psycopg.connect(dsn, autocommit=True)
        self._lock = threading.RLock()   # transaction()이 잠금을 쥔 채 execute()를 재호출하므로 RLock

    def execute(self, sql, params=None):
        with self._lock:
            cur = self._c.cursor()
            cur.execute(_to_pg(sql), params or None)
            rows = [tuple(_dec(v) for v in r) for r in cur.fetchall()] if cur.description else []
            cur.close()
            return _Result(rows)

    def executescript(self, script):
        with self._lock:
            cur = self._c.cursor()
            for stmt in filter(str.strip, script.split(";")):
                cur.execute(_to_pg_ddl(stmt))
            cur.close()

    def commit(self):
        pass   # autocommit=True → 명시적 commit은 무해한 no-op

    @contextmanager
    def transaction(self):
        """여러 execute()를 하나의 진짜 원자적 트랜잭션으로 묶음(예: pipeline.py의 리뷰별
        delete+insert) — 블록 전체 동안 잠금을 쥐고 있어 다른 스레드의 문장이 끼어들지 않는다.
        psycopg는 autocommit 커넥션에서도 Connection.transaction()으로 임시 트랜잭션을 열 수
        있고, 블록 정상 종료 시 커밋·예외 시 자동 롤백한다(직접 rollback()을 부르면 안 됨 —
        이 블록 안에서는 psycopg가 트랜잭션 상태를 관리하므로 충돌한다)."""
        with self._lock:
            with self._c.transaction():
                yield

    @contextmanager
    def snapshot(self):
        """여러 SELECT가 전부 같은 시점의 데이터를 보게 함(board()의 다중 집계 조회용) —
        Postgres 기본 격리수준(READ COMMITTED)은 트랜잭션으로 묶어도 문장마다 자기 시작
        시점 기준 최신 커밋값을 보므로, 그것만으론 여러 SELECT의 일관성이 보장 안 된다.
        이 블록에서만 REPEATABLE READ로 격상했다가 끝나면 되돌린다. 잠금을 블록 전체 동안
        쥐고 있어(RLock) 이 상태 전환 중간에 다른 요청이 끼어들 수 없다 — psycopg는 트랜잭션
        진행 중 isolation_level 변경 시도 시 자체적으로 예외를 던지므로(psycopg 소스로 확인)
        이중으로 안전하다."""
        import psycopg
        with self._lock:
            self._c.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
            try:
                with self._c.transaction():
                    yield
            finally:
                self._c.isolation_level = None   # 다음 문장부터 다시 서버 기본값(READ COMMITTED)


def get_db():
    if BACKEND == "postgres":
        db = _PgConn(PG_DSN)
    else:
        os.makedirs(os.path.dirname(DB), exist_ok=True)
        db = _SqliteConn(DB)   # WAL + busy_timeout 설정, 스레드 간 잠금 포함(_SqliteConn 참고)
    db.executescript(SCHEMA)
    return db


# 상품 x 속성별 긍/부정 집계 — 대시보드·추천이 가져다 쓰는 결과
def summary(db):
    return db.execute("""
        select i.name, a.aspect,
               sum(a.sentiment='positive') pos,
               sum(a.sentiment='negative') neg
        from aspect_sentiment a join item i using(item_id)
        group by i.name, a.aspect
        order by i.name, a.aspect
    """).fetchall()
