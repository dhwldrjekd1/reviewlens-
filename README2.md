# ReviewLens — 개발 일지 (전체 작업·의사결정 기록)

> 이 파일은 ReviewLens를 만들며 거친 **모든 작업·실험·결정·트러블슈팅**을 시간 순/주제별로 빠짐없이 정리한 개발 로그입니다.
> 무엇을 왜 했는지, 어떤 대안을 검토하고 왜 채택/기각했는지까지 남겨 면접·회고에 쓰도록 했습니다.
> (쉬운 설명 → `README1.md`, 기술 상세 → `README.md`)

---

## 0. 프로젝트 한 줄

**온라인 쇼핑 리뷰를 로컬 AI(CPU)가 항목별로 분석 → 장단점·추천·질문답변 + 마케팅 자동화(광고카피·리뷰답글)까지 해주는 풀스택 데모.** 외부 API 비용 0원, 인터넷 없이도 동작.

---

## 1. 작업 타임라인 (큰 흐름)

| 단계 | 주제 | 결과 |
|---|---|---|
| 1 | 챗봇 응답 속도 최적화 | 캐시·템플릿·사전계산으로 대부분 0.2초 즉답 |
| 2 | LLM 모델 비교·선정 | gemma3:4b(라이브) / gemma4:12b(요약) / qwen2.5:3b(ABSA) |
| 3 | 추론 백엔드 검토 | Ollama 채택, llama.cpp는 옵션으로 추상화 |
| 4 | 품질 4대 우선순위 완수 | 대시보드 실데이터·정직한 프레이밍·챗봇평가·스크린샷 |
| 5 | 마케팅 자동화 기능 추가 | AI 광고카피 + AI 리뷰답글 |
| 6 | DB 선택형(SQLite↔Postgres) | 어댑터로 런타임 전환 가능 |
| 7 | 실데이터 대규모 검증 | 네이버 3천건 ABSA 별점 87.2% 일치 |
| 8 | 배포 준비 | Dockerfile·DEPLOY.md (HF Spaces, Ollama 없이도 동작) |
| 9 | 코드 정리·문서화 | 데드코드 제거, README/README1, 트러블슈팅 |
| 10 | 양자화/QAT 심화 검토 | QAT 교체는 위험·마진 작아 **보류 권고** |

---

## 2. 챗봇 속도 최적화 (CPU LLM 한계 극복)

**문제:** CPU 전용 로컬 LLM이라 자유서술형 답변 1건에 ~14초. "빠른 모드"로는 한계.

**핵심 전략 — 질의-시점 LLM 비용을 빌드-시점으로 이동:**
- **답변 캐시 2단**: `_EXACT`(완전일치 dict) + `_CACHE`(의미 유사도 매칭)
- **템플릿 NLG**: 집계·비교·장단점·목록·추천은 LLM 없이 문장 생성
- **사전계산(precompute)**: 빌드 시 상품 15개 자연어 요약을 미리 만들어 DB 저장 → 특정 상품 질문 즉답
- **FAQ 프리워밍**: 서버 기동 시 자주 묻는 질문 미리 데움(`_prewarm` 스레드)

**결과:** 대부분 질문 **0.2초 즉답**, 자유서술형만 실시간 LLM. → 느린 CPU 호출을 실시간 경로에서 거의 제거.

**의도 라우팅(`ground()`):** 질문을 다음으로 분기 —
`aggregate(속성집계)` / `recommend(추천)` / `compare(2개 이상 비교)` / `product(특정상품)` / `product_aspect(상품+속성)` / `proscons(장단점)` / `list(목록)` / `smalltalk(인사)` / `review(RAG 의미검색)`.

---

## 3. LLM 모델 비교·선정 과정

검토하며 실제로 바꿔보고 비교한 모델들:

| 후보 | 검토 결과 |
|---|---|
| qwen2.5:3b | ABSA(JSON 추출)용으로 유지 — 구조화 출력 안정 |
| gemma3:4b | **라이브 채택** — 한국어 품질 좋고 4B라 빠름 |
| gemma4:12b | **요약 전용 채택** — 품질 최상, 12B라 느려 오프라인 빌드 1회만 |

**거친 논의:**
- "올라마 버리고 llama.cpp만 쓰자" → 백엔드를 `RL_BACKEND`로 **추상화**(`_generate`/`_stream_tokens`가 ollama/llamacpp 모두 지원). 단 LangChain은 무거워져 보류.
- gemma4는 Ollama 업데이트가 필요했음(아래 트러블슈팅).
- **사용자 정정:** "gemma4:12b 삭제하지마" → 요약 품질 모델 유지. "Ollama 불필요하면 안 되지, LLM이 핵심" → 배포에 LLM 포함 경로 유지.

