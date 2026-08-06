import csv, os, sys
from store import db
from absa import absa_llm
from chat import chatbot  # 기본 LLM ABSA + 상품 요약 사전계산(chatbot 재사용)

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
    # SQLite는 커밋 없이 실행한 쓰기가 암묵적 트랜잭션에 계속 쌓여, 뒤이은 첫 d.transaction()
    # 블록(아래 리뷰 루프)이 실패해 롤백되면 이 무관한 item insert들까지 같이 날아갈 수 있었음
    # (교차검증에서 발견). 여기서 바로 커밋해 리뷰 루프와 트랜잭션 경계를 분리
    with d.transaction():
        for iid, (name, cat) in items.items():
            d.execute("insert or replace into item(item_id,name,category) values(?,?,?)",
                      (iid, name, cat))

    failed = 0
    for r in reviews():
        rid, iid = int(r["review_id"]), r["item_id"]
        with d.transaction():   # 리뷰 원문은 분석 전에 바로 커밋 — 아래 analyze()가 오래 걸려도 락을 물고 있지 않게
            d.execute("insert or replace into review(review_id,item_id,raw_text,rating) values(?,?,?,?)",
                      (rid, iid, r["text"], int(r["rating"])))
        try:  # 리뷰 1건 분석 실패(긴 텍스트, LLM 응답 파싱 실패 등)해도 나머지가 죽지 않게
            results = analyzer.analyze(r["text"])   # 트랜잭션 밖에서 실행 — 수 초~분 걸려도 락 무관
        except Exception as e:
            failed += 1
            print(f"[리뷰 {rid} 분석 실패, 건너뜀: {e}]")
            with d.transaction():
                d.execute("delete from aspect_sentiment where review_id=?", (rid,))  # 이전 결과는 비움
            continue
        # analyze()가 끝난 뒤에야 delete+insert를 열어, 이 리뷰 하나의 delete+insert가 항상 같은
        # (짧은) 트랜잭션 안에서 원자적으로 끝나게 함 — 커밋 전에 죽어도 이전 데이터가 그대로
        # 남아있고, 트랜잭션도 이 짧은 구간에만 걸려 동시 요청(/api/feedback 등)을 막지 않음
        with d.transaction():
            d.execute("delete from aspect_sentiment where review_id=?", (rid,))
            for aspect, senti, conf, ev in results:
                d.execute("insert into aspect_sentiment(review_id,item_id,aspect,sentiment,confidence,evidence)"
                          " values(?,?,?,?,?,?)", (rid, iid, aspect, senti, conf, ev))
    if failed:
        print(f"[분석 실패 {failed}건 — 해당 리뷰는 원문만 저장되고 속성/감성은 비어있음]")

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

    print("[AI 리뷰 답글 생성 중...]")
    try:
        n = chatbot.build_replies(d)
        print(f"[리뷰 답글 {n}건 생성 완료]")
    except Exception as e:
        print(f"[리뷰 답글 생략: {e}]")

if __name__ == "__main__":
    # python pipeline.py [llm|clf|rule]  (기본 llm)
    mode = sys.argv[1] if len(sys.argv) > 1 else "llm"
    if mode == "clf":
        from absa import absa_clf as analyzer
    elif mode == "rule":
        from absa import sentiment as analyzer
    else:
        analyzer = absa_llm
    print(f"[analyzer: {mode}]")
    run(analyzer)
