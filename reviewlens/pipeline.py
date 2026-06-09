import csv, os, sys
import db, absa_llm, chatbot  # 기본 LLM ABSA + 상품 요약 사전계산(chatbot 재사용)

items = {
    "P1": ("아쿠아 무선이어폰", "전자"),
    "P2": ("스텐 텀블러 500ml", "주방"),
    "P3": ("데일리 러닝화", "패션"),
    "P4": ("라이트 블루투스 스피커", "전자"),
    "P5": ("보온 도시락통", "주방"),
    "P6": ("베이직 백팩", "패션"),
    "P7": ("휴대용 가습기", "생활"),
    "P8": ("논슬립 요가매트", "스포츠"),
    "P9": ("극세사 수면바지", "패션"),
    "P10": ("스마트 LED 스탠드", "리빙"),
    "P11": ("인덕션 프라이팬", "주방"),
    "P12": ("컴팩트 보조배터리", "전자"),
    "P13": ("캐주얼 크로스백", "패션"),
    "P14": ("우드 디퓨저", "리빙"),
    "P15": ("접이식 우산", "생활"),
}

def reviews():
    path = os.path.join(os.path.dirname(__file__), "data", "reviews.csv")
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))

def run(analyzer=absa_llm):  # 기본 LLM ABSA, sentiment(부트스트랩)도 넘길 수 있음
    d = db.get_db()
    d.execute("delete from aspect_sentiment")  # 재실행해도 깨끗하게
    for iid, (name, cat) in items.items():
        d.execute("insert or replace into item(item_id,name,category) values(?,?,?)",
                  (iid, name, cat))

    for r in reviews():
        rid, iid = int(r["review_id"]), r["item_id"]
        d.execute("insert or replace into review(review_id,item_id,raw_text,rating) values(?,?,?,?)",
                  (rid, iid, r["text"], int(r["rating"])))
        for aspect, senti, conf, ev in analyzer.analyze(r["text"]):
            d.execute("insert into aspect_sentiment(review_id,item_id,aspect,sentiment,confidence,evidence)"
                      " values(?,?,?,?,?,?)", (rid, iid, aspect, senti, conf, ev))
    d.commit()

    print(f"\n{'상품':<16}{'속성':<6}{'긍':>4}{'부':>4}")
    print("-" * 32)
    for name, aspect, pos, neg in db.summary(d):
        print(f"{name:<16}{aspect:<6}{pos:>4}{neg:>4}")

    print("\n[상품 요약 사전계산 중...]")
    try:
        n = chatbot.build_product_summaries(d)
        print(f"[상품 요약 {n}건 생성 완료]")
    except Exception as e:
        print(f"[상품 요약 생략: {e}]")   # Ollama 미가동 등 — ABSA 결과는 보존

    print("[AI 광고 카피 생성 중...]")
    try:
        n = chatbot.build_marketing(d)
        print(f"[광고 카피 {n}건 생성 완료]")
    except Exception as e:
        print(f"[광고 카피 생략: {e}]")

if __name__ == "__main__":
    # python pipeline.py [llm|clf|rule]  (기본 llm)
    mode = sys.argv[1] if len(sys.argv) > 1 else "llm"
    if mode == "clf":
        import absa_clf as analyzer
    elif mode == "rule":
        import sentiment as analyzer
    else:
        analyzer = absa_llm
    print(f"[analyzer: {mode}]")
    run(analyzer)
