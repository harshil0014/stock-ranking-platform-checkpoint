"""Exercise the rendered personalized workflow with Playwright."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from threading import Thread
from time import perf_counter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from playwright.sync_api import sync_playwright
from stock_ranker.webapp import create_server


def run(output: Path):
    output.parent.mkdir(parents=True, exist_ok=True)
    server = create_server(port=0, refresh_enabled=False)
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    console_errors, page_errors = [], []
    result = {}
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.goto(base + "/personalized", wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_selector("#personalizedForm", state="visible")
            primary_modes = page.locator("#dashboardModel option").evaluate_all(
                "options => options.map(option => [option.value, option.textContent])"
            )
            live_modes = page.locator("#liveModel option").evaluate_all(
                "options => options.map(option => [option.value, option.textContent])"
            )
            fields = ["personalizedAmount", "personalizedLookback", "personalizedInterval",
                      "personalizedTarget", "personalizedHorizon"]
            defaults = {field: page.locator("#" + field).input_value() for field in fields}
            editable = all(page.locator("#" + field).is_enabled() for field in fields)

            page.locator("#personalizedAmount").fill("999")
            page.locator("#personalizedRun").click()
            invalid_message = page.locator("#personalizedAmount").evaluate("element => element.validationMessage")

            page.locator("#personalizedAmount").fill("7500")
            first_started = perf_counter(); page.locator("#personalizedRun").click()
            page.wait_for_selector("#personalizedResults:not(.hidden)", timeout=120_000)
            first_seconds = perf_counter() - first_started
            first_fingerprint = page.locator("#personalizedFingerprint").inner_text()
            first_top = page.locator("#personalizedRows tr").first.inner_text()
            headers = page.locator("#personalizedRows").locator("xpath=../thead/tr/th").all_inner_texts()
            sector_options = page.locator("#personalizedSector option").count()
            first_cells = page.locator("#personalizedRows tr").first.locator("td").all_inner_texts()
            page.screenshot(path=str(output.with_suffix(".desktop.png")))
            profile_summary = page.locator("#personalizedProfileSummary").inner_text()
            page.locator("#personalizedRows tr").first.locator("button").click()
            inspection_visible = page.locator("#personalizedStock").is_visible()
            inspection = page.locator("#personalizedStockSummary").inner_text()
            page.locator("#personalizedSearch").fill("BOM:539997")
            fallback_row = page.locator("#personalizedRows tr").first.inner_text()
            fallback_search = page.locator("#personalizedRows tr").count() == 1 and "KPL" in fallback_row and "PRODUCT FALLBACK" in fallback_row
            page.locator("#personalizedRows tr").first.locator("button").click()
            fallback_inspection = page.locator("#personalizedStockSummary").inner_text()
            fallback_explained = ("BASELINE SECTOR RANK" in fallback_inspection
                                  and "BASELINE SCORE" in fallback_inspection
                                  and "PERSONALIZED SECTOR POSITION\nUnavailable" in fallback_inspection)
            page.locator("#personalizedSearch").fill("")
            page.locator("#personalizedSector").select_option("Retailing")
            sector_filtered = page.locator("#personalizedRows tr").count() > 0 and all(
                "Retailing" in value for value in page.locator("#personalizedRows tr").all_inner_texts()
            )
            page.locator("#personalizedSector").select_option("")

            page.locator("#personalizedTarget").fill("30")
            page.locator("#personalizedRun").click()
            page.wait_for_function("old => document.querySelector('#personalizedFingerprint').textContent !== old",
                                   arg=first_fingerprint, timeout=120_000)
            second_fingerprint = page.locator("#personalizedFingerprint").inner_text()

            page.locator("#personalizedTarget").fill("20")
            repeat_started = perf_counter(); page.locator("#personalizedRun").click()
            page.wait_for_function("expected => document.querySelector('#personalizedFingerprint').textContent === expected",
                                   arg=first_fingerprint, timeout=120_000)
            repeat_seconds = perf_counter() - repeat_started
            repeated_top = page.locator("#personalizedRows tr").first.inner_text()

            page.set_viewport_size({"width": 390, "height": 844})
            page.reload(wait_until="domcontentloaded")
            page.wait_for_selector("#personalizedForm", state="visible")
            boxes = [page.locator("#" + field).bounding_box() for field in fields]
            narrow_usable = all(box and box["x"] >= 0 and box["x"] + box["width"] <= 390 for box in boxes)
            refreshed_defaults = {field: page.locator("#" + field).input_value() for field in fields}
            refresh_cleared_result = page.locator("#personalizedResults").get_attribute("class").find("hidden") >= 0
            page.locator("#personalizedRun").click()
            page.wait_for_selector("#personalizedResults:not(.hidden)", timeout=120_000)
            mobile_table = page.locator("#personalizedRows tr").first.locator("td").count() == 10
            mobile_width = page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            mobile_overflow_elements = page.evaluate("""[...document.querySelectorAll('body *')]
              .filter(node => node.getBoundingClientRect().right > innerWidth + 2 && getComputedStyle(node).display !== 'none')
              .slice(0,12).map(node => ({tag:node.tagName,id:node.id,className:String(node.className).slice(0,80),right:Math.round(node.getBoundingClientRect().right)}))""")
            page.locator("#personalizedDisplayNote").scroll_into_view_if_needed()
            page.screenshot(path=str(output.with_suffix(".mobile.png")))
            browser.close()
            result = {
                "status": "PASS", "fields": fields, "defaults": defaults,
                "dashboard_modes": primary_modes, "live_modes": live_modes,
                "defaults_editable": editable, "invalid_message": invalid_message,
                "first_profile_summary": profile_summary, "first_run_seconds": first_seconds,
                "target_change_changed_profile": first_fingerprint != second_fingerprint,
                "back_to_back_repeat_exact": first_top == repeated_top,
                "repeat_seconds": repeat_seconds, "stock_inspection_visible": inspection_visible,
                "sector_headers": headers, "sector_option_count": sector_options,
                "first_row_cells": first_cells, "inspection_text": inspection,
                "fallback_alias_search": fallback_search, "sector_filter_works": sector_filtered,
                "fallback_inspection_explained": fallback_explained,
                "narrow_layout_usable": narrow_usable, "refresh_defaults": refreshed_defaults,
                "mobile_table_cells": mobile_table, "mobile_viewport_no_horizontal_overflow": mobile_width,
                "mobile_overflow_elements": mobile_overflow_elements,
                "refresh_cleared_result": refresh_cleared_result,
                "console_errors": console_errors, "page_errors": page_errors,
            }
            expected_modes = [["baseline_v1", "Baseline"], ["personalized", "Personalized"]]
            if not all((primary_modes == expected_modes, live_modes == expected_modes,
                        editable, "1000" in invalid_message,
                        result["target_change_changed_profile"], result["back_to_back_repeat_exact"],
                        inspection_visible, "PERSONALIZED SECTOR RANK" in headers,
                        sector_options > 50, len(first_cells) == 10,
                        "personalized sector position" in inspection.lower(),
                        fallback_search, fallback_explained, sector_filtered,
                        narrow_usable, mobile_table, mobile_width, refresh_cleared_result)) or console_errors or page_errors:
                result["status"] = "FAIL"
                raise RuntimeError(json.dumps(result, indent=2))
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output)
