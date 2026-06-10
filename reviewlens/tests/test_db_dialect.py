"""DB 어댑터의 SQLite→Postgres 방언 자동 변환 (순수 문자열 변환, DB 불필요)."""
from store.db import _to_pg, _to_pg_ddl


def test_bool_sum_cast():
    # SQLite의 sum(비교)는 Postgres에서 ::int 캐스팅 필요
    out = _to_pg("select sum(sentiment='positive') from aspect_sentiment")
    assert "sum((sentiment='positive')::int)" in out


def test_placeholder_qmark_to_percent():
    out = _to_pg("select * from item where item_id=?")
    assert "?" not in out and "%s" in out


def test_upsert_to_on_conflict():
    out = _to_pg("insert or replace into product_summary(item_id, summary) values(?,?)")
    assert out.startswith("insert into product_summary (item_id, summary)")
    assert "on conflict (item_id) do update set summary=excluded.summary" in out
    assert "%s" in out and "?" not in out


def test_ddl_serial_and_timestamp():
    ddl = _to_pg_ddl("create table x(id integer primary key autoincrement, ts text default current_timestamp)")
    assert "serial primary key" in ddl
    assert "default (current_timestamp::text)" in ddl


def test_plain_select_unchanged():
    # 변환 대상이 없는 평범한 SQL은 그대로(플레이스홀더 외)
    sql = "select name from item order by name"
    assert _to_pg(sql) == sql
