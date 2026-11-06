"""Tests for the command line interface."""

import httpx
import pytest

KNOWN_DEFECT = "known defect - see the FOSSSoC-S1 issue tracker"


def write_urls(tmp_path, *urls):
    list_file = tmp_path / "urls.txt"
    list_file.write_text("\n".join(urls) + "\n", encoding="utf-8")
    return list_file


async def test_version_option_prints_a_version(checker, capsys):
    await checker.main(["-v"])
    assert "version" in capsys.readouterr().out


async def test_without_input_the_tool_explains_itself(checker, capsys):
    await checker.main([])
    assert "No input provided" in capsys.readouterr().out


async def test_single_url_is_reported(checker, mock_transport, fake_dns, capsys):
    def handler(request):
        return httpx.Response(200)

    mock_transport(handler)
    await checker.main(["-d", "https://example.com"])

    out = capsys.readouterr().out
    assert "===== 2XX =====" in out
    assert "https://example.com" in out
    assert "200" in out


async def test_report_file_is_written(checker, mock_transport, fake_dns, tmp_path):
    def handler(request):
        return httpx.Response(200)

    mock_transport(handler)
    report = tmp_path / "report.txt"
    await checker.main(["-d", "https://example.com", "-o", str(report)])

    content = report.read_text(encoding="utf-8")
    assert "https://example.com" in content
    assert "200" in content


@pytest.mark.xfail(strict=True, reason=KNOWN_DEFECT)
async def test_report_file_contains_every_status_group(
    checker, mock_transport, fake_dns, tmp_path
):
    def handler(request):
        if request.url.path == "/missing":
            return httpx.Response(404)
        return httpx.Response(200)

    mock_transport(handler)
    list_file = write_urls(tmp_path, "https://good.test/", "https://bad.test/missing")
    report = tmp_path / "report.txt"
    await checker.main(["-l", str(list_file), "-o", str(report)])

    content = report.read_text(encoding="utf-8")
    assert "===== 2XX =====" in content
    assert "===== 4XX =====" in content



async def test_one_broken_url_does_not_stop_the_batch(
    checker, mock_transport, fake_dns, tmp_path, capsys
):
    def handler(request):
        if request.url.path == "/loop":
            return httpx.Response(302, headers={"Location": "/loop"})
        return httpx.Response(200)

    mock_transport(handler)
    list_file = write_urls(tmp_path, "https://good.test/", "https://loop.test/loop")
    await checker.main(["-l", str(list_file)])

    out = capsys.readouterr().out
    assert "https://good.test/" in out
    assert "https://loop.test/loop" in out

def test_max_concurrent_argument_is_parsed(checker):
    args = checker.parse_arguments(["--max-concurrent", "4"])

    assert args.max_concurrent == 4


def test_max_concurrent_has_default(checker):
    args = checker.parse_arguments([])

    assert args.max_concurrent == 10


def test_retry_arguments_are_parsed(checker):
    args = checker.parse_arguments(["--retries", "3", "--retry-delay", "1.5"])

    assert args.retries == 3
    assert args.retry_delay == 1.5


def test_retries_default_to_disabled(checker):
    args = checker.parse_arguments([])

    assert args.retries == 0
    assert args.retry_delay == 1.0


@pytest.mark.parametrize("value", ["0", "-1", "abc"])
def test_invalid_max_concurrent_is_rejected(checker, value):
    with pytest.raises(SystemExit):
        checker.parse_arguments(["--max-concurrent", value])


@pytest.mark.parametrize("option", ["--retries", "--retry-delay"])
@pytest.mark.parametrize("value", ["-1", "abc"])
def test_invalid_retry_options_are_rejected(checker, option, value):
    with pytest.raises(SystemExit):
        checker.parse_arguments([option, value])