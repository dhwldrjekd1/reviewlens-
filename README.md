# ReviewLens

> 리뷰 텍스트를 **속성별 감성 분석 → 설명가능 추천 → 근거기반 챗봇**으로 잇는 리뷰 분석 플랫폼

**제작: 최동윤**

리뷰에서 추출한 속성별 감성(ABSA)을 단일 저장소에 적재하고, 그 감성을 **추천의 점수·설명**과 **챗봇 답변의 근거**로 재사용하는 것이 핵심입니다. 세 기능이 따로 노는 게 아니라 하나의 데이터 흐름으로 연결됩니다.

전 과정은 **CPU 전용** 환경에서 동작하도록 설계했습니다 (LLM은 로컬 Ollama 추론).

---

## 한눈에 보기

| 항목 | 내용 |
|---|---|
| 한 줄 소개 | 리뷰 감성을 추천·챗봇의 근거로 재사용하는 통합 리뷰 분석 플랫폼 |
| 핵심 기술 | ABSA(속성별 감성 분석), 협업필터링+감성 하이브리드 추천, 의미검색 RAG 챗봇, 마케팅 자동화(AI 광고 카피·리뷰 답글) |
| 스택 | Python, FastAPI, SQLite, KoELECTRA, Ollama(gemma3:4b 챗봇·gemma4:12b 요약·qwen2.5:3b ABSA), implicit(ALS), ko-sroberta+FAISS |
| 실행 환경 | CPU 전용 (torch CPU 휠 + 로컬 LLM) |
| 성과 | ABSA F1 0.93(gold 101), 추천 블렌딩 Recall@10 0.31(>popularity 0.19), 속성 학습(NIKL ACD micro-F1 0.66) |

> ⚠️ **데이터 규모(정직)**: ABSA 평가는 **데모 데이터셋(15상품·55리뷰·gold 101, 단일 라벨러)** 기준입니다. 절대 수치의 통계적 일반화보다 **방법 간 상대 비교와 파이프라인 검증**이 목적이에요. 추천은 실로그가 없어 **합성 시뮬레이션 데이터**로 평가했습니다(데이터 로더만 교체하면 실데이터 확장). 감성 분류기 학습만 **네이버쇼핑 200k 실데이터**입니다.

---

## 데모 화면

**분석 대시보드** (`/dashboard`) — 속성 감성·개선 이슈·전략 카드를 **실데이터로 실시간 산출**:

![분석 대시보드](reviewlens/docs/img/dashboard.png)

**AI 마케팅 카피** (`/dashboard#market`) — 리뷰 강점(디자인 94%·배송 83% 등)을 **광고 문구로 자동 생성**. 인사이트를 마케팅 산출물로:

![AI 광고 카피](reviewlens/docs/img/market.png)

**AI 리뷰 답글** (`/dashboard#review`) — 부정 리뷰마다 정중한 판매자 답글 초안을 자동 생성(평판관리 자동화):

![AI 리뷰 답글](reviewlens/docs/img/review.png)

| 랜딩 (`/`) | CS 챗봇 (`/cs`) |
|---|---|
| ![랜딩](reviewlens/docs/img/index.png) | ![CS 챗봇](reviewlens/docs/img/cs.png) |

> 대시보드의 모든 수치(긍정률 70.3%·속성 점수·기회 맵·Top 이슈·전략 카드)는 데모 데이터셋(15상품·55리뷰)에서 `/api/board`로 **실시간 집계**됩니다 — 하드코딩 목업이 아닙니다.

---

## 시스템 아키텍처 (데이터 흐름)

```
리뷰 → ABSA(속성별 감성) → 감성 저장소(SQLite) ┬→ 추천  (감성을 점수·설명에 반영)
                                                └→ 챗봇  (근거 리뷰로 답변)
```

리뷰 한 건이 들어오면 속성별(`배송·품질·가격·포장·디자인·CS`)로 감성을 분해해 SQLite에 적재합니다. 이 저장소가 추천과 챗봇의 공통 근거가 됩니다.

