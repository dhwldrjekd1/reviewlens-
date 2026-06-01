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
| 핵심 기술 | ABSA(속성별 감성 분석), 설명가능 추천, RAG형 근거기반 챗봇 |
| 스택 | Python, FastAPI, SQLite, KoELECTRA, Ollama(qwen2.5:3b) |
| 실행 환경 | CPU 전용 (torch CPU 휠 + 로컬 LLM) |
| 성과 | ABSA F1 0.84~0.85, 규칙/LLM 두 분석기 비교 평가 체계 구축 |

---

## 시스템 아키텍처 (데이터 흐름)

```
리뷰 → ABSA(속성별 감성) → 감성 저장소(SQLite) ┬→ 추천  (감성을 점수·설명에 반영)
                                                └→ 챗봇  (근거 리뷰로 답변)
```

리뷰 한 건이 들어오면 속성별(`배송·품질·가격·포장·디자인·CS`)로 감성을 분해해 SQLite에 적재합니다. 이 저장소가 추천과 챗봇의 공통 근거가 됩니다.

### 1. ABSA — 속성별 감성 분석 (2-way)
- **규칙 + KoELECTRA**: 규칙 기반 부트스트랩으로 빠르게 라벨 확보 (재현율↑)
- **LLM (qwen2.5:3b)**: Ollama에 JSON 스키마를 강제해 `aspect / sentiment / evidence`를 구조화 추출 (정밀도↑)
- 두 분석기를 같은 인터페이스로 두고 **gold 라벨로 F1 비교**

### 2. 설명가능 추천
- 상품별 속성 긍정비율을 추천 피처로 사용
- 유저가 중시하는 속성 가중치로 점수화 → **구매 기록이 없어도 동작(콜드스타트 OK)**
- `"배송 만족도 92%, 가격 만족도 80%"` 식으로 **추천 이유를 함께 제시**

### 3. 근거기반 챗봇
- 질문에 답할 때 실제 리뷰를 근거로 검색해 LLM이 답변
- "왜 그렇게 답했는지"를 근거 리뷰와 함께 반환

---

## 측정 결과 (ABSA, gold 39 라벨 기준)

| 분석기 | 정밀도 | 재현율 | F1 |
|---|---|---|---|
| 규칙 + KoELECTRA | 0.86 | 0.82 | 0.84 |
| LLM (qwen2.5:3b) | **1.00** | 0.74 | **0.85** |

- 규칙은 재현율↑/정밀도↓, LLM은 정밀도↑/재현율↓ — **정밀도-재현율 트레이드오프**가 뚜렷하고 F1은 거의 동률.
- 결론: 두 방식 모두 천장이 있어 **하이브리드 또는 ABSA 파인튜닝**이 다음 단계.
- 주의: gold 39개·단일 라벨러 기준이라 지표는 *방향성* 수준. 규모를 키우면 재측정 필요.

---

## 기술적 의사결정 (포인트)

- **CPU 전용 제약을 설계 원칙으로**: 학습은 클라우드(Colab GPU), 추론은 로컬 CPU로 분리.
- **LLM 출력 신뢰성**: Ollama `format` 스키마로 JSON 구조를 강제하고 `temperature=0`으로 결정적 추출. `neutral`은 노이즈로 보고 버려 정밀도 확보.
- **콜드스타트 대응**: 상호작용 데이터가 없는 초기엔 협업필터링 대신 투명한 점수 스코어러를 채택 (없는 속성은 0.5 중립 처리).
- **평가 우선**: 기능보다 먼저 gold 라벨 기반 F1 평가 파이프라인을 만들어 두 분석기를 정량 비교.

---

## 실행

```bash
cd reviewlens
pip install -r requirements.txt          # torch는 CPU 휠
# LLM ABSA/챗봇용: Ollama 설치 후
ollama pull qwen2.5:3b

python pipeline.py        # 리뷰 → 감성 저장소 (기본 LLM, sentiment 모드면 규칙)
python eval.py            # 규칙 vs LLM F1
python recommend.py       # 취향별 추천
python chatbot.py         # 근거기반 Q&A
python -m uvicorn app:app # 웹 UI (localhost:8000)
```

---

## 파일 구조

```
reviewlens/
├─ db.py           SQLite 스키마 + 집계 (감성 저장소)
├─ sentiment.py    규칙 + KoELECTRA ABSA (부트스트랩)
├─ absa_llm.py     LLM(Ollama) ABSA, JSON 스키마 강제
├─ pipeline.py     리뷰 → 분석 → 적재
├─ recommend.py    감성 기반 설명가능 추천
├─ chatbot.py      근거 검색 + LLM 답변
├─ eval.py         gold 대비 F1 측정
├─ app.py          FastAPI 웹 UI/API
├─ dashboard.html  대시보드 프런트엔드
├─ data/           reviews.csv(샘플), gold.csv(정답)
└─ docs/           기획서.md
```

---

## 한계 & 다음 단계 (Phase 2)

- **추천**: 현재는 투명한 점수 스코어러. 실제 협업필터링(LightFM)은 상호작용 데이터가 쌓이는 실데이터(Amazon-Reviews-2023) 규모에서 도입 예정.
- **챗봇 검색**: 현재 키워드 기반 → 규모 확장 시 **임베딩(ko-sroberta) + FAISS** 의미검색으로 교체.
- **ABSA**: 재현율 개선을 위해 **Colab GPU에서 파인튜닝**(학습=클라우드, 추론=로컬 CPU) 진행 예정.
