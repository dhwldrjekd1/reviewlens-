"""챗봇 행동 평가 — 기능을 '측정'으로 검증.

RAG 챗봇은 정답이 하나가 아니라 평가가 까다롭다. 그래서 정답 텍스트 일치 대신
'지켜야 할 행동'을 라벨로 두고 측정한다:
  1) 라우팅 정확도   — 질문 의도를 올바른 모드(집계/추천/특정상품/자유)로 분기하는가
  2) 오답상품 회피율 — 일반 질문에 엉뚱한 특정 상품을 단정하지 않는가 (과거 실제 버그)
  3) 근거 충실(상품) — 특정 상품 질문에 그 상품을 실제로 다루는가
  4) 지연                — 경로별 응답 시간(사전계산/캐시 효과 확인)

  실행:  python chat_eval.py
"""
import sys, time
import db, chatbot

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# (질문, 기대 모드, 특정상품 질문이면 그 상품명 / 일반이면 None)
CASES = [
    ("배송 빠른 편인가요?",            "aggregate",  None),
    ("포장 상태는 괜찮나요?",          "aggregate",  None),
    ("품질은 전반적으로 어떤가요?",    "aggregate",  None),
    ("가격대는 합리적인가요?",          "aggregate",  None),
    ("가성비 좋은 거 추천해줘",        "recommend",  None),
    ("품질 좋은 상품 추천해줘",        "recommend",  None),
    ("아쿠아 무선이어폰 어때요?",      "product",    "아쿠아 무선이어폰"),
    ("인덕션 프라이팬 품질 괜찮아요?", "product",    "인덕션 프라이팬"),
    ("데일리 러닝화 발 편한가요?",     "product",    "데일리 러닝화"),
    ("스마트 LED 스탠드 괜찮아요?",    "product",    "스마트 LED 스탠드"),
    ("우드 디퓨저 향 어때요?",         "product",    "우드 디퓨저"),
    ("보온 도시락통 보온 잘 되나요?",  "product",    "보온 도시락통"),
]


def _named_in(ans, names):  # 답변에 등장한 상품명 목록
    return [nm for nm in names if any(len(w) >= 2 and w in ans for w in nm.split())]


def main():
    d = db.get_db()
    names = [n for (n,) in d.execute("select name from item").fetchall()]
    chatbot.ask(d, "워밍업")                          # 콜드스타트(모델 로드) 분리 → 지연은 정상상태 측정

    route_ok = 0
    agg_ok = agg_n = rec_ok = rec_n = prod_ok = prod_n = 0
    lat, rows = [], []

    for q, exp_mode, prod in CASES:
        _, mode, _ = chatbot.ground(d, q)            # 라우팅 판정
        r_ok = (mode == exp_mode)
        route_ok += r_ok

        t = time.time()
        ans, _ = chatbot.ask(d, q)                   # 실제 답변(캐시/사전계산/LLM)
        dt = time.time() - t
        lat.append(dt)

        chk = "-"
        if exp_mode == "aggregate":                  # 일반 질문 → 엉뚱한 상품 단정 금지(과거 버그)
            agg_n += 1
            named = _named_in(ans, names)
            ok = not named; agg_ok += ok
            chk = "회피 OK" if ok else "오답:" + ",".join(named)
        elif exp_mode == "recommend":                # 추천 → 상품을 1개 이상 제시해야
            rec_n += 1
            ok = bool(_named_in(ans, names)); rec_ok += ok
            chk = "제시 OK" if ok else "상품없음"
        else:                                        # 특정 상품 → 그 상품을 실제로 다뤄야
            prod_n += 1
            ok = any(w in ans for w in prod.split() if len(w) >= 2); prod_ok += ok
            chk = "근거 OK" if ok else "MISS"

        rows.append((q[:22], exp_mode, mode, "✓" if r_ok else "✗", chk, dt))

    print(f"{'질문':<24}{'기대':<10}{'실제':<10}{'라우팅':<7}{'행동검증':<16}{'초':>6}")
    print("-" * 80)
    for q, em, am, rk, chk, dt in rows:
        print(f"{q:<24}{em:<10}{am:<10}{rk:<7}{chk:<16}{dt:>6.2f}")

    n = len(CASES)
    print("\n=== 요약 ===")
    print(f"라우팅 정확도        : {route_ok}/{n}  ({100*route_ok/n:.0f}%)")
    print(f"집계 오답상품 회피율 : {agg_ok}/{agg_n}  ({100*agg_ok/agg_n:.0f}%)  ← 일반 질문에 특정 상품 단정 안 함")
    print(f"추천 상품 제시율     : {rec_ok}/{rec_n}  ({100*rec_ok/rec_n:.0f}%)  ← 추천 의도에 상품 제시")
    print(f"특정상품 근거 충실   : {prod_ok}/{prod_n}  ({100*prod_ok/prod_n:.0f}%)  ← 그 상품을 실제로 다룸")
    print(f"평균 지연(정상상태)  : {sum(lat)/len(lat):.2f}s  (최소 {min(lat):.2f} / 최대 {max(lat):.2f})")


if __name__ == "__main__":
    main()