### 1. ABSA — 속성별 감성 분석 (3-way, 교체 가능)
- **규칙 + KoELECTRA**: 키워드 속성 추출 + 절 분리 + KoELECTRA 감성 (부트스트랩)
- **LLM (qwen2.5:3b)**: Ollama에 JSON 스키마를 강제해 `aspect / sentiment / evidence`를 구조화 추출
- **규칙 + 학습분류기**: 속성 추출은 규칙 공유, 감성만 도메인 학습 분류기(네이버쇼핑)로 교체 → **F1 0.92로 최고**
- 세 분석기를 같은 인터페이스(`analyze(text)`)로 두고 **gold 라벨로 F1 비교** (속성 추출 규칙은 `aspect_rules.py`로 공유)

### 2. 추천 — 협업필터링 + 감성 하이브리드
- **협업필터링(implicit ALS)**: user-item 상호작용에서 잠재요인을 학습해 개인화 추천
- **감성 블렌딩**: ABSA 감성 점수를 콘텐츠 신호로 섞어(`0.7·CF + 0.3·감성`) 정확도·설명력 강화
- **콜드스타트 fallback**: 상호작용이 없는 신규 유저는 감성 스코어러로 폴백 → `"배송 만족도 92%, 가격 만족도 80%"` 식 설명과 함께 추천
- **시간 기반 분할** 평가로 popularity 베이스라인과 비교 (랜덤 분할의 미래→과거 누수 회피)

### 3. 근거기반 챗봇 (의미검색 RAG + 자기개선)
- **의미검색**: 리뷰 원문을 ko-sroberta로 임베딩해 FAISS 인덱스로 만들고, 질문도 같은 공간에 임베딩해 **의미가 가까운 근거 리뷰**를 검색 (키워드 불일치도 검색)
- 검색된 리뷰(+속성 감성 라벨)를 프롬프트 근거로 넣어 LLM이 답변 → 근거 함께 반환
- **자기검증(self-check)**: 답하기 전 "근거에 충실한지" 모델이 스스로 판정해, 환각이면 재생성 (자동 오류 수정)
- **교정 메모리**: 사용자 👍/👎·정정을 저장하고, 다음에 **의미가 비슷한 질문**이 오면 그 정정을 근거보다 우선 주입 → *모델 재학습 없이* 대화로 즉시 개선 (모델 가중치를 안 건드려 catastrophic forgetting 없음)
- **한국어 보정**: 한자·코드스위칭 감지 시 삭제가 아니라 재생성으로 문법 보존
- **graceful fallback**: 의미검색은 LLM 없이도 동작 → Ollama 미가동 시에도 근거 리뷰를 반환

#### 응답 최적화 (CPU에서 즉답 서빙)
CPU 로컬 LLM은 신규 질문에 수~십수 초가 걸리므로, **실시간 경로에서 LLM 호출 자체를 최대한 제거**했습니다.
- **의도 라우팅**: 질문을 분기 — *집계*("배송 어때?")·*추천*("가성비 추천")·*비교*("A vs B")·*장단점*·*특정상품+속성*("○○ 배송 어때?")·*상품목록*·*인사/도움*까지 **전부 리뷰 근거로 즉답**(LLM 생략), *특정 상품*("○○ 어때?")은 **빌드 시 미리 생성한 상품 요약**으로, 자유서술형만 실시간 RAG. 무관/난센스는 관련도 가드로 **안전 거절**.
- **상품 요약 사전계산**: 오프라인(빌드 시)에 상품별 자연어 요약을 `gemma4:12b`로 생성·저장 → 질의 시점 LLM 비용을 빌드 시점으로 이동. 품질 손실 없이 특정 상품 질문도 **<0.2초**.
- **답변 캐시 + FAQ 프리워밍**: 완전일치(dict)·의미유사(임베딩) 캐시로 반복/유사 질문 즉시 응답, 자주 묻는 질문은 서버 시작 시 백그라운드로 미리 데움.
- **모델 분리**: 라이브 챗봇 = 빠른 `gemma3:4b`, 오프라인 요약 = 고품질 `gemma4:12b`(thinking off로 한국어 보장), ABSA = `qwen2.5:3b`. 자유서술형(상품·속성 미특정) 질문만 실시간 LLM 사용.
- **백엔드 교체 가능**: 기본 Ollama, `RL_BACKEND=llamacpp`로 `llama-server` 직접 호출도 지원(둘 다 내부 엔진은 llama.cpp).

#### 챗봇 행동 평가 (`chat_eval.py`)
RAG 챗봇은 정답 텍스트가 하나가 아니라, **'지켜야 할 행동'을 라벨로 두고 측정** — 해피패스 12 + **적대적·엣지 8 시나리오**.

