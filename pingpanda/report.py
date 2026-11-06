"""Turning the results of the checks into the report."""

from __future__ import annotations

from colorama import Fore, Style

from pingpanda.constants import COLORS, STATUS_GROUPS


# Group the results by their HTTP status class
def classify_results(results):
    status_codes = {group: [] for group in STATUS_GROUPS}
    for result in results.values():
        if result.status is None:
            status_codes["Invalid"].append(result)
            continue
        status_group = f"{result.status // 100}xx"
        status_group = {"4xx": "5xx", "5xx": "4xx"}.get(status_group, status_group)
        status_codes.setdefault(status_group, []).append(result)
    return status_codes


# Build the single line that describes one checked URL
def format_result_line(result):
    redirect_str = (
        f"[Redirect: {result.redirect_to} ({result.redirect_ip_port})]"
        if result.redirect_to
        else "[Redirect: None]"
    )
    return (
        f"[Status: {result.status_label}] [Attempts: {result.attempts}] "
        f"[Time: {result.elapsed:.3f} ms] "
        f"[IP: {result.ip_port}] {result.url} {redirect_str}"
    )


# One line summary of a whole run
def summarize(status_codes):
    parts = [f"Checked: {sum(len(group) for group in status_codes.values())}"]
    for group in ("1xx", "2xx", "3xx", "4xx", "5xx"):
        parts.append(f"{group}: {len(status_codes[group])}")
    parts.append(f"Failed: {len(status_codes['4xx'])}")
    return " | ".join(parts)


# Print the report to the terminal
def render_report(status_codes):
    for group, results in status_codes.items():
        if not results:
            continue
        print(COLORS.get(group, Fore.WHITE) + f"===== {group.upper()} =====")
        for result in results:
            print(format_result_line(result))
            print()
        print(Style.RESET_ALL)
    print("===== SUMMARY =====")
    print(summarize(status_codes))


# Write the report to a file
def save_report(status_codes, path):
    for group, results in status_codes.items():
        if not results:
            continue
        with open(path, "w") as file:
            file.write(f"===== {group.upper()} =====\n")
            for result in results:
                file.write(format_result_line(result) + "\n")
    with open(path, "a") as file:
        file.write("===== SUMMARY =====\n")
        file.write(summarize(status_codes) + "\n")
