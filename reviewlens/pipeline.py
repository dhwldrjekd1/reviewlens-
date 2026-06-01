import csv, os
import db, absa_llm  # 부트스트랩(KoELECTRA) 쓰려면 run(sentiment)로 호출

items = {
    "P1": ("아쿠아 무선이어폰", "전자"),
    "P2": ("스텐 텀블러 500ml", "주방"),
    "P3": ("데일리 러닝화", "패션"),
    "P4": ("라이트 블루투스 스피커", "전자"),
    "P5": ("보온 도시락통", "주방"),
    "P6": ("베이직 백팩", "패션"),
}

def reviews():
    path = os.path.join(os.path.dirname(__file__), "data", "reviews.csv")
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))

def run(analyzer=absa_llm):  # 기본 LLM ABSA, sentiment(부트스트랩)도 넘길 수 있음
    d = db.get_db()
    d.execute("delete from aspect_sentiment")  # 재실행해도 깨끗하게
    for iid, (name, cat) in items.items():
        d.execute("insert or replace into item values(?,?,?)", (iid, name, cat))

    for r in reviews():
        rid, iid = int(r["review_id"]), r["item_id"]
        d.execute("insert or replace into review values(?,?,?,?)",
                  (rid, iid, r["text"], int(r["rating"])))
        for aspect, senti, conf, ev in analyzer.analyze(r["text"]):
            d.execute("insert into aspect_sentiment(review_id,item_id,aspect,sentiment,confidence,evidence)"
                      " values(?,?,?,?,?,?)", (rid, iid, aspect, senti, conf, ev))
    d.commit()

    print(f"\n{'상품':<16}{'속성':<6}{'긍':>4}{'부':>4}")
    print("-" * 32)
    for name, aspect, pos, neg in db.summary(d):
        print(f"{name:<16}{aspect:<6}{pos:>4}{neg:>4}")

if __name__ == "__main__":
    run()