| 지표 | 결과 | 의미 |
|---|---|---|
| 라우팅 정확도 | **12/12 (100%)** | 질문 의도를 올바른 모드(집계/추천/특정상품)로 분기 |
| 집계 오답상품 회피율 | **4/4 (100%)** | 일반 질문에 엉뚱한 특정 상품을 단정하지 않음 |
| 추천 상품 제시율 | **2/2 (100%)** | 추천 의도에 실제 상품 제시 |
| 특정상품 근거 충실 | **6/6 (100%)** | 질문이 지목한 상품을 실제로 다룸 |
| **적대적·엣지 robustness** | **8/8 (100%)** | 인젝션 방어 + 오타·미등록상품·난센스에 **안전한 거절** |
| 평균 지연(정상상태) | **0.12s** | 사전계산·캐시로 즉답(콜드스타트 분리 측정) |

**적대적 테스트가 실제 버그를 잡음**: *"갤럭시 버즈 어때요?"*(미등록)·오타·난센스에 *엉뚱한 카탈로그 상품을 자신있게 단정*하던 실패를 발견 → 의미검색 폴백에 **관련도 임계값(0.45) 가드**를 넣어, 관련 리뷰가 없으면 단정 대신 안내로 거절하도록 수정. 정직한 한계도 명시: *절차성 질문("환불 어떻게?")은 CS 감성집계로 답함 — 감성 분석기지 FAQ봇이 아님.*

| 질문 (정답 리뷰와 단어 안 겹침) | 키워드 검색 top1 | 의미검색 top1 |
|---|---|---|
| "이어폰 **소리** 괜찮아?" | 텀블러 색상·가성비 ❌ | 스피커 "소리는 좋은데…" ✅ |
| "물건 **늦게** 오나요?" | 러닝화 교환응대 ❌ | 백팩 "배송이 너무 느렸고…" ✅ |

→ 키워드는 글자가 겹쳐야만 찾지만, 의미검색은 표현이 달라도 같은 의미의 리뷰를 찾음.

---

## 측정 결과 (ABSA, gold 101 라벨 기준 · 15상품·55리뷰)

| 분석기 | 정밀도 | 재현율 | F1 |
|---|---|---|---|
| 규칙 + KoELECTRA | 0.92 | 0.90 | 0.91 |
| LLM (qwen2.5:3b) | **0.96** | 0.80 | 0.88 |
| **규칙 + 학습분류기(네이버쇼핑)** | **0.94** | **0.92** | **0.93** |

- LLM은 정밀도↑/재현율↓(보수적), 학습분류기가 **F1 0.93으로 최고** — 쇼핑 도메인 학습이 범용 KoELECTRA·LLM을 앞섬.
- **gold를 39→101개로 확대**(상품 6→15·리뷰 18→55) 재측정 — 표본이 커져 이전보다 신뢰도↑. (단일 라벨러 한계는 남음)
- 속성 추출은 세 방식 공통으로 규칙(`aspect_rules.py`) 기반 → *학습 기반 속성 추출*은 아래 NIKL ACD에서 별도 실험.

---

## 측정 결과 (추천, 시간 기반 분할 · `recommender.py`)

상호작용 로그가 없어, 잠재 취향 구조를 심은 **합성 상호작용 시뮬레이터**(유저 600·아이템 160·상호작용 ~9k, seed 고정)로 학습·평가했습니다. 데이터 로더만 교체하면 실데이터로 확장되며, 실제로 **CF 백본은 아래 MovieLens로 교차검증**했습니다(합성 과적합 아님 확인).

| 유저 그룹 | 방법 | Recall@10 | NDCG@10 |
|---|---|---|---|
| 따뜻한 유저 (n=143) | popularity (baseline) | 0.185 | 0.191 |
| | implicit ALS (CF) | 0.201 | 0.224 |
| | **ALS + 감성 블렌딩** | **0.310** | **0.331** |
| 콜드스타트 (n=47) | popularity (baseline) | 0.156 | 0.211 |
| | **감성 스코어러 fallback** | **0.260** | **0.352** |

