"""SQLite → Postgres 데이터 복사. ABSA를 다시 안 돌리고 기존 데이터를 옮길 때.

  사전: docker compose up -d  (Postgres가 떠 있어야 함)
  사용: python db_migrate.py

db.py의 _PgConn/_to_pg 어댑터를 그대로 써서, 같은 SQL이 양쪽에서 도는 걸 보여준다.
"""
import sys, sqlite3
import db as dbmod

if hasattr(sys.stdout, "reconfigure"):       # Windows 콘솔(cp949) 한글/대시 깨짐 방지
    sys.stdout.reconfigure(encoding="utf-8")

# 테이블 → 복사할 컬럼(serial id 컬럼은 제외, 대상에서 자동 생성)
TABLES = {
    "item":             ["item_id", "name", "category"],
    "review":           ["review_id", "item_id", "raw_text", "rating"],
    "aspect_sentiment": ["review_id", "item_id", "aspect", "sentiment", "confidence", "evidence"],
    "product_summary":  ["item_id", "summary"],
    "feedback":         ["question", "answer", "vote", "correction"],
}


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
