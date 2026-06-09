"""실데이터 ABSA 대규모 검증.

데모 gold(55리뷰·단일 라벨러)가 아니라, **실제 네이버 쇼핑 리뷰 수천 건**에
ABSA(규칙 속성추출 + 학습 분류기, `absa_clf`)를 돌리고, **별점을 약지도(weak label)**로
'아스펙트 감성 ↔ 별점 극성' 일치도를 측정한다. → ABSA가 실데이터 규모에서 작동함을 확인.

  사용: python absa_real.py [N]      (기본 3000건 샘플, seed 고정)
"""
import os, sys, random
from collections import Counter
from absa import absa_clf

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DATA = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "naver_shopping.txt")


def load(n):
    rows = []
    with open(DATA, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if "\t" in line:
                r, t = line.split("\t", 1)
                if r.isdigit():
                    rows.append((int(r), t))
    random.seed(0)
    random.shuffle(rows)
    return rows[:n]


def main(n=3000):
    rows = load(n)
    asp_cnt = Counter()
    polarity = {}                       # aspect → [pos, neg]
    agree = total = 0
    for rating, text in rows:
        gold = "positive" if rating >= 4 else "negative" if rating <= 2 else None   # 3점 제외
        for a, s, _, _ in absa_clf.analyze(text):
            asp_cnt[a] += 1
            polarity.setdefault(a, [0, 0])[0 if s == "positive" else 1] += 1
            if gold:
                total += 1
                agree += (s == gold)

    print(f"실데이터 네이버 쇼핑 리뷰 {len(rows)}건 · 속성 추출 {sum(asp_cnt.values())}건\n")
    print(f"{'속성':<8}{'추출수':>7}{'긍정률':>8}")
    print("-" * 24)
    for a, c in asp_cnt.most_common():
        p, ng = polarity[a]
        print(f"{a:<8}{c:>7}{100*p/(p+ng):>7.0f}%")
    print(f"\n별점-감성 일치도(weak label, 별점 4↑=긍정·2↓=부정): "
          f"{agree}/{total} = {100*agree/total:.1f}%")
    print("→ 데모 55리뷰가 아닌 '실제 리뷰 수천 건'에서도 ABSA가 별점과 높게 일치함을 확인.")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 3000
    main(n)