- **하이브리드 효과**: 순수 CF(0.201)는 인기도(0.185)를 소폭 상회하는 데 그치지만, **감성을 블렌딩하면 0.310**으로 크게 향상 — 협업 신호가 희소할 때 콘텐츠(감성) 신호가 메우는 하이브리드 가설을 실측으로 확인.
- **콜드스타트**: 상호작용이 0인 신규 유저에서 감성 스코어러(0.260)가 인기도(0.156)를 명확히 상회 → ABSA 감성을 추천 피처로 재사용한 효과.
- 누수 방지를 위해 **전역 시간 컷오프**로 분할(랜덤 분할 금지). 합성 데이터라 절대값보다 *방법 간 상대 비교*가 핵심.

### 실데이터 CF 백본 검증 (MovieLens-small · leave-last-out)
"CF가 합성 데이터에 과적합된 것 아니냐"는 의심을 없애려 **공개 벤치마크로 교차검증**. MovieLens엔 속성 만족도 라벨이 없어 감성 블렌딩은 검증 불가 → CF(pop vs ALS)만, 표준 **leave-last-out**(유저별 시간순 마지막을 test).

| 방법 | Recall@10 | NDCG@10 |
|---|---|---|
| popularity (baseline) | 0.039 | 0.022 |
| **implicit ALS (CF)** | **0.074** | **0.040** |

- 608 warm 유저 · 48,580 상호작용(평점≥4를 암묵 양성). **ALS가 인기도를 ~1.9× 상회** → CF 구현이 합성 데이터 덕이 아님을 실데이터로 확인.
- 한계(정직): 감성 블렌딩(아스펙트 사이드피처)은 *상호작용 + 속성 라벨이 함께 있는* 공개 데이터가 없어 합성으로만 평가. 실 쇼핑 로그(Amazon-Reviews 등) 확보 시 동일 인터페이스(`load_*`)로 확장.
- 실행: `python recommender.py movielens` (데이터는 코드가 자동 다운로드, 저장소 미포함)

---

## 측정 결과 (감성 분류기 학습, linear probing · `sentiment_finetune.py`)

gold은 *평가용*이라 학습엔 부족 → **네이버쇼핑 리뷰 200k**(도메인 일치, 평점 1~5 → 긍/부정)로 감성 분류기를 학습. CPU 제약상 전체 파인튜닝 대신 **linear probing**(ko-sroberta 인코더 동결 + 임베딩 캐시 → 로지스틱 회귀 헤드만 학습)으로 수 분 내 완료.

| 방법 | 정확도 | 정밀도 | 재현율 | F1 |
|---|---|---|---|---|
| 다수클래스 baseline | 0.500 | – | – | – |
| **linear probing (헤드 학습)** | **0.914** | 0.915 | 0.912 | **0.914** |

- 균형 표본 16k(긍/부정 8k씩), 테스트 3.2k. baseline 0.5 대비 **F1 0.914**.
- 우리 리뷰(쇼핑 도메인)에 적용해도 별점과 일치(별점5→긍정 0.92, 별점1→부정 0.00) — **도메인 전이 확인**.
- **ABSA 파이프라인에 통합**: 이 분류기를 규칙 속성 추출과 결합한 분석기(`absa_clf.py`)가 gold F1 **0.93** 달성(위 ABSA 표) — 학습이 실제 성능 향상으로 이어짐을 확인.
- 한계: 이 데이터는 **문장 단위 감성**이라 *속성 구분은 학습 안 됨*. 즉 '감성 분류'만 개선하고 **속성 추출은 규칙이 담당** → 아래 NIKL ACD에서 속성 추출까지 학습.

---

## 측정 결과 (속성 카테고리 학습, NIKL ABSA · `absa_nikl_train.py`)

속성 추출을 규칙(키워드)이 아니라 **데이터로 학습** — **국립국어원 속성 기반 감성 분석 말뭉치(2021)** 의 쇼핑 도메인(제품·전자기기·화장품, 776문서)으로 `엔티티#속성` 카테고리를 멀티라벨 분류(ACD). CPU라 linear probing(ko-sroberta 동결 + OneVsRest 로지스틱).

| 방법 | micro-F1 | macro-F1 |
|---|---|---|
| 빈도 베이스라인(top2) | 0.621 | – |
| **linear probing** | **0.659** | 0.189 |
| linear probing(balanced) | 0.542 | 0.381 |

