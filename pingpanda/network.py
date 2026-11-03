"""Resolving a host and checking a URL."""

from __future__ import annotations

import asyncio
import socket
import time
from urllib.parse import urlparse

import httpx
from tqdm import tqdm

from pingpanda.models import UrlResult

# How long a single request may take, in seconds
DEFAULT_TIMEOUT_SECONDS = 10.0


# Function to resolve hostname to IP:Port
def resolve_ip_and_port(url):
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        scheme = parsed.scheme
        port = parsed.port or (443 if scheme == "https" else 8080)
        ip_address = socket.gethostbyname(hostname)
        return f"{ip_address}:{port}"
    except Exception:
        return "IP:Port Not Found"


# Function to make sure the URL has a scheme httpx understands
def normalize_url(url):
    url = url.strip()
    if "://" not in url:
        url = "https://" + url
    return url


# Function to check URL status and redirection
async def check_url_status(session, url_id, url):
    url = normalize_url(url)
    started = time.perf_counter()
    try:
        response = await asyncio.wait_for(
        session.get(
            url,
            follow_redirects=True,
            timeout=httpx.Timeout(DEFAULT_TIMEOUT_SECONDS, read=None),
            ),
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
    except httpx.ConnectError:
        elapsed = time.perf_counter() - started
        return UrlResult(url_id, url, None, elapsed, None, "IP:Port Not Found", None)
    except asyncio.TimeoutError:
        elapsed = time.perf_counter() - started
        return UrlResult(url_id, url, None, elapsed, None, "IP:Port Not Found", None)

    final_url = str(response.url)

    original_ip_port = resolve_ip_and_port(url)
    redirect_ip_port = resolve_ip_and_port(final_url) if final_url != url else None
    redirect_to = final_url if final_url != url else None

    elapsed = time.perf_counter() - started
    return UrlResult(
        url_id,
        url,
        response.status_code,
        elapsed,
        redirect_to,
        original_ip_port,
        redirect_ip_port,
    )


# Check every URL of the collection and return the results by url id
async def check_all(urls):
    results = {}
    async with httpx.AsyncClient() as session:
        tasks = [
            check_url_status(session, url_id, url) for url_id, url in enumerate(urls)
        ]
        if len(urls) > 1:
            with tqdm(total=len(urls), desc="Checking URLs") as pbar:
                for coro in asyncio.as_completed(tasks):
                    result = await coro
                    results[result.url_id] = result
                    pbar.update(1)
        else:
            for coro in asyncio.as_completed(tasks):
                result = await coro
                results[result.url_id] = result
    return results
