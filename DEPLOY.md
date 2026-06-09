# 배포 가이드 — 라이브 데모 (Hugging Face Spaces · 무료 CPU)

대시보드 전체 + 챗봇 즉답(집계·추천·비교·특정상품·장단점·인사)은 **Ollama 없이 동작**합니다.
사전계산된 데모 DB(요약·광고카피·리뷰답글)를 함께 실어 호스트엔 LLM 서버가 필요 없습니다.
*자유서술형* 질문만 LLM이 없어 "근거 리뷰 반환"으로 graceful 폴백합니다.

## 1) Space 생성
- https://huggingface.co/new-space → **SDK: Docker**, 하드웨어: **CPU basic(무료, 16GB)**

## 2) 코드 올리기
이 저장소를 Space에 푸시(또는 GitHub 연동). Space `README.md` 최상단에 헤더만 추가하면 포트를 인식합니다:
```yaml
---
title: ReviewLens
emoji: 🛍️
colorFrom: pink
colorTo: indigo
sdk: docker
app_port: 7860
---
```

## 3) 자동 빌드
HF가 루트의 `Dockerfile`을 감지해 빌드(수 분) → 대시보드가 뜹니다. **멀티스테이지**라 별도 작업 불필요:
- **① Node 스테이지**: `frontend/`(Vue+Vite)를 `npm ci && npm run build` → `dist/` 생성.
- **② Python 스테이지**: 백엔드(`reviewlens/`)를 설치하고 `dist/`를 함께 실어 FastAPI가 SPA를 서빙.
- 첫 로딩 때 임베딩 모델(ko-sroberta) 1회 다운로드.
- 데모 DB(`reviewlens/db/reviewlens.db`)가 저장소에 포함돼 바로 데이터가 보입니다.

## 동작 범위 (Ollama 없는 호스트)
| 기능 | 동작 |
|---|---|
| 대시보드 전 탭(실데이터·AI 카피·리뷰 답글) | ✅ 완전 동작 |
| 챗봇: 집계·추천·비교·특정상품·장단점·목록·인사 | ✅ 즉답(사전계산/템플릿) |
| 챗봇: 자유서술형(실시간 RAG 생성) | ⚠️ LLM 없어 근거 리뷰로 폴백 |

## (선택) Render·Fly 등
`PORT` 환경변수를 읽으므로 Dockerfile 기반 호스트면 동작. 단 **메모리 1GB+ 필요**(torch+임베딩) — 512MB 무료 티어는 부족하니 HF Spaces 권장.

## 풀스택(LLM까지) 데모는 로컬에서
자유서술형 RAG까지 보여주려면 로컬에서 Ollama와 함께 실행하세요(README의 실행/트러블슈팅 참고).