- 14개 카테고리(출현 20회↑), 테스트 156문서. 베이스라인 0.621 → **0.659**로 학습 효과 확인.
- **불균형 트레이드오프**: 말뭉치가 `본품#품질`·`제품 전체#일반`에 쏠려 기본 모델은 micro↑/희소 카테고리(macro)↓. `class_weight=balanced`로 macro 0.19→0.38↑(대신 micro↓).
- 한계(정직): 인코더 동결 linear probing은 세분 카테고리 탐지에 천장이 있음 → **롱테일은 GPU 전체 파인튜닝**이 다음 레버.
- **데이터 라이선스**: 국립국어원 배포(재배포 금지) → **원본은 저장소에 미포함**(`.gitignore`). 코드·결과만 공개. 받는 법은 아래 *데이터* 참고.

---

## 기술적 의사결정 (포인트)

- **CPU 전용 제약을 설계 원칙으로**: 학습은 클라우드(Colab GPU), 추론은 로컬 CPU로 분리.
- **LLM 출력 신뢰성**: Ollama `format` 스키마로 JSON 구조를 강제하고 `temperature=0`으로 결정적 추출. `neutral`은 노이즈로 보고 버려 정밀도 확보.
- **콜드스타트 대응**: 상호작용이 없는 신규 유저는 협업필터링이 불가능 → 감성 스코어러로 폴백(없는 속성은 0.5 중립 처리)해 첫 추천부터 동작.
- **죽은 의존성 회피(LightFM→implicit)**: 당초 LightFM 하이브리드를 계획했으나 유지보수가 끊겨 Python 3.12 + 최신 setuptools/numpy 2.x에서 빌드 불가. 유지보수되는 `implicit`(ALS)로 CF 백본을 옮기고, LightFM의 *아이템 사이드피처(감성)* 역할은 감성 스코어러 블렌딩으로 대체.
- **RAG 견고성**: 챗봇은 검색(ko-sroberta+FAISS)과 생성(LLM)을 분리 — 의미검색은 LLM 없이도 동작하므로, Ollama가 꺼져 있어도 500 대신 근거 리뷰를 반환하도록 fallback 설계.
- **학습 대신 외부 메모리(자기개선)**: 챗봇을 "대화로 개선"하되 LLM 가중치를 재학습하지 않음. 사용자 정정을 외부 메모리에 쌓아 RAG로 주입 → 즉시 반영 + **지식 보존**(가중치를 안 바꾸니 catastrophic forgetting 자체가 없음). 희소·노이즈 피드백으로 모델을 망치는 위험을 회피.
- **CPU에서 학습하기(linear probing)**: GPU 없이 감성 분류기를 학습하려고 전체 파인튜닝 대신 인코더를 동결하고 임베딩을 캐시한 뒤 가벼운 헤드만 학습. forward 한 번이면 끝나 CPU로도 수 분. baseline 0.5 → F1 0.914로 실효성 확인.
- **평가 우선**: 기능보다 먼저 평가 파이프라인을 구축 — ABSA는 gold F1, 추천은 시간 분할 Recall@K/NDCG@K로 베이스라인 대비 정량 비교.

---

## 실행

```bash
python -m venv .venv && .venv\Scripts\activate   # (권장) 가상환경
cd reviewlens
pip install -r requirements.txt          # torch는 CPU 휠
# Ollama 설치 후 — ABSA: qwen2.5:3b, 라이브 챗봇: gemma3:4b, 오프라인 요약: gemma4:12b
ollama pull qwen2.5:3b
ollama pull gemma3:4b
ollama pull gemma4:12b

python pipeline.py [llm|clf|rule]  # 리뷰 → 감성 저장소 (분석기 선택, 기본 llm)
python eval.py            # ABSA 3-way F1 비교 (규칙/LLM/학습분류기)
python recommend.py       # 취향별 설명가능 추천 (phase 1 스코어러)
python recommender.py     # 협업필터링(ALS)+감성 블렌딩 추천 + 시간분할 평가(합성)
python recommender.py movielens  # 실데이터 CF 백본 검증(MovieLens, leave-last-out)
python retriever.py       # 키워드 vs 의미검색(ko-sroberta+FAISS) 비교 데모
python sentiment_finetune.py  # 네이버쇼핑 200k로 감성 분류기 학습(linear probing)+평가
python absa_nikl_train.py     # 국립국어원 ABSA로 속성 카테고리 탐지(ACD) 학습 (json/ 필요)
python chatbot.py         # 의미검색 RAG Q&A (LLM 없으면 근거만 반환)
python chat_eval.py       # 챗봇 행동 평가 (라우팅·오답상품 회피·근거 충실·지연)
python -m uvicorn app:app # 웹 UI (localhost:8000)
```

