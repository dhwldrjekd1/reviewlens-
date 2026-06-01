import sqlite3, os

DB = os.path.join(os.path.dirname(__file__), "db", "reviewlens.db")

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
"""

def get_db():
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
