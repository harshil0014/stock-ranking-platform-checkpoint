from __future__ import annotations

import json
from pathlib import Path
from threading import Event, Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from stock_ranker.market_refresh import MarketRefreshController, RefreshAlreadyRunning
from stock_ranker.web_assets import APP_JS, INDEX_HTML
from stock_ranker.webapp import create_server


class FakeProcess:
    def __init__(self, *, exit_code: int = 0) -> None:
        self.pid = 9999
        self.exit_code = exit_code
        self.running = True
        self.done = Event()

    def poll(self):
        return None if self.running else self.exit_code

    def wait(self):
        self.done.wait(timeout=5)
        self.running = False
        return self.exit_code

    def finish(self) -> None:
        self.done.set()


def _project(root: Path) -> Path:
    runner = root / "marketdata/runners/refresh_company_data.py"
    runner.parent.mkdir(parents=True)
    runner.write_text("# test runner\n", encoding="utf-8")
    return root


def test_controller_starts_one_isolated_refresh_and_reports_success(tmp_path: Path) -> None:
    calls: list[tuple[list[str], dict]] = []
    process = FakeProcess()

    def popen(command, **kwargs):
        calls.append((command, kwargs))
        return process

    controller = MarketRefreshController(_project(tmp_path), popen=popen)
    initial = controller.start()
    assert initial["running"] is True
    assert initial["stage"] == "CHECKING_LATEST_MARKET_DATA"
    assert "--status-file" in calls[0][0]
    assert calls[0][1]["cwd"] == tmp_path.resolve()
    with pytest.raises(RefreshAlreadyRunning):
        controller.start()
    # The monitor is intentionally asynchronous; it preserves a successful runner result.
    process.finish()
    controller._monitor(process)
    status = controller.status()
    assert status["running"] is False
    assert status["status"] == "SUCCEEDED"
    assert status["last_known_good_retained"] is True


def test_controller_failure_keeps_last_known_good(tmp_path: Path) -> None:
    controller = MarketRefreshController(
        _project(tmp_path), popen=lambda *args, **kwargs: FakeProcess(exit_code=2)
    )
    result = controller.start()
    process = controller._process
    assert process is not None
    process.finish()
    controller._monitor(process)
    status = controller.status()
    assert status["status"] == "FAILED"
    assert status["last_known_good_retained"] is True
    assert "Previous accepted data retained" in status["message"]


def test_refresh_http_start_status_and_concurrent_rejection(tmp_path: Path) -> None:
    process = FakeProcess()
    controller = MarketRefreshController(
        _project(tmp_path), popen=lambda *args, **kwargs: process
    )
    server = create_server(port=0, refresh_controller=controller)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        request = Request(base + "/api/live/refresh", method="POST")
        with urlopen(request, timeout=10) as response:
            started = json.load(response)
        assert started["running"] is True
        with urlopen(base + "/api/live/refresh-status", timeout=10) as response:
            running = json.load(response)
        assert running["running"] is True
        with pytest.raises(HTTPError) as error:
            urlopen(request, timeout=10)
        assert error.value.code == 409
        payload = json.loads(error.value.read().decode("utf-8"))
        assert "already in progress" in payload["message"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_local_ui_exposes_refresh_control_and_nonblocking_polling() -> None:
    assert 'data-market-refresh' in INDEX_HTML
    assert '/api/live/refresh-status' in APP_JS
    assert "method:'POST'" in APP_JS
    assert "Refreshing…" in APP_JS