---

## 데이터베이스 — SQLite(기본) · Postgres(선택)

기본은 **SQLite**입니다. 임베디드(파일 1개)·제로셋업이라 *"`uvicorn` 하나로 로컬·오프라인 동작"*이라는 이 프로젝트 설계와 맞습니다 (단일 사용자 분석 도구엔 SQLite가 적합).

동시에 **다중 사용자·다중 서버 프로덕션을 가정한 Postgres 백엔드**를 `RL_DB` 환경변수로 전환할 수 있게 했습니다. 코드의 SQL은 **한 벌(SQLite 기준)** 만 두고, `db.py`의 얇은 어댑터가 방언 차이를 자동 변환합니다 — *리포지토리 패턴으로 백엔드 교체*.

| SQLite | → Postgres 자동 변환 |
|---|---|
| `?` 플레이스홀더 | `%s` |
| `sum(sentiment='positive')` | `sum((…)::int)` |
| `insert or replace into …` | `insert … on conflict … do update` |
| `integer primary key autoincrement` | `serial primary key` |

```bash
# 기본: SQLite (Docker 불필요)
python -m uvicorn app:app

# Postgres로 전환 (Docker)
docker compose up -d                 # Postgres 컨테이너 기동
python reviewlens/db_migrate.py      # SQLite 데이터 → Postgres 복사 (ABSA 재실행 불필요)
RL_DB=postgres python -m uvicorn app:app
```

> **왜 둘 다?** "55행에 Postgres"는 과잉이라 SQLite가 *맞는 선택*이지만, 백엔드 직무에선 Postgres가 표준입니다. 그래서 **전환 가능하게 설계**해 *도구 선택의 판단력 + 양쪽 역량*을 함께 보였습니다. 두 백엔드에서 **동일 결과**(긍정률 70.3%, 속성 집계, 상품 요약, 대시보드 board 쿼리)를 검증했습니다.

---

## 트러블슈팅

| 증상 | 원인 / 해결 |
|---|---|
| 챗봇이 답을 못 만듦 / `(LLM 응답 생략)` | Ollama 서버 미가동 → `ollama serve`(또는 Ollama 앱 실행). 모델 없음 → `ollama pull gemma3:4b` |
| 첫 질문이 십수 초 걸림 | CPU에서 ko-sroberta·LLM **콜드 로드**(최초 1회). 이후엔 캐시·사전계산으로 즉답. GPU면 빠름 |
| 최초 실행에서 모델 다운로드가 멈춤 | ko-sroberta는 첫 실행에 HuggingFace에서 1회 다운로드(인터넷 필요). 이후 오프라인(`HF_HUB_OFFLINE=1`) |
| `/static`·`/tabs` 404 | 서버를 **`reviewlens/`에서** 실행했는지 확인(StaticFiles 상대경로). 코드 수정 후엔 서버 재시작 |
| 대시보드가 빈 화면 / 옛 데이터 | 브라우저 캐시 → **Ctrl+Shift+R**. 데이터가 없으면 `python pipeline.py`로 재빌드 |
| 포트 8000 사용 중 | 기존 uvicorn 종료 후 재실행 (`--port 8001`로 포트 변경 가능) |
| 한글 깨짐 (cp949, Windows) | `set PYTHONUTF8=1` 후 실행 (스크립트는 `sys.stdout.reconfigure` 적용됨) |
| Postgres 연결 거부 | `docker compose up -d` 기동 → `python db_migrate.py` 시드 → `RL_DB=postgres` 실행. 컨테이너 healthy 대기 확인 |
| `absa_nikl_train.py`가 동작 안 함 | 국립국어원 말뭉치(라이선스)는 미포함 → `json/`에 직접 넣어야 함(선택 기능) |
| 디스크 부족 | LLM 모델이 큼(수 GB). 안 쓰는 Ollama 모델은 `ollama rm <이름>`으로 정리 |

---

## 파일 구조

