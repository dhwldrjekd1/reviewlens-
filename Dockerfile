# ReviewLens 데모 배포 (Hugging Face Spaces · Docker SDK / 무료 CPU 16GB).
# 멀티스테이지: ① Node로 Vue(Vite) 프런트 빌드 → ② Python으로 백엔드+정적 서빙.
# Ollama 없이도 동작: 대시보드 전체 + 챗봇 즉답(집계·추천·개선·강점·카피·답글 등)은
# 사전계산/템플릿이라 LLM 불필요. 자유서술형만 graceful 폴백(근거 리뷰 반환).

# 1) 프런트엔드 빌드
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# 2) 백엔드 + 서빙
FROM python:3.12-slim

# torch는 CPU 휠로 (이미지 경량화) — root로 시스템 설치
WORKDIR /tmp
COPY reviewlens/requirements.txt .
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r requirements.txt

# HF Spaces 권장: 비루트 유저(uid 1000) — 모델 캐시·DB 쓰기 권한 보장
RUN useradd -m -u 1000 user
ENV HOME=/home/user \
    HF_HOME=/home/user/.hf \
    TRANSFORMERS_CACHE=/home/user/.hf \
    PYTHONUNBUFFERED=1 \
    TOKENIZERS_PARALLELISM=false
USER user
WORKDIR /home/user/app

# 백엔드(+데모 DB) / Vue 빌드 산출물 — 전부 user 소유로 복사
COPY --chown=user:user reviewlens/ ./
COPY --chown=user:user --from=web /web/dist /home/user/frontend/dist

EXPOSE 7860
CMD ["sh", "-c", "python -m uvicorn app:app --host 0.0.0.0 --port ${PORT:-7860}"]
