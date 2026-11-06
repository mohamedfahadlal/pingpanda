# PingPanda 🐼

<p align="center">
  <img src="img/url-status-checker-logo.png" alt="PingPanda logo" width="180">
</p>

<p align="center">
  <strong>A fast, friendly command-line URL status checker.</strong>
</p>

<p align="center">
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="MIT License"></a>
</p>

PingPanda checks one URL or a list of URLs and groups the results by HTTP status class. It is a small command-line tool for developers, students, and anyone who wants a quick overview of whether a set of websites is reachable, redirecting, or returning an error.

PingPanda started as [Status Checker](https://github.com/BLACK-SCORP10/url-status-checker) by **BLACK-SCORP10** and was later enhanced by **matteocapricci**. The original authors are credited in the program banner and in the [LICENSE](LICENSE) file. The project is maintained for the **FOSSSoC-S1** contribution season.

## Preview

<p align="center">
  <img src="img/demo.png" alt="PingPanda checking a list of URLs in a terminal" width="720">
</p>

## Features

- Check a single URL or a list of URLs from a text file.
- Use asynchronous HTTP requests for list checks.
- Follow redirects and show the final destination.
- Display the HTTP status, response time, and resolved IP address for each URL.
- Organise results into status-class sections: 1xx, 2xx, 3xx, 4xx, 5xx, and invalid.
- Colour-coded terminal output with a progress bar for list runs.
- Save the report to a text file.
- Save completed scan results to an atomic checkpoint after each URL finishes.
- Resume interrupted scans without rechecking completed URLs; checkpoint inputs are validated before reuse.
- Print a summary line at the end of every run.
- Simple command-line interface with built-in help.

## Tech Stack

| Area | Technology |
|---|---|
| Language | Python 3.10+ |
| HTTP client | httpx |
| Terminal output | colorama, tqdm |
| Command line | argparse |
| Testing | pytest, pytest-asyncio |
| Continuous integration | GitHub Actions |

## Project Structure

```text
url-status-checker.py    Entry point for the command-line tool
pingpanda/
├── __init__.py          Package exports
├── constants.py         Banner, colours, and status groups
├── models.py            Data model for a checked URL
├── network.py           URL preparation, address lookup, and checks
├── report.py            Grouping, formatting, and saving results
├── checkpoint.py        Atomic checkpoint storage and validation
└── cli.py               Argument parsing and application flow
tests/                   Test suite (no external network access)
.github/                 CI workflow and issue/PR templates
img/                     Logo and demo image
```

## Prerequisites

- **Python 3.10 or newer**
- **pip**
- **Git** (to clone the repository)
- Network access to the URLs you want to check

## Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/<your-username>/PingPanda.git
   cd PingPanda
   ```

2. Create and activate a virtual environment:

   ```bash
   python -m venv .venv
   ```

   Linux and macOS:

   ```bash
   source .venv/bin/activate
   ```

   Windows PowerShell:

   ```powershell
   .venv\Scripts\Activate.ps1
   ```

3. Install the runtime dependencies:

   ```bash
   pip install -r requirements.txt
   ```

   For development and for running the test suite, install the development
   dependencies instead:

   ```bash
   pip install -r requirements-dev.txt
   ```

## Running the Application

Check a single URL:

```bash
python url-status-checker.py -d https://example.com
```

Check a list of URLs:

```bash
python url-status-checker.py -l urls.txt
```

Retry transient failures with exponential backoff:

```bash
python url-status-checker.py -l urls.txt --retries 3 --retry-delay 1
```

The command allows three retries after the initial request. Retry delays are
approximately 1, 2, and 4 seconds. Connection failures, timeouts, and
transient HTTP responses (`408`, `429`, `502`, `503`, and `504`) are retried;
permanent responses such as `404` are not.

Save the report to a file:

```bash
python url-status-checker.py -l urls.txt -o results.txt
```

Resume an interrupted scan using the default checkpoint:

```powershell
python url-status-checker.py -l urls.txt --resume
```

Choose a custom checkpoint path:

```powershell
python url-status-checker.py -l urls.txt --checkpoint .\\state\\scan.json
python url-status-checker.py -l urls.txt --checkpoint .\\state\\scan.json --resume
```

PingPanda saves progress after each completed URL to `.pingpanda-checkpoint.json` by default. A checkpoint is tied to the exact ordered URL list. If the input changes or is reordered, resume stops with a validation error rather than applying results to the wrong URLs.

Show the built-in help:

```bash
python url-status-checker.py --help
```

A list file contains one URL per line:

```text
https://example.com
https://github.com
https://python.org
```

### Command-line options

| Option | Description |
|---|---|
| `-d`, `--domain` | Check a single URL or domain |
| `-l`, `--list` | Check every URL in a text file, one per line |
| `-o`, `--output` | Save the report to a file |
| `--checkpoint PATH` | Choose where scan progress is saved (default: `.pingpanda-checkpoint.json`) |
| `--resume` | Resume from the selected checkpoint, skipping completed URLs |
| `--retries N` | Retry transient failures up to `N` times after the initial request (default: `0`) |
| `--retry-delay SECONDS` | Initial delay before retrying; each later delay doubles (default: `1`) |
| `--max-concurrent N` | Maximum number of URLs checked concurrently (default: `10`) |
| `-v`, `--version` | Show version information |
| `-h`, `--help` | Show the help text |

Provide one input source, either `-d` or `-l`, for each run.

### Report format

Every checked URL becomes one line of the report:

```text
[Status: 200] [Time: 123.456 ms] [IP: 93.184.216.34:443] https://example.com [Redirect: None]
```

| Field | Meaning |
|---|---|
| `Status` | HTTP status code of the response, or `Invalid` when the URL could not be reached |
| `Time` | Response time in milliseconds |
| `IP` | Resolved address and port of the host |
| `URL` | The URL that was checked |
| `Redirect` | Final URL and its address when the server redirected, `None` otherwise |

Results are grouped under headings such as `2XX`, `4XX`, and `INVALID`. The run
ends with a summary line:

```text
Checked: 3 | 1xx: 0 | 2xx: 2 | 3xx: 0 | 4xx: 1 | 5xx: 0 | Failed: 0
```

The `-o` option writes the report to a file without the colours.

### Periodic checks

On systems that provide the `watch` command, the tool can be run repeatedly:

```bash
watch -n 72000 python url-status-checker.py -l urls.txt
```

## Development

Run the whole test suite:

```bash
python -m pytest
```

Run a single test file or a single test:

```bash
python -m pytest tests/test_cli.py
python -m pytest tests/test_cli.py::test_version_option_prints_a_version
```

The suite does not use the public internet. HTTP responses are simulated, and a
temporary server on `localhost` is used where a real socket is needed.

### Troubleshooting

Having trouble installing or running PingPanda? Check our
[Troubleshooting Guide](docs/troubleshooting.md) for solutions
to common setup and runtime problems.

## Contributing

Contributions of all sizes are welcome: bug reports, documentation
improvements, tests, and new features.

1. **Fork** the repository on GitHub.
2. **Clone your fork** and create a branch:

   ```bash
   git clone https://github.com/<your-username>/PingPanda.git
   cd PingPanda
   git checkout -b fix/short-description
   ```

3. **Make your change.** Keep the pull request focused on a single issue, and
   add or update tests when the behaviour changes.
4. **Commit** with a clear message:

   ```bash
   git add .
   git commit -m "Add a test for the report summary"
   ```

5. **Push** the branch and open a pull request against `main`. Link the issue
   it resolves in the pull request description.

Please read [CONTRIBUTING.md](CONTRIBUTING.md) for the full setup and review
workflow, and follow the [Code of Conduct](CODE_OF_CONDUCT.md). If you are new
to the project, look for issues labelled `good first issue`.

## Development Standards

- Follow the style of the existing code: 4 spaces, small functions, and clear
  names.
- Add a test for every bug fix and for new behaviour.
- Keep pull requests small and limited to one issue.
- Update the README when a change affects users.
- Do not commit local artifacts such as `.venv`, `__pycache__`, or report files.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file
for details.

## Acknowledgements

- **BLACK-SCORP10** for creating the original Status Checker.
- **matteocapricci** for the earlier enhancements.
- The FOSSSoC-S1 organisers and all contributors who help maintain PingPanda.

---

## 🚀 FOSSSoC Season 1 Contribution Guidelines

This repository is an official project for **FOSSSoC Season 1 (November Phase)** hosted by **[TKM FOSS](https://github.com/tkmfoss)**.

- 📋 **Active Issues:** Browse open challenges on the [Issues Tab](https://github.com/tkmfoss/pingpanda/issues) (tagged `soc-s1`).

---

### 1. How to Claim an Issue
1. Browse open issues tagged with `soc-s1`.
2. Comment `/claim` on an unassigned issue.
3. Our automated bot will immediately assign you if you meet the eligibility criteria.
4. ⚠️ **1-Issue Rule:** You can only have **ONE active claimed issue at any time** across all FOSSSoC repositories. You must have your pull request merged or closed before claiming another.
5. ⏳ **Tiered Inactivity Window:** You have **3 days (72 hours)** for Easy issues, and **5 days (120 hours)** for Medium and Hard issues to open a pull request. If no PR is opened within this window, the bot automatically unassigns the issue to keep opportunities open for others.

---

### 2. How to Raise a New Issue & Work on It
Found an unlisted bug, edge case, or have an idea for an awesome new CLI feature or test suite expansion? You are strongly encouraged to propose it!

#### Step A: Check Existing Issues & PRs
Before creating a new issue, search the [Issues Tab](https://github.com/tkmfoss/pingpanda/issues) and [Pull Requests Tab](https://github.com/tkmfoss/pingpanda/pulls) to make sure someone else hasn't already reported, claimed, or fixed it. Duplicate issues will be closed.

#### Step B: Open an Issue with a Template
1. Go to [New Issue](https://github.com/tkmfoss/pingpanda/issues/new/choose).
2. Choose either **Bug Report** or **Feature Request**.
3. Fill out all template sections: steps to reproduce, expected vs observed behavior, relevant files, and your proposed approach.

#### Step C: Mentor Review & Difficulty Assignment
- A project mentor (`@hrudulmmn` / `@ganes4real` / `@ras-al`) will review your proposal to verify that it is constructive, non-trivial, and fits the tool.
- If approved, the mentor will tag your issue with:
  - `soc-s1` label (mandatory for automated leaderboard tracking).
  - The appropriate difficulty tier: `level:easy` (10 pts), `level:medium` (25 pts), or `level:hard` (50 pts).
- ⚠️ **IMPORTANT:** **Do not start coding or submit a PR until a mentor has reviewed and labeled the issue!** PRs linked to unapproved or unlabeled issues cannot be scored by the automated leaderboard.

#### Step D: Claim and Begin Working
- As soon as the mentor adds the labels, comment `/claim` on the issue to assign yourself.
- The standard **1-Issue Rule** applies (you cannot claim if you already have an active assigned issue).
- Your **tiered inactivity clock (3 days for Easy, 5 days for Medium/Hard)** begins once assigned.

---

### 3. How to Submit Your Solution
1. Fork this repository to your personal GitHub account.
2. Clone your fork locally and create a descriptive branch:
   ```bash
   git checkout -b fix/http-default-port
   ```
3. Set up your environment and run the test suite:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\Activate.ps1
   pip install -r requirements-dev.txt
   pytest -v
   ```
4. Commit your changes with clear commit messages and push to your fork.
5. Open a Pull Request targeting `main` of `tkmfoss/pingpanda`.
6. 🔗 **CRITICAL:** Include `Fixes #<issue_number>` in your pull request description (e.g., `Fixes #1`). This automatically links the issue, closes it upon merge, and ensures the automated leaderboard tracks your score!

---

### 4. Scoring & Points

| Difficulty | Tag | Points | Description |
|---|---|---|---|
| 🟢 Easy | `level:easy` | **10 pts** | Localized CLI fixes, documentation guides, small output tweaks |
| 🟡 Medium | `level:medium` | **25 pts** | Asynchronous networking, status aggregation, JSON formatting, retry loops |
| 🔴 Hard | `level:hard` | **50 pts** | Concurrency safety, race condition prevention, timeout architectures |

- ⚡ **Early Bird Bonus:** **+5 bonus points** for PRs opened during Week 1 (November 1 – November 7).
- 🌟 **Quality Bonus:** **+5 bonus points** for clean, well-documented code with thorough PR descriptions (awarded via `quality:excellent` label).
- 🛑 **Repository Cap:** Maximum of **5 scored PRs** per repository.

---

### 5. 🎯 Starter Issues & Bug Hunting

Starter beginner-friendly issues (`level:easy`) are available on the [Issues Tab](https://github.com/tkmfoss/pingpanda/issues) to help you get started with your first pull request!

Beyond the starter issues, contributors are encouraged to test CLI edge cases (handling malformed input, network timeouts, redirects, concurrent requests, output formats, and documentation). If you spot a bug or have an idea for an enhancement, follow the steps above to open a **Bug Report** or **Feature Request**!