```
reviewlens/
├─ db.py           DB 어댑터(감성 저장소) — SQLite 기본 / Postgres(RL_DB) 전환, 방언 자동 변환
├─ db_migrate.py   SQLite → Postgres 데이터 복사 (Docker Postgres 시드)
├─ aspect_rules.py 속성 사전 + 절 분리 (분석기 공유)
├─ sentiment.py    규칙 + KoELECTRA ABSA (부트스트랩)
├─ absa_llm.py     LLM(Ollama) ABSA, JSON 스키마 강제
├─ absa_clf.py     규칙 속성 + 학습 분류기 감성 ABSA (phase 2)
├─ pipeline.py     리뷰 → 분석 → 적재
├─ recommend.py    감성 기반 설명가능 추천 (phase 1 스코어러)
├─ recommender.py  협업필터링(ALS)+감성 블렌딩 추천 + 시뮬레이터·평가 (phase 2)
├─ retriever.py    ko-sroberta + FAISS 의미검색 리트리버 (phase 2)
├─ sentiment_finetune.py  네이버쇼핑 200k 감성 분류기 학습 (linear probing, phase 2)
├─ absa_nikl.py    국립국어원 ABSA 말뭉치 로더 (쇼핑 도메인)
├─ absa_nikl_train.py  속성 카테고리 탐지(ACD) 학습·평가 (linear probing)
├─ chatbot.py      의미검색 RAG + 의도 라우팅 + 사전계산/캐시 + 교정 메모리
├─ eval.py         gold 대비 ABSA F1 측정 (python eval.py [llm])
├─ chat_eval.py    챗봇 행동 평가 (라우팅·환각 회피·근거·지연)
├─ app.py          FastAPI 웹 UI/API (+ /api/board 대시보드 실집계)
├─ dashboard.html  대시보드 프런트엔드
├─ data/           reviews.csv(샘플), gold.csv(정답)
└─ docs/           기획서.md

json/                 국립국어원 ABSA 말뭉치 (라이선스, .gitignore — 저장소 미포함)
```

---

## 한계 & 다음 단계

- **추천 (구현됨, Phase 2)**: 협업필터링(implicit ALS) + 감성 블렌딩 + 콜드스타트 폴백까지 구현·평가 완료. 다음은 **실데이터(Amazon-Reviews-2023)** 로더 연결로 합성 시뮬레이터를 대체.
- **챗봇 의미검색 (구현됨, Phase 2)**: 키워드 → **ko-sroberta + FAISS** 의미검색으로 교체 완료(LLM 없이도 동작하는 fallback 포함). 다음은 규모 확장 시 IVF/HNSW 인덱스, 임베딩 캐시.
- **ABSA 감성 분류기 (구현·통합됨, Phase 2)**: 네이버쇼핑 200k로 CPU linear probing 학습(F1 0.914) → 규칙 속성 추출과 결합해 ABSA에 통합(gold F1 0.93, 기존 0.91 대비↑).
- **속성 추출 학습 (구현됨)**: 국립국어원 ABSA 말뭉치로 속성 카테고리 탐지(ACD)를 학습(micro-F1 0.66 > baseline 0.62) → 규칙 의존을 데이터 학습으로 대체. 다음은 **GPU 전체 파인튜닝**으로 롱테일 카테고리·극성(ASC)까지 개선.

---

## 데이터

| 데이터 | 용도 | 공개 여부 |
|---|---|---|
| `data/reviews.csv`·`gold.csv` | 데모·ABSA 평가 (15상품·55리뷰·101 gold) | 저장소 포함 |
| 네이버쇼핑 리뷰 200k | 감성 분류기 학습 | 코드로 자동 다운로드(공개) |
| MovieLens-small (10만 평점) | CF 백본 검증 | 코드로 자동 다운로드(공개) |
| **국립국어원 ABSA 말뭉치 2021** | 속성 카테고리 학습(ACD) | **라이선스상 비공개** — 미포함 |

> 국립국어원 말뭉치는 [모두의 말뭉치](https://kli.korean.go.kr/corpus/main/requestMain.do)에서 **"속성 기반 감성 분석 말뭉치"** 를 신청·동의 후 받아 `json/`에 넣으면 `absa_nikl_train.py`가 동작합니다. 재배포 금지라 본 저장소엔 원본을 포함하지 않습니다(코드·결과만 공개).
