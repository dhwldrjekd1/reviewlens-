"""app.py의 SPA 캐치올(GET /{full_path:path})이 /api/* 요청을 가로채 200 HTML로
삼키지 않는지 검증. 실제 SPA 라우트와 진짜 GET API는 그대로 동작해야 한다.
"""
from fastapi.testclient import TestClient

import app as app_module

client = TestClient(app_module.app)


def test_get_on_post_only_api_route_is_404_not_html():
    r = client.get("/api/chat")   # 원래 POST 전용
    assert r.status_code == 404


def test_unknown_api_path_is_404_not_html():
    r = client.get("/api/no-such-endpoint")
    assert r.status_code == 404


def test_real_spa_route_still_serves_html():
    r = client.get("/dashboard")
    # frontend/dist가 빌드돼 있으면 200, 아직 안 돼있으면(신규 체크아웃 등) app.py가 의도적으로
    # 503을 반환함 — 둘 다 정상 동작이고, 여기서 실제로 검증하려는 건 "/api/*"가 아닌 경로가
    # api/ 404 분기로 잘못 새지 않고 원래 SPA 서빙 로직을 그대로 타는지이므로 404만 아니면 됨
    assert r.status_code in (200, 503)
    assert "text/html" in r.headers["content-type"]


def test_real_get_api_route_still_works():
    r = client.get("/api/feedback/stats")
    assert r.status_code == 200
