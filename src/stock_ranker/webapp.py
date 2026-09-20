"""Dependency-free read-only server for the stock-ranking product."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import subprocess
from typing import Any
from urllib.parse import parse_qs, urlparse

from stock_ranker.web_assets import APP_JS, INDEX_HTML, STYLES_CSS
from stock_ranker.market_refresh import MarketRefreshController, RefreshAlreadyRunning
from stock_ranker.live_website import (
    LiveWebsiteError,
    company_facts_coverage,
    deployment_health,
    live_dashboard,
    live_data_status,
    live_history,
    live_overview,
    live_stock,
)
from stock_ranker.research_website import (
    ResearchWebsiteError,
    historical,
    methodology,
    model_candidates,
    overview,
    professor_acceptance,
    professor_reference,
    quant_lab,
    provenance as research_provenance,
    rankings,
    status as research_status,
    stock_explanation,
    validation,
)
from stock_ranker.website import analyze_website_request


MAX_REQUEST_BYTES = 30 * 1024 * 1024


class ResearchWebsiteHandler(BaseHTTPRequestHandler):
    """Serve static assets and the in-process canonical analysis endpoint."""

    server_version = "StockRankingPlatform/1.0"

    def _refresh_controller(self) -> MarketRefreshController:
        return self.server.refresh_controller  # type: ignore[attr-defined]

    def _send(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        request = urlparse(self.path)
        path = request.path
        query = parse_qs(request.query)
        routes = {
            "/": (INDEX_HTML, "text/html; charset=utf-8"),
            "/dashboard": (INDEX_HTML, "text/html; charset=utf-8"),
            "/live": (INDEX_HTML, "text/html; charset=utf-8"),
            "/overview": (INDEX_HTML, "text/html; charset=utf-8"),
            "/rankings": (INDEX_HTML, "text/html; charset=utf-8"),
            "/historical": (INDEX_HTML, "text/html; charset=utf-8"),
            "/validation": (INDEX_HTML, "text/html; charset=utf-8"),
            "/provenance": (INDEX_HTML, "text/html; charset=utf-8"),
            "/methodology": (INDEX_HTML, "text/html; charset=utf-8"),
            "/status": (INDEX_HTML, "text/html; charset=utf-8"),
            "/quant-lab": (INDEX_HTML, "text/html; charset=utf-8"),
            "/app.js": (APP_JS, "text/javascript; charset=utf-8"),
            "/styles.css": (STYLES_CSS, "text/css; charset=utf-8"),
        }
        if path == "/api/health":
            try:
                self._json(HTTPStatus.OK, deployment_health())
            except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                self._json(HTTPStatus.SERVICE_UNAVAILABLE, {
                    "status": "not_ready", "service": "stock-ranking-website",
                    "ready": False, "error": type(exc).__name__,
                })
            return
        if path == "/api/live/refresh-status":
            payload = self._refresh_controller().status()
            payload["enabled"] = bool(self.server.refresh_enabled)  # type: ignore[attr-defined]
            if not payload["enabled"]:
                payload["message"] = "Refresh disabled in read-only deployment"
            self._json(HTTPStatus.OK, payload)
            return
        live_routes = {
            "/api/live/dashboard": lambda: live_dashboard(
                query.get("sector", [""])[0], query.get("model", ["baseline_v1"])[0],
                query.get("segment", [""])[0],
                fingerprint_only=query.get("fingerprint_only", ["false"])[0].lower() == "true",
            ),
            "/api/live/overview": lambda: live_overview(query.get("model", ["baseline_v1"])[0]),
            "/api/live/stock": lambda: live_stock(query.get("ticker", [""])[0]),
            "/api/live/history": lambda: live_history(
                query.get("ticker", [""])[0], query.get("range", ["1y"])[0]
            ),
            "/api/live/data-status": lambda: live_data_status(),
            "/api/live/company-facts-coverage": lambda: company_facts_coverage(),
        }
        if path in live_routes:
            try:
                self._json(HTTPStatus.OK, live_routes[path]())
            except LiveWebsiteError as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"available": False, "status": "LIVE MARKET REQUEST ERROR", "error": str(exc)})
            except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {
                    "available": False, "status": "CONTROLLED LIVE MARKET API ERROR",
                    "error": f"Prepared live-market response is unavailable ({type(exc).__name__}).",
                })
            return
        research_routes = {
            "/api/research/overview": lambda: overview(),
            "/api/research/rankings": lambda: rankings(query.get("model", ["research_v2"])[0]),
            "/api/research/stock": lambda: stock_explanation(
                query.get("model", ["research_v2"])[0], query.get("ticker", [""])[0]
            ),
            "/api/research/historical": lambda: historical(query.get("year", [""])[0]),
            "/api/research/validation": lambda: validation(),
            "/api/research/provenance": lambda: research_provenance(query.get("ticker", [""])[0]),
            "/api/research/methodology": lambda: methodology(),
            "/api/research/status": lambda: research_status(),
            "/api/research/model-candidates": lambda: model_candidates(query.get("ticker", [""])[0]),
            "/api/research/quant-lab": lambda: quant_lab(),
            "/api/research/professor-reference": lambda: professor_reference(
                query.get("sector", [""])[0]
            ),
            "/api/research/professor-acceptance": lambda: professor_acceptance(
                query.get("search", [""])[0]
            ),
        }
        if path in research_routes:
            try:
                payload = research_routes[path]()
                self._json(HTTPStatus.OK, payload)
            except ResearchWebsiteError as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"available": False, "status": "INTEGRITY OR REQUEST ERROR", "error": str(exc)})
            except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {
                    "available": False, "status": "CONTROLLED RESEARCH API ERROR",
                    "error": f"Prepared research response is unavailable ({type(exc).__name__}).",
                })
            return
        if path not in routes:
            self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
            return
        text, content_type = routes[path]
        self._send(HTTPStatus.OK, text.encode("utf-8"), content_type)

    def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        path = urlparse(self.path).path
        if path == "/api/live/refresh":
            if not self.server.refresh_enabled:  # type: ignore[attr-defined]
                self._json(HTTPStatus.FORBIDDEN, {
                    "status": "DISABLED", "running": False,
                    "last_known_good_retained": True,
                    "message": "Market refresh is disabled in this read-only deployment.",
                })
                return
            try:
                self._json(HTTPStatus.ACCEPTED, self._refresh_controller().start())
            except RefreshAlreadyRunning as exc:
                payload = self._refresh_controller().status()
                payload["message"] = str(exc)
                self._json(HTTPStatus.CONFLICT, payload)
            except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
                self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {
                    "status": "FAILED", "running": False,
                    "last_known_good_retained": True,
                    "message": f"Refresh could not start ({type(exc).__name__}). Previous accepted data retained.",
                })
            return
        if path != "/api/analyze":
            self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
            return
        if self.headers.get_content_type() != "application/json":
            self._json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "Content-Type must be application/json"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_REQUEST_BYTES:
                raise ValueError("Request body is empty or exceeds the 30 MiB local limit")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            result = analyze_website_request(payload)
        except (ValueError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        self._json(HTTPStatus.OK, result)

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")


def create_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    *,
    refresh_controller: MarketRefreshController | None = None,
    refresh_enabled: bool = True,
) -> ThreadingHTTPServer:
    """Create, but do not start, the website server."""

    if host not in {"127.0.0.1", "localhost", "0.0.0.0", "::"}:
        raise ValueError("host must be localhost, 127.0.0.1, 0.0.0.0, or ::")
    if isinstance(port, bool) or not isinstance(port, int) or not 0 <= port <= 65535:
        raise ValueError("port must be an integer from 0 through 65535")
    server = ThreadingHTTPServer((host, port), ResearchWebsiteHandler)
    server.refresh_controller = refresh_controller or MarketRefreshController(  # type: ignore[attr-defined]
        Path(__file__).resolve().parents[2]
    )
    server.refresh_enabled = refresh_enabled  # type: ignore[attr-defined]
    return server


def start_background_refresh(
    project_root: str | Path | None = None,
    *,
    controller: MarketRefreshController | None = None,
) -> subprocess.Popen[bytes] | None:
    """Start one isolated bounded refresh; serving never waits for or depends on it."""

    try:
        manager = controller or MarketRefreshController(
            project_root or Path(__file__).resolve().parents[2]
        )
        manager.start(source="startup")
        return manager._process  # compatibility for callers that inspect the process
    except (FileNotFoundError, OSError, RefreshAlreadyRunning, RuntimeError, ValueError):
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve the local Indian equity research website.")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8765")))
    parser.add_argument("--auto-refresh", action="store_true", help="Opt in to one startup refresh check.")
    parser.add_argument("--enable-refresh-api", action="store_true", help="Enable mutable refresh endpoints.")
    parser.add_argument("--no-auto-refresh", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        controller = MarketRefreshController(Path(__file__).resolve().parents[2])
        server = create_server(
            host=args.host, port=args.port, refresh_controller=controller,
            refresh_enabled=args.enable_refresh_api,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    url = f"http://{args.host}:{server.server_address[1]}"
    should_refresh = args.auto_refresh and not args.no_auto_refresh
    refresh = start_background_refresh(controller=controller) if should_refresh else None
    print(f"Indian Equity Research Platform: {url}", flush=True)
    print(
        "Market refresh: disabled" if not should_refresh else
        "Market refresh: checking free public sources in the background",
        flush=True,
    )
    print("Press Ctrl+C to stop.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nWebsite stopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
