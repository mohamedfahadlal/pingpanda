"""Tests for checking a single URL."""

import asyncio
import re
import socket
import time

import httpx
import pytest

KNOWN_DEFECT = "known defect - see the FOSSSoC-S1 issue tracker"

@pytest.mark.parametrize(
    ("url", "expected_port"),
    [
        ("http://example.com/", 80),
        ("https://example.com/", 443),
        ("http://example.com:8000/", 8000),
    ],
)
async def test_resolve_ip_and_port_uses_correct_port(
    checker, fake_dns, url, expected_port
):
    result = await checker.network.resolve_ip_and_port(url)

    assert result.endswith(f":{expected_port}")



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


async def test_transient_http_failure_is_retried_with_exponential_backoff(
    checker, fake_dns, monkeypatch
):
    responses = iter([httpx.Response(503), httpx.Response(503), httpx.Response(200)])
    delays = []

    async def fake_sleep(delay):
        delays.append(delay)

    monkeypatch.setattr(checker.network.asyncio, "sleep", fake_sleep)

    def handler(request):
        return next(responses)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
        result = await checker.check_url_status(
            session,
            0,
            "https://example.com",
            max_retries=2,
            retry_delay=0.5,
        )

    assert result.status == 200
    assert result.attempts == 3
    assert delays == [0.5, 1.0]


async def test_permanent_http_failure_is_not_retried(
    checker, fake_dns, monkeypatch
):
    requests = 0

    async def unexpected_sleep(delay):
        raise AssertionError("Permanent failures must not be retried.")

    monkeypatch.setattr(checker.network.asyncio, "sleep", unexpected_sleep)

    def handler(request):
        nonlocal requests
        requests += 1
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
        result = await checker.check_url_status(
            session, 0, "https://example.com", max_retries=3
        )

    assert result.status == 404
    assert result.attempts == 1
    assert requests == 1


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


async def test_redirect_ip_belongs_to_the_redirect_target(checker, monkeypatch):
    hosts = {"example.com": "10.0.0.1", "target.test": "10.0.0.2"}
    def fake_getaddrinfo(
        hostname, port, family=0, type=0, proto=0, flags=0
    ):
        ip_address = hosts.get(hostname, "10.0.0.3")

        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                (ip_address, port),
            )
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    def handler(request):
        if request.url.host == "example.com":
            return httpx.Response(302, headers={"Location": "https://target.test/final"})
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
        result = await checker.check_url_status(session, 0, "https://example.com")

    assert result.redirect_ip_port == "10.0.0.2:443"



async def test_redirect_loop_is_reported_as_invalid(checker, local_server, fake_dns):
    async with httpx.AsyncClient() as session:
        result = await checker.check_url_status(session, 0, f"{local_server}/loop")

    assert result.status is None


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

async def test_silent_server_times_out(checker, local_server, fake_dns, monkeypatch):
    monkeypatch.setattr(checker.network, "DEFAULT_TIMEOUT_SECONDS", 0.3)

    async with httpx.AsyncClient() as session:
        started = time.perf_counter()

        result = await asyncio.wait_for(
            checker.check_url_status(session, 0,f"{local_server}/silent"),timeout=2.0,
        )

        duration = time.perf_counter() - started

    assert duration < 1.0
    assert result.status is None

async def test_trickling_server_times_out(checker, local_server, fake_dns, monkeypatch):
    monkeypatch.setattr(checker.network, "DEFAULT_TIMEOUT_SECONDS", 0.35)

    async with httpx.AsyncClient() as session:
        started = time.perf_counter()

        result = await asyncio.wait_for(
            checker.check_url_status(session, 0, f"{local_server}/trickle"),timeout=2.5,
        )

        duration = time.perf_counter() - started

    assert duration < 0.8, "the overall timeout was not enforced"
    assert result.status is None

async def test_redirect_chain_respects_overall_timeout(
        checker, local_server, fake_dns, monkeypatch
):
    monkeypatch.setattr(checker.network, "DEFAULT_TIMEOUT_SECONDS", 0.35)
    async with httpx.AsyncClient() as session:
        started = time.perf_counter()

        result = await asyncio.wait_for(
            checker.check_url_status(session, 0, f"{local_server}/redirect-chain/0"),timeout=2.5,
        )

        duration = time.perf_counter() - started

    assert duration < 0.8, "the redirect chain exceeded the overall timeout"
    assert result.status is None

async def test_resolve_ip_and_port_supports_ipv6(checker, monkeypatch):
    def fake_getaddrinfo(
        hostname, port, family=0, type=0, proto=0, flags=0
    ):
        return [
            (
                socket.AF_INET6,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("2001:db8::1", port, 0, 0),
            )
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    result = await checker.network.resolve_ip_and_port(
        "https://example.com"
    )

    assert result == "[2001:db8::1]:443"

async def test_dns_lookup_times_out(checker, monkeypatch):
    monkeypatch.setattr(
        checker.network, "DEFAULT_TIMEOUT_SECONDS", 0.01
    )

    loop = asyncio.get_running_loop()

    async def slow_getaddrinfo(*args, **kwargs):
        await asyncio.sleep(0.1)
        return []

    monkeypatch.setattr(loop, "getaddrinfo", slow_getaddrinfo)

    result = await checker.network.resolve_ip_and_port(
        "https://example.com"
    )

    assert result == "IP:Port Not Found"