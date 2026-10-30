"""Resumable single-worker acquisition of official BSE daily price CSVs.

The browser is used only for the official Stock Prices form and session.  The
CSV request is captured and fetched through the same Playwright context so a
malformed Content-Disposition header cannot replace the working browser tab.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Iterable
from urllib.parse import parse_qs, urlparse
from zipfile import ZipFile


STOCK_PAGE = "https://www.bseindia.com/markets/equity/EQReports/StockPrcHistori.aspx?flag=sp"
WINDOWS = (
    ("05/09/2024", "04/09/2025"),
    ("05/09/2023", "04/09/2024"),
    ("05/09/2022", "04/09/2023"),
    ("05/09/2021", "04/09/2022"),
)
SMOKE_CODES = ("500051", "500371", "500500", "501270", "505690")
MAX_ATTEMPTS = 3
PROGRESS_VERSION = "bse_official_history_playwright_v1"
CODE_PATTERN = re.compile(r"^(?:BSE_)?(?P<code>\d{6})(?:[_-].*)?\.csv$", re.IGNORECASE)
DATE_PATTERNS = (
    (re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b"), "%d/%m/%Y"),
    (re.compile(r"\b(\d{2})-(\d{2})-(\d{4})\b"), "%d-%m-%Y"),
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), "%Y-%m-%d"),
    (re.compile(r"\b(\d{2})-([A-Za-z]{3})-(\d{4})\b"), "%d-%b-%Y"),
)
TERMINAL_STATUSES = {"DOWNLOADED", "NO_RECORD"}
CSV_COLUMNS = (
    "key", "code", "from_date", "to_date", "year_folder", "status",
    "attempts", "rows", "output_file", "csv_url", "error", "updated_at",
)

BSE_PRICE_REQUIRED_COLUMNS = (
    "Date",
    "Open Price",
    "High Price",
    "Low Price",
    "Close Price",
    "WAP",
    "No.of Shares",
    "No. of Trades",
    "Total Turnover (Rs.)",
)
BSE_PRICE_NUMERIC_COLUMNS = (
    "Open Price",
    "High Price",
    "Low Price",
    "Close Price",
    "WAP",
    "No.of Shares",
    "No. of Trades",
    "Total Turnover (Rs.)",
)


@dataclass
class Task:
    key: str
    code: str
    from_date: str
    to_date: str
    year_folder: str
    status: str = "PENDING"
    attempts: int = 0
    rows: int | None = None
    output_file: str = ""
    csv_url: str = ""
    error: str = ""
    updated_at: str = ""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_downloads_root() -> Path:
    return Path.home() / "Downloads"


def discover_phase_one_source(downloads_root: Path) -> Path:
    candidates = (
        downloads_root / "BSE_2025_2026",
        downloads_root / "BSE_2025_2026.zip",
    )
    found = [path for path in candidates if path.is_dir() or path.is_file()]
    if not found:
        raise FileNotFoundError("Could not find Downloads\\BSE_2025_2026 or BSE_2025_2026.zip")
    return found[0]


def _code_from_name(name: str) -> str | None:
    match = CODE_PATTERN.fullmatch(Path(name).name)
    return match.group("code") if match else None


def extract_codes(source: Path) -> list[str]:
    if source.is_dir():
        names = [path.name for path in source.rglob("*.csv") if path.is_file()]
    elif source.is_file() and source.suffix.lower() == ".zip":
        with ZipFile(source) as archive:
            names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
    else:
        raise ValueError("phase-one source must be a directory or ZIP")
    codes = sorted({code for name in names if (code := _code_from_name(name))})
    if not codes:
        raise ValueError("phase-one source contains no exact six-digit BSE CSV filenames")
    return codes


def build_tasks(codes: Iterable[str], windows: Iterable[tuple[str, str]]) -> list[Task]:
    tasks: list[Task] = []
    for code in codes:
        if not re.fullmatch(r"\d{6}", code):
            raise ValueError(f"invalid BSE code: {code!r}")
        for from_date, to_date in windows:
            folder = f"{from_date[-4:]}-{to_date[-4:]}"
            tasks.append(Task(
                key=f"{code}|{from_date}|{to_date}", code=code,
                from_date=from_date, to_date=to_date, year_folder=folder,
            ))
    return tasks


def _atomic_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(path.name + ".pending")
    with pending.open("wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(pending, path)


def _canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            + "\n").encode("utf-8")


class ProgressStore:
    def __init__(self, output_root: Path, source: Path, codes: list[str], tasks: list[Task]):
        self.output_root = output_root
        self.json_path = output_root / "bse_history_progress.json"
        self.csv_path = output_root / "bse_history_progress.csv"
        self.log_path = output_root / "bse_history_run.log"
        self.source = source.resolve()
        self.codes = codes
        self.tasks = tasks

    def load_or_initialize(self) -> None:
        if not self.json_path.is_file():
            self.persist()
            return
        raw = json.loads(self.json_path.read_text(encoding="utf-8"))
        if raw.get("version") != PROGRESS_VERSION:
            raise ValueError("existing BSE progress uses an unsupported version")
        saved = {row["key"]: row for row in raw.get("tasks", [])}
        for index, task in enumerate(self.tasks):
            row = saved.get(task.key)
            if row:
                self.tasks[index] = Task(**{name: row.get(name, getattr(task, name)) for name in Task.__dataclass_fields__})
        known = {task.key for task in self.tasks}
        if any(key not in known for key in saved):
            raise ValueError("existing progress contains tasks outside the current exact code/window queue")
        for task in self.tasks:
            if task.status == "RUNNING":
                task.status = "PENDING" if task.attempts < MAX_ATTEMPTS else "FAILED"
                task.error = "Previous process ended while this task was running."
        self.persist()

    def persist(self) -> None:
        payload = {
            "version": PROGRESS_VERSION,
            "source": str(self.source),
            "source_code_count": len(self.codes),
            "source_codes_sha256": hashlib.sha256(("\n".join(self.codes) + "\n").encode()).hexdigest(),
            "updated_at": utc_now(),
            "tasks": [asdict(task) for task in self.tasks],
        }
        _atomic_bytes(self.json_path, _canonical_json(payload))
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for task in self.tasks:
            writer.writerow({name: getattr(task, name) for name in CSV_COLUMNS})
        _atomic_bytes(self.csv_path, stream.getvalue().encode("utf-8"))

    def log(self, task: Task, message: str) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(f"{utc_now()}\t{task.key}\t{task.status}\t{message}\n")
            handle.flush()


def output_path(root: Path, task: Task) -> Path:
    from_value = task.from_date.replace("/", "-")
    to_value = task.to_date.replace("/", "-")
    return root / task.year_folder / f"BSE_{task.code}_{from_value}_to_{to_value}.csv"


def _parse_dates(text: str) -> list[datetime]:
    values: list[datetime] = []
    for pattern, format_value in DATE_PATTERNS:
        for match in pattern.finditer(text):
            try:
                values.append(datetime.strptime(match.group(0), format_value))
            except ValueError:
                pass
    return values


def _parse_bse_csv_date(value: str) -> datetime:
    value = value.strip()
    formats = (
        "%d-%B-%Y",
        "%d-%b-%Y",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y-%m-%d",
    )
    for format_value in formats:
        try:
            return datetime.strptime(value, format_value)
        except ValueError:
            continue
    raise ValueError(f"unrecognized BSE CSV date: {value!r}")


def _validate_csv_request_url(url: str, task: Task) -> None:
    """Validate BSE origin and, when exposed, exact scrip-code provenance.

    Official BSE Stock Prices CSVs do not include a dedicated scrip-code column.
    They contain many legitimate six-digit numeric values in quantity/turnover
    fields, so scanning arbitrary CSV cells for six-digit numbers is invalid.
    """
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host not in {"bseindia.com", "www.bseindia.com", "api.bseindia.com"} and not host.endswith(".bseindia.com"):
        raise ValueError(f"CSV request is not an official BSE URL: {host or url!r}")

    query = parse_qs(parsed.query, keep_blank_values=True)
    code_values: list[str] = []
    for key, values in query.items():
        normalized_key = re.sub(r"[^a-z0-9]", "", key.lower())
        if any(token in normalized_key for token in ("scrip", "securitycode", "scripcode")):
            code_values.extend(str(value).strip() for value in values)

    if code_values and task.code not in code_values:
        raise ValueError(
            f"BSE CSV request identifies a different scrip code: {code_values[:5]}"
        )


def validate_csv_bytes(content: bytes, task: Task) -> tuple[bytes, int]:
    if len(content) < 20:
        raise ValueError("CSV response is empty or implausibly small")

    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("CSV response is not decodable text")

    prefix = text.lstrip()[:500].lower()
    if prefix.startswith("<") or "<html" in prefix or "access denied" in prefix:
        raise ValueError("BSE returned HTML/error content instead of CSV")

    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error as exc:
        raise ValueError("BSE response is not recognizable delimited data") from exc

    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        raise ValueError("BSE response lacks a CSV header")

    fieldnames = [str(name or "").strip().lstrip("\ufeff") for name in reader.fieldnames]
    missing = [column for column in BSE_PRICE_REQUIRED_COLUMNS if column not in fieldnames]
    if missing:
        raise ValueError(
            "BSE response is not the expected Stock Prices CSV; "
            f"missing columns: {missing}"
        )

    rows = [
        {str(key or "").strip().lstrip("\ufeff"): str(value or "").strip()
         for key, value in row.items()}
        for row in reader
        if any(str(value or "").strip() for value in row.values())
    ]
    if not rows:
        raise ValueError("BSE Stock Prices CSV contains no data rows")

    lower = datetime.strptime(task.from_date, "%d/%m/%Y")
    upper = datetime.strptime(task.to_date, "%d/%m/%Y")
    seen_dates: set[datetime] = set()

    for row_number, row in enumerate(rows, start=2):
        date_value = _parse_bse_csv_date(row.get("Date", ""))
        if date_value < lower or date_value > upper:
            raise ValueError(
                f"BSE CSV row {row_number} date {row.get('Date')!r} is outside "
                f"requested window {task.from_date}..{task.to_date}"
            )
        if date_value in seen_dates:
            raise ValueError(f"BSE CSV contains duplicate trading date: {row.get('Date')}")
        seen_dates.add(date_value)

        for column in BSE_PRICE_NUMERIC_COLUMNS:
            raw = row.get(column, "").replace(",", "")
            if raw == "":
                raise ValueError(f"BSE CSV row {row_number} has blank {column!r}")
            try:
                float(raw)
            except ValueError as exc:
                raise ValueError(
                    f"BSE CSV row {row_number} has non-numeric {column!r}: {row.get(column)!r}"
                ) from exc

        low = float(row["Low Price"].replace(",", ""))
        high = float(row["High Price"].replace(",", ""))
        if high < low:
            raise ValueError(f"BSE CSV row {row_number} has High Price below Low Price")

    normalized = text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    return normalized, len(rows)


class BSEBrowser:
    def __init__(self, *, output_root: Path, headless: bool, timeout_ms: int):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright is missing. Run the documented .venv-bse setup command first."
            ) from exc
        self._manager = sync_playwright().start()
        self.context = self._manager.chromium.launch_persistent_context(
            user_data_dir=output_root / ".playwright-profile",
            channel="msedge", headless=headless, accept_downloads=False,
            locale="en-IN", viewport={"width": 1440, "height": 1000},
        )
        self.context.set_default_timeout(timeout_ms)
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()

    def close(self) -> None:
        self.context.close()
        self._manager.stop()

    def recreate_page(self) -> None:
        old_page = self.page
        self.page = self.context.new_page()
        try:
            old_page.close()
        except Exception:
            pass

    def ensure_page(self) -> None:
        if "stockprchistori" not in self.page.url.lower():
            response = self.page.goto(STOCK_PAGE, wait_until="domcontentloaded", timeout=60_000)
            self.page.wait_for_timeout(4_000)
            if response is not None and response.status >= 400:
                raise RuntimeError(f"BSE Stock Prices page returned HTTP {response.status}")
        if not self.page.locator("#ddlAnnType").count():
            raise RuntimeError("BSE Stock Prices form did not load")

    @staticmethod
    def _exact_code(text: str, code: str) -> bool:
        return re.search(rf"(?<!\d){re.escape(code)}(?!\d)", text) is not None

    def _select_security(self, task: Task) -> None:
        search = self.page.locator('input[aria-label="smart search"]')
        search.wait_for(state="visible")
        search.fill(task.code)
        self.page.wait_for_timeout(1_200)
        candidates = self.page.locator("li:visible, [role=option]:visible")
        selected = None
        for index in range(candidates.count()):
            candidate = candidates.nth(index)
            text = candidate.inner_text().strip()
            if self._exact_code(text, task.code):
                selected = candidate
                break
        if selected is None:
            raise RuntimeError(f"BSE autocomplete returned no exact result for code {task.code}")
        selected.click()
        self.page.wait_for_timeout(700)
        resolved = search.input_value().strip()
        if not resolved or resolved == task.code:
            raise RuntimeError(f"BSE autocomplete did not resolve exact code {task.code}")

    def _set_form(self, task: Task) -> None:
        self.page.locator("#ddlAnnType").select_option("C")
        self._select_security(task)
        self.page.locator("#Period").select_option("D")
        dates = self.page.locator('input[placeholder="DD/MM/YYYY"]')
        if dates.count() != 2:
            # BSE's current form (Oct 2026) renders the same two controls as
            # name="datepicker" with a whitespace placeholder. Keep the old
            # selector first so historical/browser fixtures remain valid.
            dates = self.page.locator('input[name="datepicker"]')
        if dates.count() != 2:
            raise RuntimeError("BSE Daily form did not expose exactly two date inputs")
        dates.nth(0).fill(task.from_date)
        dates.nth(1).fill(task.to_date)
        dates.nth(1).press("Tab")
        if dates.nth(0).input_value() != task.from_date or dates.nth(1).input_value() != task.to_date:
            raise RuntimeError("BSE date controls did not retain the requested window")

    def _result_state(self, task: Task) -> str:
        deadline = time.monotonic() + 65
        while time.monotonic() < deadline:
            body = self.page.locator("body").inner_text()
            if re.search(r"No\s+Record\s+Found", body, re.IGNORECASE):
                return "NO_RECORD"
            if self._exact_code(body, task.code) and re.search(r"Kindly\s+download\s+the\s+csv", body, re.IGNORECASE):
                return "RECORDS"
            self.page.wait_for_timeout(400)
        raise RuntimeError("Timed out waiting for BSE result or No Record Found")

    def _csv_control(self):
        note = self.page.get_by_text(
            re.compile(r"Kindly\s+download\s+the\s+csv\s+file\s+to\s+view\s+all\s+records", re.IGNORECASE)
        ).first
        note.scroll_into_view_if_needed()
        container = note.locator("xpath=ancestor::*[self::div or self::td][1]")
        controls = container.locator("a,button,img")
        if not controls.count():
            controls = note.locator("xpath=following::*[self::a or self::button or self::img][1]")
        if not controls.count():
            raise RuntimeError("BSE result lacks the footer CSV control")
        return controls.first

    def _fetch_csv(self, url: str, headers: dict[str, str]) -> bytes:
        allowed = {
            key: str(value).strip()
            for key, value in headers.items()
            if key.lower() in {"accept", "accept-language", "referer", "user-agent"}
            and "\r" not in str(value)
            and "\n" not in str(value)
        }
        allowed["Referer"] = STOCK_PAGE

        try:
            response = self.context.request.get(
                url,
                headers=allowed,
                timeout=60_000,
                fail_on_status_code=False,
            )
            if not response.ok:
                raise RuntimeError(f"BSE CSV API returned HTTP {response.status}")
            return response.body()
        except Exception as exc:
            message = str(exc).lower()
            malformed_headers = (
                "parse error" in message
                or "content-disposition" in message
                or "unexpected whitespace after header value" in message
            )
            if not malformed_headers:
                raise

            # BSE occasionally sends malformed response headers. Playwright/Node
            # rejects those before exposing the body, but Windows curl accepts
            # the same official response. Reuse the exact browser-session cookies.
            curl = shutil.which("curl.exe") or shutil.which("curl")
            if not curl:
                raise RuntimeError(
                    "BSE returned malformed HTTP headers and curl is unavailable"
                ) from exc

            cookies = self.context.cookies()
            cookie_header = "; ".join(
                f"{item['name']}={item['value']}"
                for item in cookies
                if item.get("name")
            )

            with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as handle:
                temp_path = Path(handle.name)

            command = [
                curl,
                "--silent",
                "--show-error",
                "--location",
                "--fail-with-body",
                "--compressed",
                "--output",
                str(temp_path),
                "--header",
                f"Referer: {STOCK_PAGE}",
            ]
            for key, value in allowed.items():
                if key.lower() == "referer":
                    continue
                command.extend(["--header", f"{key}: {value}"])
            if cookie_header:
                command.extend(["--cookie", cookie_header])
            command.append(url)

            try:
                result = subprocess.run(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=90,
                    check=False,
                )
                content = temp_path.read_bytes() if temp_path.is_file() else b""
            finally:
                try:
                    temp_path.unlink()
                except OSError:
                    pass

            if result.returncode != 0:
                detail = result.stderr.decode("utf-8", errors="replace").strip()
                raise RuntimeError(
                    f"BSE CSV curl fallback failed ({result.returncode}): {detail}"
                ) from exc
            if not content:
                raise RuntimeError("BSE CSV curl fallback returned an empty body") from exc
            return content

    def run_task(self, task: Task) -> tuple[str, bytes | None, str]:
        self.ensure_page()
        reset = self.page.locator('input[type="submit"][value="Reset"]')
        if reset.count():
            reset.click()
            self.page.wait_for_timeout(600)
        self._set_form(task)
        captured: list[tuple[str, dict[str, str]]] = []

        def remember(request) -> None:
            url = request.url
            lowered = url.lower()
            if "bseindia.com" not in lowered:
                return
            if "stockpricecsv" in lowered or "csv" in lowered or "download" in lowered:
                captured.append((url, request.headers))

        self.page.on("request", remember)
        try:
            self.page.locator("#btnSubmit").click()
            state = self._result_state(task)
            if state == "NO_RECORD":
                return state, None, ""
            control = self._csv_control()
            anchor = control if control.evaluate("e => e.tagName.toLowerCase()") == "a" else control.locator("xpath=ancestor-or-self::a[1]")
            href = anchor.get_attribute("href") if anchor.count() else None
            if href and href.lower().startswith("http"):
                _validate_csv_request_url(href, task)
                return "DOWNLOADED", self._fetch_csv(href, {}), href
            before = len(captured)
            intercepted: list[tuple[str, dict[str, str]]] = []
            csv_route_pattern = re.compile(
                r".*(?:StockPriceCSVDownload|StockPriceCSV).*",
                re.IGNORECASE,
            )

            def intercept_csv(route, request) -> None:
                intercepted.append((request.url, request.headers))
                route.abort()

            self.page.route(csv_route_pattern, intercept_csv)
            try:
                control.click(no_wait_after=True)
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline and not intercepted:
                    self.page.wait_for_timeout(200)
            finally:
                self.page.unroute(csv_route_pattern, intercept_csv)

            candidates = intercepted or captured[before:] or captured
            if not candidates:
                raise RuntimeError("CSV control produced no capturable BSE request")
            candidates.sort(
                key=lambda item: (
                    "stockpricecsvdownload" in item[0].lower(),
                    "stockpricecsv" in item[0].lower(),
                    "csv" in item[0].lower(),
                )
            )
            url, headers = candidates[-1]
            _validate_csv_request_url(url, task)
            return "DOWNLOADED", self._fetch_csv(url, headers), url
        finally:
            self.page.remove_listener("request", remember)


def _select_mode(codes: list[str], mode: str) -> tuple[list[str], tuple[tuple[str, str], ...]]:
    if mode == "smoke":
        missing = sorted(set(SMOKE_CODES) - set(codes))
        if missing:
            raise ValueError(f"smoke codes missing from phase-one filenames: {missing}")
        return list(SMOKE_CODES), (WINDOWS[0],)
    if mode == "stability":
        return codes[:20], WINDOWS
    return codes, WINDOWS


def run(args: argparse.Namespace) -> int:
    downloads = args.downloads_root.resolve()
    source = args.source.resolve() if args.source else discover_phase_one_source(downloads)
    codes = extract_codes(source)
    selected_codes, windows = _select_mode(codes, args.mode)
    selected_keys = {task.key for task in build_tasks(selected_codes, windows)}
    all_tasks = build_tasks(codes, WINDOWS)
    store = ProgressStore(args.output_root.resolve(), source, codes, all_tasks)
    store.load_or_initialize()
    pending = [task for task in store.tasks if task.key in selected_keys and task.status not in TERMINAL_STATUSES and task.attempts < MAX_ATTEMPTS]
    skipped = len(selected_keys) - len(pending)
    print(f"BSE codes discovered: {len(codes)}; selected tasks: {len(selected_keys)}; resume-skipped: {skipped}")
    if not pending:
        print("No pending tasks for this mode.")
        return 0
    browser = BSEBrowser(output_root=store.output_root, headless=args.headless, timeout_ms=args.timeout_seconds * 1000)
    try:
        for position, task in enumerate(pending, 1):
            while task.attempts < MAX_ATTEMPTS and task.status not in TERMINAL_STATUSES:
                task.status = "RUNNING"
                task.attempts += 1
                task.updated_at = utc_now()
                task.error = ""
                store.persist()
                store.log(task, f"attempt {task.attempts}/{MAX_ATTEMPTS} started")
                try:
                    status, content, url = browser.run_task(task)
                    if status == "NO_RECORD":
                        task.status = "NO_RECORD"
                        task.rows = 0
                        task.csv_url = ""
                    else:
                        assert content is not None
                        validated, row_count = validate_csv_bytes(content, task)
                        destination = output_path(store.output_root, task)
                        _atomic_bytes(destination, validated)
                        task.status = "DOWNLOADED"
                        task.rows = row_count
                        task.output_file = str(destination)
                        task.csv_url = url
                    task.error = ""
                    task.updated_at = utc_now()
                    store.persist()
                    store.log(task, f"completed; rows={task.rows}")
                except Exception as exc:  # one bad security must not stop the queue
                    task.error = f"{type(exc).__name__}: {exc}"
                    task.status = "FAILED" if task.attempts >= MAX_ATTEMPTS else "PENDING"
                    task.updated_at = utc_now()
                    store.persist()
                    store.log(task, task.error)
                    try:
                        browser.recreate_page()
                    except Exception:
                        pass
                    if task.status != "FAILED":
                        time.sleep(min(60.0, args.delay_seconds * (2 ** (task.attempts - 1))))
                if task.status in TERMINAL_STATUSES or task.status == "FAILED":
                    break
            print(f"[{position}/{len(pending)}] {task.key}: {task.status} rows={task.rows} attempts={task.attempts}")
            if position < len(pending):
                time.sleep(args.delay_seconds)
    finally:
        browser.close()
    selected = [task for task in store.tasks if task.key in selected_keys]
    failures = [task for task in selected if task.status == "FAILED"]
    print(json.dumps({status: sum(task.status == status for task in selected) for status in (
        "DOWNLOADED", "NO_RECORD", "FAILED", "PENDING",
    )}, sort_keys=True))
    return 1 if failures else 0


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="Download official BSE daily history through a resumable local Playwright session.")
    value.add_argument("--mode", choices=("smoke", "stability", "full"), required=True)
    value.add_argument("--downloads-root", type=Path, default=default_downloads_root())
    value.add_argument("--source", type=Path, help="Phase-one BSE_2025_2026 folder or ZIP; auto-detected by default.")
    value.add_argument("--output-root", type=Path, default=default_downloads_root() / "BSE_History")
    value.add_argument("--delay-seconds", type=float, default=8.0)
    value.add_argument("--timeout-seconds", type=int, default=45)
    value.add_argument("--headless", action="store_true", help="Not recommended: BSE currently rejects headless Edge with HTTP 403.")
    return value


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.delay_seconds < 2 or args.timeout_seconds < 10:
        parser().error("delay must be at least 2 seconds and timeout at least 10 seconds")
    try:
        return run(args)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"BSE history acquisition failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
