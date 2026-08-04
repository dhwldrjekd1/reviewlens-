"""app.py의 SPA 캐치올(GET /{full_path:path})이 /api/* 요청을 가로채 200 HTML로
삼키지 않는지 검증. 실제 SPA 라우트와 진짜 GET API는 그대로 동작해야 한다.
"""
import pytest
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
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_real_get_api_route_still_works():
    r = client.get("/api/feedback/stats")
    assert r.status_code == 200
