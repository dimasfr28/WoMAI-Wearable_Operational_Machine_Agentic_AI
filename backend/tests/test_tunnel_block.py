"""Unit tests for _require_direct_localhost_request — POST /sensor/readings
and /sensor/readings/batch reject requests proxied through Cloudflare
Tunnel, identified by Cloudflare's own injected headers (a tunnel-forwarded
request and a genuine localhost request are otherwise indistinguishable by
peer IP alone inside Docker — both arrive via the bridge gateway)."""
from __future__ import annotations

import unittest

from fastapi import HTTPException
from starlette.datastructures import Headers
from starlette.requests import Request

from app.api.routes_sensor import _require_direct_localhost_request


def _request(headers: dict[str, str]) -> Request:
    scope = {
        "type": "http",
        "headers": Headers(headers).raw,
    }
    return Request(scope)


class RequireDirectLocalhostRequestTestCase(unittest.TestCase):
    def test_plain_request_with_no_tunnel_headers_passes(self):
        _require_direct_localhost_request(_request({}))  # must not raise

    def test_cf_connecting_ip_header_is_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            _require_direct_localhost_request(_request({"cf-connecting-ip": "1.2.3.4"}))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_cf_ray_header_is_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            _require_direct_localhost_request(_request({"cf-ray": "abc123-SIN"}))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_cf_visitor_header_is_rejected(self):
        with self.assertRaises(HTTPException):
            _require_direct_localhost_request(_request({"cf-visitor": '{"scheme":"https"}'}))


if __name__ == "__main__":
    unittest.main()
