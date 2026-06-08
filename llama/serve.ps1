# llama.cpp 백엔드(옵션) — llama-server로 GGUF를 직접 서빙.
# 기본 백엔드는 Ollama. 이 스크립트로 띄운 뒤 RL_BACKEND=llamacpp 로 chatbot을 돌리면
# Ollama 대신 llama-server(localhost:8080)로 LLM 호출이 라우팅된다.
#
# ⚠ 메모: Ollama 내부 엔진도 llama.cpp라 속도 이득은 없다. 또한 추론(thinking) 모델
#   (gemma4 등)은 이 빌드에서 사고가 응답에 새는 이슈가 있어, 표준 비추론 GGUF 권장.
#
# 사용:  powershell -File llama\serve.ps1 -Gguf "<GGUF 경로>"
#   GGUF는 HuggingFace(ggml-org 등)의 표준 변환본을 권장.
#   (참고: Ollama 블롭은 메타데이터가 달라 upstream llama.cpp에서 로드 안 될 수 있음)

param(
  [string]$Gguf = "",
  [int]$Port = 8080,
  [int]$Threads = 6,
  [int]$Ctx = 4096
)

if (-not $Gguf -or -not (Test-Path $Gguf)) {
  Write-Host "GGUF 경로를 -Gguf 로 지정하세요. 예: -Gguf C:\models\gemma3-4b-Q4_K_M.gguf"
  exit 1
}

$bin = Join-Path $PSScriptRoot "bin\llama-server.exe"
# --jinja: 모델 chat 템플릿 적용 / --reasoning-budget 0: 추론모델 사고 억제 시도
& $bin -m $Gguf --port $Port -c $Ctx -t $Threads --no-webui --jinja --reasoning-budget 0
