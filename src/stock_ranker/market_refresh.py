"""Controlled background execution for user-triggered market maintenance."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import RLock, Thread
from typing import Any, Callable

from stock_ranker.data_state import atomic_write_json, data_state_status


class RefreshAlreadyRunning(RuntimeError):
    """Raised when a second refresh is requested while one is active."""


class MarketRefreshController:
    """Launch and observe the existing refresh runner without blocking serving."""

    def __init__(
        self,
        project_root: str | Path,
        *,
        popen: Callable[..., Any] | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.market_root = self.project_root / "data" / "live_market"
        self.runner = self.project_root / "marketdata" / "runners" / "refresh_company_data.py"
        self.status_path = self.market_root / "user_refresh_status.json"
        self.log_path = self.market_root / "user_refresh.log"
        self._popen = popen or subprocess.Popen
        self._process: Any | None = None
        self._guard = RLock()

    def _accepted(self) -> dict[str, Any]:
        try:
            state = data_state_status(self.market_root)
            return {
                "trade_date": state.get("trade_date"),
                "fingerprint": state.get("bundle_fingerprint"),
            }
        except (FileNotFoundError, KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            return {"trade_date": None, "fingerprint": None}

    def _read(self) -> dict[str, Any] | None:
        try:
            value = json.loads(self.status_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else None
        except (FileNotFoundError, OSError, TypeError, ValueError, json.JSONDecodeError):
            return None

    @staticmethod
    def _pid_is_running(pid: object) -> bool:
        try:
            numeric = int(pid)
            if numeric <= 0:
                return False
            os.kill(numeric, 0)
            return True
        except (OSError, TypeError, ValueError):
            return False

    def status(self) -> dict[str, Any]:
        with self._guard:
            value = self._read()
            accepted = self._accepted()
            if value is None:
                return {
                    "status": "READY",
                    "running": False,
                    "stage": "READY",
                    "started_at": None,
                    "completed_at": None,
                    "current_accepted_trade_date": accepted["trade_date"],
                    "current_accepted_fingerprint": accepted["fingerprint"],
                    "new_accepted_trade_date": None,
                    "new_accepted_fingerprint": None,
                    "provider_failures": [],
                    "last_known_good_retained": True,
                    "message": "Ready",
                }
            if value.get("running") and self._process is not None:
                value["running"] = self._process.poll() is None
            value["current_accepted_trade_date"] = accepted["trade_date"]
            value["current_accepted_fingerprint"] = accepted["fingerprint"]
            return value

    def _monitor(self, process: Any) -> None:
        exit_code = process.wait()
        with self._guard:
            value = self._read() or {}
            if value.get("running") or value.get("status") not in {"SUCCEEDED", "FAILED"}:
                accepted = self._accepted()
                succeeded = exit_code == 0
                value.update(
                    {
                        "status": "SUCCEEDED" if succeeded else "FAILED",
                        "running": False,
                        "stage": "COMPLETED" if succeeded else "FAILED",
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                        "new_accepted_trade_date": accepted["trade_date"] if succeeded else None,
                        "new_accepted_fingerprint": accepted["fingerprint"] if succeeded else None,
                        "last_known_good_retained": True,
                        "message": (
                            "Market data refresh completed successfully."
                            if succeeded
                            else "Refresh failed. Previous accepted data retained."
                        ),
                    }
                )
                atomic_write_json(self.status_path, value)
            self._process = None

    def start(self, *, source: str = "user") -> dict[str, Any]:
        with self._guard:
            prior = self._read()
            active_process = self._process is not None and self._process.poll() is None
            active_external = bool(
                prior and prior.get("running") and self._pid_is_running(prior.get("pid"))
            )
            if active_process or active_external:
                raise RefreshAlreadyRunning("A market-data refresh is already in progress.")
            if not self.runner.is_file():
                raise FileNotFoundError("The configured market refresh runner is unavailable.")

            accepted = self._accepted()
            started = datetime.now(timezone.utc).isoformat()
            initial = {
                "status": "RUNNING",
                "running": True,
                "stage": "CHECKING_LATEST_MARKET_DATA",
                "started_at": started,
                "completed_at": None,
                "current_accepted_trade_date": accepted["trade_date"],
                "current_accepted_fingerprint": accepted["fingerprint"],
                "new_accepted_trade_date": None,
                "new_accepted_fingerprint": None,
                "provider_failures": [],
                "last_known_good_retained": True,
                "message": "Checking latest market data…",
                "source": source,
            }
            atomic_write_json(self.status_path, initial)

            market_python = self.project_root / ".venv-marketdata" / "Scripts" / "python.exe"
            interpreter = market_python if market_python.is_file() else Path(sys.executable)
            command = [
                str(interpreter),
                str(self.runner),
                "--status-file",
                str(self.status_path),
            ]
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            log = self.log_path.open("ab")
            try:
                process = self._popen(
                    command,
                    cwd=self.project_root,
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except Exception:
                initial.update(
                    {
                        "status": "FAILED",
                        "running": False,
                        "stage": "FAILED",
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                        "message": "Refresh could not start. Previous accepted data retained.",
                    }
                )
                atomic_write_json(self.status_path, initial)
                raise
            finally:
                log.close()

            self._process = process
            initial["pid"] = getattr(process, "pid", None)
            atomic_write_json(self.status_path, initial)
            Thread(target=self._monitor, args=(process,), daemon=True).start()
            return dict(initial)
