from store import db

# 공유 DB 커넥션 — 라우터들이 함께 사용 (단일 워커 데모 전제).
# 멀티워커(uvicorn --workers N)면 워커별로 분리되므로, 그때는 풀/외부 캐시로 전환 필요.
d = db.get_db()