**Thinking 모델 처리:** `_THINKING=("gemma4","qwen3")` 는 `body["think"]=False`로 사고출력 끔.

---

## 4. 품질 4대 우선순위 (완벽 진행 요청)

1. **대시보드 → 실데이터 연결**: 목업 제거, `/api/board`가 실제 집계(KPI·속성·카테고리·이슈·상품·인용)를 반환. 9개 탭 전부 실데이터.
2. **작은 데이터 정직한 프레이밍**: "데모 15상품·55리뷰"임을 화면·문서에 명시. 과장 금지.
3. **딥다이브(챗봇 평가)**: `chat_eval.py` — 라우팅/강건성 평가(정상 12 + 엣지 8케이스).
4. **스크린샷**: Chrome 헤드리스로 대시보드 캡처(`--virtual-time-budget`로 비동기 렌더 대기).

---

## 5. 마케팅 자동화 기능 (포트폴리오 "와" 포인트)

마케팅 회사 관점에서 실무에 쓰일 기능을, 모델·코드는 가볍게:

- **AI 광고 카피 생성** (`build_marketing` + `_ad_prompt`): 리뷰 강점 → 광고 문구 자동 생성. 앞 "1./2." 번호는 정규식으로 제거.
- **AI 리뷰 답글 생성** (`build_replies` + `_reply_prompt`): 부정 리뷰에 정중한 판매자 답글 초안 자동 작성.
- **대시보드 노출**: 마케팅 탭에 "✨ AI 광고 카피" 패널, 리뷰 탭에 "💬 AI 리뷰 답글" 패널.
- 모두 빌드-시점 사전계산 → 배포 호스트에 LLM 없어도 결과 표시.

---

## 6. DB 선택형 (SQLite ↔ PostgreSQL)

**요구:** 기본은 가벼운 SQLite, 필요 시 Docker Postgres로 전환(둘 다 다룰 줄 안다는 증명).

**구현(`db.py` 어댑터):**
- `RL_DB` 환경변수로 백엔드 선택(`sqlite` 기본 / `postgres`).
- 단일 `SCHEMA`(item·review·aspect_sentiment·feedback·product_summary·product_copy·review_reply).
- **방언 자동 변환**: `_to_pg()`(`sum()`→`::int`, `?`→`%s`, `insert or replace`→`on conflict`), `_to_pg_ddl()`(`serial`, `current_timestamp::text`).
- `_PgConn`(threading.Lock, autocommit), `psycopg[binary]`.
- `db_migrate.py`: SQLite→Postgres 데이터 복사.

---

## 7. 실데이터 대규모 검증 (8.0점으로)

"55리뷰 toy data 아니냐" 비판에 대응:
- **감성 분류기**: 네이버쇼핑 20만건으로 직접 학습(linear probing).
- **추천 CF**: MovieLens로 LOO 평가(`recommender.py` `load_movielens`·`loo_split`).
- **ABSA 실검증**: `absa_real.py` — 실제 네이버 리뷰 **3,000건**에 ABSA 돌려 별점과 **87.2% 일치** 확인.

---

## 8. 배포 준비 (8.5점으로)

- **Dockerfile**: python:3.12-slim, torch CPU 휠, 포트 `${PORT:-7860}`.
- **DEPLOY.md**: HF Spaces(무료 CPU 16GB) 가이드. **Ollama 없이도** 대시보드 전체 + 챗봇 즉답 동작(사전계산 DB 동봉), 자유서술형만 graceful 폴백.
- **.dockerignore / docker-compose.yml** 추가.
- 데모 DB(`reviewlens/db/reviewlens.db`, 72KB) 강제 추가(`git add -f`)해 배포 즉시 데이터 표시.
- **AWS**: 다음 주 강사님과 진행 예정이라 가이드는 **지금 추가 안 함**(과금 이슈).

---

## 9. 코드 정리·문서화

- `pyflakes`로 데드코드 탐지·제거(예: 미사용 `import numpy`).
- CSS 데드코드 제거 + 폴리시(`static/dashboard.css`).
- `README.md`(기술상세) / `README1.md`(쉬운버전) 업데이트: 마케팅 자동화·실데이터 검증(87.2%)·Postgres·트러블슈팅·데모 스크린샷.

---

## 10. 학습/개념 Q&A (작업 중 정리한 이해)

작업하며 짚고 넘어간 개념들:

- **SQLite vs PostgreSQL**: SQLite=파일 1개·로컬·간편. Postgres=서버·동시성·확장. Docker로 둘 다 다룸.
- **벡터/이진화**: 텍스트를 임베딩으로 수치화(의미를 좌표로). 양자화는 그 수치의 비트수를 줄여 용량↓.
- **RAG란**: 검색(Retrieval)으로 근거 문서를 찾아 LLM 생성(Generation)에 넣는 것. ReviewLens는 ko-sroberta+FAISS로 리뷰 검색 → 로컬 LLM 답변.
- **로컬 실행 가능성**: 임베딩·LLM 모두 CPU 로컬 → 인터넷·API 없이 동작.
- **"RAG 안에 다 들어있나"**: RAG는 파이프라인(검색+생성)이고, 그 안에 임베딩·벡터DB·LLM이 부품으로 들어감.

