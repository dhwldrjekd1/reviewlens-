import os
import sys

# 어디서 pytest를 돌리든 reviewlens/ 가 import 루트가 되도록 (from store import db 등)
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# test_spa_fallback.py가 app을 import하면 app.py의 prewarm 백그라운드 스레드가 실제
# chatbot 상태(_EXACT/_CACHE, 실제 임베딩 모델)를 건드리는데, 다른 테스트(test_chat_cache.py 등)가
# monkeypatch로 같은 모듈 상태를 갈아끼우는 시점과 겹치면 결과가 뒤섞일 수 있음(교차검증에서 발견 —
# 타이밍 의존적이라 지금까지는 우연히 안 터졌을 뿐). conftest.py는 어떤 테스트 파일보다 먼저
# 로드되므로, 여기서 미리 꺼두면 app import 시점에 항상 반영된다.
os.environ["RL_SKIP_PREWARM"] = "1"
