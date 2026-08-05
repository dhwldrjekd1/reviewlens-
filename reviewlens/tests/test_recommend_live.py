"""recommend_live.recommend()가 item 테이블엔 없는데 aspect_sentiment엔 남아있는
item_id(재적재 등으로 상품이 items 딕셔너리에서 빠진 뒤에도 이전 감성 데이터가 남는 경우)를
만나도 KeyError 없이 나머지 상품으로 정상 추천하는지 검증.
"""
from store import db
from recommend import recommend_live


def test_recommend_skips_item_missing_from_item_table(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB", str(tmp_path / "t.db"))
    d = db.get_db()
    d.execute("insert into item(item_id, name) values(?,?)", ("P1", "이어폰"))
    # P2는 item 테이블엔 없지만 aspect_sentiment엔 남아있는 상황(상품 목록에서 빠진 뒤 재적재 안 됨)
    d.execute("insert into aspect_sentiment(review_id,item_id,aspect,sentiment,confidence,evidence)"
              " values(1,'P1','배송','positive',0.9,'x')")
    d.execute("insert into aspect_sentiment(review_id,item_id,aspect,sentiment,confidence,evidence)"
              " values(2,'P2','배송','positive',0.9,'x')")
    d.commit()

    out = recommend_live.recommend(d, {"배송": 1})   # KeyError 없이 끝나야 함

    assert [name for _, name, _ in out] == ["이어폰"]   # P2는 건너뛰고 P1만 추천됨
