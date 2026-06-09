# ReviewLens 데모 배포 (Hugging Face Spaces · Docker SDK 권장 / 무료 CPU 16GB).
# 멀티스테이지: ① Node로 Vue(Vite) 프런트 빌드 → ② Python으로 백엔드+정적 서빙.
# Ollama 없이도 동작: 대시보드 전체 + 챗봇 즉답(집계·추천·비교·특정상품·장단점·인사)은
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
WORKDIR /app
ENV PYTHONUNBUFFERED=1 HF_HOME=/app/.hf TRANSFORMERS_CACHE=/app/.hf TOKENIZERS_PARALLELISM=false

# torch는 CPU 휠로 (이미지 경량화)
COPY reviewlens/requirements.txt .
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r requirements.txt

COPY reviewlens/ ./
# Vue 빌드 산출물 → app.py 가 ../frontend/dist 로 참조 (app.py=/app 이므로 /frontend/dist)
COPY --from=web /web/dist /frontend/dist

EXPOSE 7860
CMD ["sh", "-c", "python -m uvicorn app:app --host 0.0.0.0 --port ${PORT:-7860}"]