---

## 11. 양자화 / QAT 심화 검토 (최종 보류)

- 현재 LLM 3종 모두 **Q4_K_M**(4비트, 품질-용량 sweet spot).
- **Gemma 4 메모리 차별점** 정리: PLE(Per-Layer Embeddings, 엣지 E2B/E4B), Shared KV Cache, 하이브리드(sliding-window+global attention+GQA), QAT.
- **QAT(Quantization-Aware Training)**: 학습 중 양자화를 시뮬레이션 → 같은 4비트에서 품질↑.
- **교체 검토 결과 → 보류 권고**:
  - 태그 확인: `gemma3:4b-it-qat`(Q4_0, **4.0GB** — 현재 3.3GB보다 큼).
  - ⚠️ Ollama 이슈 #13454: **Gemma3 QAT gibberish 출력** 보고.
  - 이득(QAT vs Q4_K_M)은 작고(둘 다 4비트), 디스크 2.4GB로 빠듯, 잘 도는 챗봇 깨질 위험.
  - **결론: 현재 Q4_K_M 유지가 ROI상 합리적.**

---

## 12. 트러블슈팅 모음 (실제로 겪고 해결)

| 문제 | 원인 | 해결 |
|---|---|---|
| 커밋 메시지 앞에 `@` 붙음 | PowerShell `@'...'@` 히어독 | `git commit -F -` + bash 히어독 |
| 대시보드 한글 깨짐 | PowerShell Get/Set-Content가 UTF-8 한글을 cp949로 오독·손상 | `git checkout`으로 복구, **이후 Edit 도구/sed만 사용** |
| 디스크 0GB | A/B 테스트용 bge-m3 다운로드가 디스크 가득 채움 | bge-m3 캐시 삭제(2.14GB 회수) |
| 장단점이 단점만 표시 | has_neg/has_pos 로직 + "장단" 누락 | both-case 처리 + "장단"을 has_pos에 추가 |
| Ollama 업데이트 504 | winget 게이트웨이 타임아웃 | `curl.exe -L --retry -C -` 재시도/이어받기 |
| chat_eval이 recommend를 오판 | 모드별 검사 부재 | per-mode 검사로 수정 |
| /static·/tabs 404 | uvicorn 스테일 | 서버 재시작 |

---

## 13. 포트폴리오 점수 추이 (냉정한 자기평가)

- 초기: **~7.5** (기능은 되나 데이터 작고 검증 부족)
- 실데이터 검증 후: **~8.0** (네이버 3천건 87.2%, 20만건 학습, MovieLens)
- 라이브 배포 시: **8.5** (클릭 한 번 데모)

---

## 14. 현재 모델 인벤토리 (2026-06 기준)

**LLM (Ollama·CPU·Q4_K_M):**
- `gemma3:4b`(3.3GB) — 라이브 챗봇 + 광고카피 + 리뷰답글 / 런타임
- `gemma4:12b`(7.6GB) — 상품 요약 / 빌드 전용
- `qwen2.5:3b`(1.9GB) — ABSA / 빌드

**임베딩:** `jhgan/ko-sroberta-multitask`(768d) — 검색·캐시 의미매칭

**감성/분류:**
- `matthewburke/korean_sentiment`(KoELECTRA) — 절 감성 부트스트랩
- `models/sentiment_head.joblib` — 감성 분류 헤드(네이버 20만 학습)
- `models/absa_acd.joblib` — 속성 카테고리 탐지(NIKL, micro-F1 0.66)

**추천:** implicit ALS + 감성 혼합

---

## 15. 남은 작업 / 향후

- [ ] **AWS 배포** — 다음 주 강사님과 진행(과금 이슈로 가이드 보류).
- [ ] (선택) `OLLAMA` URL을 `RL_OLLAMA` 환경변수로 분리 — 배포 유연화.
- [ ] (선택) 면접 예상 Q&A 정리.
- [x] QAT 교체 — 검토 후 **보류**(위 11장).

---

## 16. 핵심 제약 (작업 규칙)

- **라이선스**: 국립국어원(NIKL) 말뭉치(`json/`)는 GitHub 공개 금지 — 코드·결과만.
- **데모 데이터**: 15상품·55리뷰임을 정직하게 명시(과장 금지).
- **한글 파일 편집**: PowerShell Get/Set-Content 금지(손상) → Edit/sed 사용.
