"""Tests for checking a single URL."""

import asyncio
import re
import socket
import time

import httpx
import pytest

KNOWN_DEFECT = "known defect - see the FOSSSoC-S1 issue tracker"


async def test_successful_request_reports_the_status(checker, fake_dns):
    def handler(request):
        return httpx.Response(200, text="hello")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
        result = await checker.check_url_status(session, 0, "https://example.com")

    assert result.status == 200
    assert result.url == "https://example.com"
    assert result.ip_port.endswith(":443")


async def test_connection_error_is_reported_as_invalid(checker):
    def handler(request):
        raise httpx.ConnectError("connection refused")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
        result = await checker.check_url_status(session, 0, "https://example.com")

    assert result.status is None
    assert result.status_label == "Invalid"


async def test_url_without_scheme_is_checked_over_https(checker, fake_dns):
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
        await checker.check_url_status(session, 0, "example.com")

    assert seen["url"].startswith("https://")


@pytest.mark.xfail(strict=True, reason=KNOWN_DEFECT)
async def test_response_time_is_reported_in_milliseconds(checker, fake_dns):
    async def handler(request):
        await asyncio.sleep(0.25)
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
        result = await checker.check_url_status(session, 0, "https://example.com")

    reported = re.search(r"\[Time: ([0-9.]+) ms\]", checker.format_result_line(result))
    assert reported is not None
    assert float(reported.group(1)) >= 200.0


async def test_redirect_target_is_reported(checker, fake_dns):
    def handler(request):
        if request.url.host == "example.com":
            return httpx.Response(302, headers={"Location": "https://target.test/final"})
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
        result = await checker.check_url_status(session, 0, "https://example.com")

    assert result.redirect_to == "https://target.test/final"


@pytest.mark.xfail(strict=True, reason=KNOWN_DEFECT)
async def test_redirect_ip_belongs_to_the_redirect_target(checker, monkeypatch):
    hosts = {"example.com": "10.0.0.1", "target.test": "10.0.0.2"}
    monkeypatch.setattr(socket, "gethostbyname", lambda host: hosts.get(host, "10.0.0.3"))

    def handler(request):
        if request.url.host == "example.com":
            return httpx.Response(302, headers={"Location": "https://target.test/final"})
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
        result = await checker.check_url_status(session, 0, "https://example.com")

    assert result.redirect_ip_port == "10.0.0.2:443"


@pytest.mark.xfail(strict=True, reason=KNOWN_DEFECT)
async def test_redirect_loop_is_reported_as_invalid(checker, local_server, fake_dns):
    async with httpx.AsyncClient() as session:
        result = await checker.check_url_status(session, 0, f"{local_server}/loop")

    assert result.status is None


@pytest.mark.xfail(strict=True, reason=KNOWN_DEFECT)
async def test_slow_server_times_out(checker, local_server, fake_dns, monkeypatch):
    monkeypatch.setattr(checker.network, "DEFAULT_TIMEOUT_SECONDS", 0.3)

    async with httpx.AsyncClient() as session:
        started = time.perf_counter()
        result = await asyncio.wait_for(
            checker.check_url_status(session, 0, f"{local_server}/slow"), timeout=2.5
        )
        duration = time.perf_counter() - started

    assert duration < 1.0, "the request was not cut short by the timeout"
    assert result.status is None
