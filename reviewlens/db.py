import sqlite3, os, re, threading

DB = os.path.join(os.path.dirname(__file__), "db", "reviewlens.db")
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


class _Result:
    """잠금 안에서 미리 fetch한 행을 들고, sqlite 커서처럼 fetchall/fetchone/순회를 지원."""
    def __init__(self, rows): self._rows = rows
    def fetchall(self): return self._rows
    def fetchone(self): return self._rows[0] if self._rows else None
    def __iter__(self): return iter(self._rows)


class _PgConn:
    """sqlite3.Connection 흉내 — 코드의 d.execute(sql, params).fetchall() 패턴을 Postgres에서 그대로.
    psycopg 연결은 스레드 동시 사용이 불가하므로 잠금으로 직렬화한다(이 규모엔 충분)."""
    def __init__(self, dsn):
        import psycopg
        self._c = psycopg.connect(dsn, autocommit=True)
        self._lock = threading.Lock()

    def execute(self, sql, params=None):
        with self._lock:
            cur = self._c.cursor()
            cur.execute(_to_pg(sql), params or None)
            rows = cur.fetchall() if cur.description else []   # SELECT면 행, INSERT/DELETE면 []
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


def get_db():
    if BACKEND == "postgres":
        db = _PgConn(PG_DSN)
    else:
        os.makedirs(os.path.dirname(DB), exist_ok=True)
        db = sqlite3.connect(DB, check_same_thread=False)  # FastAPI 스레드에서도 쓰게
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
