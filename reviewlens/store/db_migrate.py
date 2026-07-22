"""SQLite → Postgres 데이터 복사. ABSA를 다시 안 돌리고 기존 데이터를 옮길 때.

  사전: docker compose up -d  (Postgres가 떠 있어야 함)
  사용: reviewlens/ 에서 python -m store.db_migrate  (store가 패키지로 잡히려면 -m 실행 필요)

db.py의 _PgConn/_to_pg 어댑터를 그대로 써서, 같은 SQL이 양쪽에서 도는 걸 보여준다.
"""
import sys, sqlite3, re
from store import db as dbmod

if hasattr(sys.stdout, "reconfigure"):       # Windows 콘솔(cp949) 한글/대시 깨짐 방지
    sys.stdout.reconfigure(encoding="utf-8")


# 테이블 → 복사할 컬럼을 db.SCHEMA에서 직접 추출(수기 목록이었을 때 새 테이블 추가를 깜빡하는 문제 방지).
# 제외 대상: autoincrement 대체키(대상에서 새로 채번), default current_timestamp 컬럼(대상에서 새로 찍음).
def _derive_tables(schema):
    tables = {}
    for name, body in re.findall(r"create table if not exists (\w+)\(\s*(.*?)\s*\);",
                                  schema, re.IGNORECASE | re.DOTALL):
        cols = []
        for col_def in body.split(","):
            col_def = col_def.strip()
            if not col_def:
                continue
            low = col_def.lower()
            if "autoincrement" in low or "default current_timestamp" in low:
                continue
            cols.append(col_def.split()[0])
        tables[name] = cols
    return tables


TABLES = _derive_tables(dbmod.SCHEMA)


def main():
    src = sqlite3.connect(dbmod.DB)            # SQLite 원본
    pg = dbmod._PgConn(dbmod.PG_DSN)           # Postgres 대상
    pg.executescript(dbmod.SCHEMA)            # 스키마 보장(없으면 생성)
    for t, cols in TABLES.items():
        pg.execute(f"delete from {t}")        # 재실행 멱등성
        rows = src.execute(f"select {','.join(cols)} from {t}").fetchall()
        ph = ",".join(["?"] * len(cols))
        for r in rows:
            pg.execute(f"insert into {t}({','.join(cols)}) values({ph})", tuple(r))
        print(f"{t:<18} {len(rows)}행 복사")
    print("완료 — 이제 RL_DB=postgres 로 앱을 실행하세요.")


if __name__ == "__main__":
    main()
