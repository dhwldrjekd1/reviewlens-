# ReviewLens 데모 배포 (Hugging Face Spaces · Docker SDK 권장 / 무료 CPU 16GB).
# Ollama 없이도 동작: 대시보드 전체 + 챗봇 즉답(집계·추천·비교·특정상품·장단점·인사)은
# 사전계산/템플릿이라 LLM 불필요. 자유서술형만 graceful 폴백(근거 리뷰 반환).
# 사전계산된 데모 DB(요약·광고카피·리뷰답글 포함)를 함께 실어 호스트에 Ollama가 필요 없다.
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 HF_HOME=/app/.hf TRANSFORMERS_CACHE=/app/.hf TOKENIZERS_PARALLELISM=false

# torch는 CPU 휠로 (이미지 경량화)
COPY reviewlens/requirements.txt .
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r requirements.txt

COPY reviewlens/ ./

EXPOSE 7860
CMD ["sh", "-c", "python -m uvicorn app:app --host 0.0.0.0 --port ${PORT:-7860}"]
