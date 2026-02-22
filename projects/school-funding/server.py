"""
School Funding Monitor — MitRat Scraper + Web UI
=================================================
Scrapes financial data from MitRat (מית"ר) for school 144097
and displays it in a local web UI.

Usage:
    python -B server.py
    # Open http://localhost:8300
"""

import http.server
import json
import os
import sys
import threading
import traceback
import urllib.parse
from datetime import datetime

PORT = 8300
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "data.json")
SCHOOL_SYMBOL = "144097"
MITRAT_URL = "https://apps.education.gov.il/mtrnet/home.aspx"

# Global lock so only one scrape runs at a time
_scrape_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Data persistence
# ---------------------------------------------------------------------------

def load_data():
    """Load saved scrape data from disk."""
    if not os.path.isfile(DATA_FILE):
        return None
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def save_data(data):
    """Persist scrape data to disk."""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# MitRat Scraper (Playwright)
# ---------------------------------------------------------------------------

def scrape_mitrat():
    """
    Scrape MitRat for school 144097.
    Returns a dict with school info and financial tables.
    """
    from playwright.sync_api import sync_playwright

    result = {
        "school_symbol": SCHOOL_SYMBOL,
        "school_name": "",
        "scraped_at": datetime.now().isoformat(),
        "tables": [],
        "raw_texts": [],
        "errors": [],
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="he-IL",
        )
        page = context.new_page()
        page.set_default_timeout(30000)

        try:
            # Step 1: Navigate to MitRat home
            page.goto(MITRAT_URL, wait_until="networkidle")

            # Step 2: Click "מוסד" radio button (institution search)
            # The radio button switches search from מוטב (beneficiary) to מוסד (institution)
            mosad_radio = page.locator("input[type='radio'][value='מוסד']")
            if mosad_radio.count() == 0:
                # Try by label text
                mosad_radio = page.get_by_label("מוסד")
            if mosad_radio.count() == 0:
                # Try common ASP.NET radio patterns
                mosad_radio = page.locator("input[id*='Mosad'], input[id*='mosad'], input[id*='rdo'][value*='מוסד']")
            if mosad_radio.count() > 0:
                mosad_radio.first.click()
                page.wait_for_timeout(1000)
            else:
                result["errors"].append("Could not find מוסד radio button")

            # Step 3: Enter school symbol
            # Look for the symbol input field
            symbol_input = page.locator("input[id*='Semel'], input[id*='semel'], input[id*='Symbol'], input[id*='symbol'], input[id*='txt'][type='text']")
            if symbol_input.count() == 0:
                # Try broader search — find text inputs near the search area
                symbol_input = page.locator("input[type='text']")
            if symbol_input.count() > 0:
                symbol_input.first.fill(SCHOOL_SYMBOL)
                page.wait_for_timeout(500)
            else:
                result["errors"].append("Could not find symbol input field")

            # Step 4: Click search button
            search_btn = page.locator("input[value='חפש'], input[value*='חפש'], button:has-text('חפש'), input[id*='btn'][type='submit']")
            if search_btn.count() == 0:
                search_btn = page.locator("input[type='submit'], input[type='button']").filter(has_text="חפש")
            if search_btn.count() > 0:
                search_btn.first.click()
                page.wait_for_timeout(3000)
            else:
                result["errors"].append("Could not find search button")

            # Step 5: Wait for results and click on institution row
            page.wait_for_timeout(2000)

            # Try to find results grid/table
            result_links = page.locator("a[href*='144097'], a:has-text('144097'), td:has-text('144097')")
            if result_links.count() > 0:
                result_links.first.click()
                page.wait_for_timeout(3000)
            else:
                # Maybe results appear as a clickable row
                rows = page.locator("tr:has-text('144097')")
                if rows.count() > 0:
                    rows.first.click()
                    page.wait_for_timeout(3000)

            # Step 6: Extract school name from the page
            page_text = page.inner_text("body")
            # Try to find the school name near the symbol
            for line in page_text.split("\n"):
                line = line.strip()
                if SCHOOL_SYMBOL in line and len(line) > len(SCHOOL_SYMBOL) + 2:
                    result["school_name"] = line
                    break

            # Step 7: Extract all visible tables from the current page
            tables = _extract_tables(page)
            if tables:
                result["tables"].extend(tables)

            # Step 8: Look for navigation links to reports
            report_links = page.locator("a:has-text('ריכוז תשלומים'), a:has-text('תשלומים'), a:has-text('הקצאות'), a:has-text('תקציב')")
            report_names = []
            for i in range(report_links.count()):
                name = report_links.nth(i).inner_text().strip()
                report_names.append(name)

            # Visit each report link
            for i, name in enumerate(report_names):
                try:
                    link = report_links.nth(i)
                    if link.is_visible():
                        link.click()
                        page.wait_for_timeout(3000)
                        tables = _extract_tables(page, prefix=name)
                        if tables:
                            result["tables"].extend(tables)
                        # Navigate back if possible
                        page.go_back()
                        page.wait_for_timeout(2000)
                except Exception as e:
                    result["errors"].append(f"Error visiting report '{name}': {str(e)}")

            # Step 9: Capture a text snapshot of what we see
            try:
                visible_text = page.inner_text("body")
                # Keep first 5000 chars as raw context
                result["raw_texts"].append({
                    "page": page.url,
                    "text": visible_text[:5000],
                })
            except Exception:
                pass

        except Exception as e:
            result["errors"].append(f"Scraper error: {str(e)}")
            result["errors"].append(traceback.format_exc())

        finally:
            browser.close()

    return result


def _extract_tables(page, prefix=""):
    """Extract all HTML tables from the current page as structured data."""
    tables = []
    table_els = page.locator("table")
    for i in range(table_els.count()):
        try:
            table_el = table_els.nth(i)
            if not table_el.is_visible():
                continue
            rows_data = []
            rows = table_el.locator("tr")
            for j in range(rows.count()):
                cells = rows.nth(j).locator("td, th")
                row = []
                for k in range(cells.count()):
                    row.append(cells.nth(k).inner_text().strip())
                if row and any(c for c in row):  # skip empty rows
                    rows_data.append(row)
            if len(rows_data) > 1:  # at least header + 1 data row
                table_name = f"{prefix} — טבלה {i+1}" if prefix else f"טבלה {i+1}"
                tables.append({
                    "name": table_name,
                    "headers": rows_data[0] if rows_data else [],
                    "rows": rows_data[1:] if len(rows_data) > 1 else [],
                })
        except Exception:
            continue
    return tables


# ---------------------------------------------------------------------------
# HTML UI
# ---------------------------------------------------------------------------

def build_html(data):
    """Generate the full HTML page."""
    last_update = ""
    school_name = "בית ספר 144097"
    tables_html = "<p>אין נתונים עדיין. לחצו על 'רענן נתונים' כדי לטעון.</p>"
    errors_html = ""
    raw_html = ""

    if data:
        last_update = data.get("scraped_at", "")
        if last_update:
            try:
                dt = datetime.fromisoformat(last_update)
                last_update = dt.strftime("%d/%m/%Y %H:%M")
            except (ValueError, TypeError):
                pass
        school_name = data.get("school_name") or school_name

        # Build tables
        tables = data.get("tables", [])
        if tables:
            parts = []
            for t in tables:
                headers = t.get("headers", [])
                rows = t.get("rows", [])
                name = t.get("name", "")
                header_html = "".join(f"<th>{h}</th>" for h in headers)
                rows_html = ""
                for row in rows:
                    cells = "".join(f"<td>{c}</td>" for c in row)
                    rows_html += f"<tr>{cells}</tr>"
                parts.append(f"""
                    <div class="table-section">
                        <h3>{name}</h3>
                        <div class="table-wrap">
                            <table>
                                <thead><tr>{header_html}</tr></thead>
                                <tbody>{rows_html}</tbody>
                            </table>
                        </div>
                    </div>
                """)
            tables_html = "\n".join(parts)
        else:
            tables_html = "<p>לא נמצאו טבלאות. נסו לרענן.</p>"

        # Errors
        errors = data.get("errors", [])
        if errors:
            items = "".join(f"<li>{e[:200]}</li>" for e in errors)
            errors_html = f'<div class="errors"><h3>שגיאות</h3><ul>{items}</ul></div>'

        # Raw text preview
        raw_texts = data.get("raw_texts", [])
        if raw_texts:
            parts = []
            for rt in raw_texts:
                text = rt.get("text", "")[:3000]
                url = rt.get("page", "")
                parts.append(f'<details><summary>טקסט גולמי — {url}</summary><pre>{text}</pre></details>')
            raw_html = "\n".join(parts)

    return f"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>מעקב תקציב בית ספר</title>
<style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
        font-family: 'Segoe UI', Tahoma, Arial, sans-serif;
        background: #f0f2f5;
        color: #1a1a2e;
        direction: rtl;
        min-height: 100vh;
    }}
    .header {{
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        color: white;
        padding: 20px 32px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
        gap: 12px;
    }}
    .header h1 {{
        font-size: 1.5em;
        font-weight: 600;
    }}
    .header .meta {{
        font-size: 0.85em;
        opacity: 0.8;
    }}
    .header .meta span {{
        margin-inline-start: 16px;
    }}
    .actions {{
        display: flex;
        gap: 12px;
        align-items: center;
    }}
    .btn {{
        background: #0f3460;
        color: white;
        border: 1px solid rgba(255,255,255,0.2);
        padding: 10px 24px;
        border-radius: 6px;
        cursor: pointer;
        font-size: 0.95em;
        font-family: inherit;
        transition: background 0.2s;
    }}
    .btn:hover {{ background: #1a4f8a; }}
    .btn:disabled {{
        opacity: 0.5;
        cursor: not-allowed;
    }}
    .spinner {{
        display: none;
        width: 20px;
        height: 20px;
        border: 3px solid rgba(255,255,255,0.3);
        border-top-color: white;
        border-radius: 50%;
        animation: spin 0.8s linear infinite;
    }}
    .spinner.active {{ display: inline-block; }}
    @keyframes spin {{ to {{ transform: rotate(360deg); }} }}

    .container {{
        max-width: 1200px;
        margin: 24px auto;
        padding: 0 24px;
    }}
    .table-section {{
        background: white;
        border-radius: 8px;
        padding: 20px;
        margin-bottom: 16px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }}
    .table-section h3 {{
        margin-bottom: 12px;
        color: #16213e;
        font-size: 1.1em;
    }}
    .table-wrap {{
        overflow-x: auto;
    }}
    table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 0.9em;
    }}
    th, td {{
        border: 1px solid #e0e0e0;
        padding: 8px 12px;
        text-align: right;
    }}
    th {{
        background: #f8f9fa;
        font-weight: 600;
        color: #16213e;
        position: sticky;
        top: 0;
    }}
    tr:nth-child(even) {{ background: #fafbfc; }}
    tr:hover {{ background: #f0f4ff; }}

    .errors {{
        background: #fff5f5;
        border: 1px solid #feb2b2;
        border-radius: 8px;
        padding: 16px 20px;
        margin-bottom: 16px;
    }}
    .errors h3 {{ color: #c53030; margin-bottom: 8px; }}
    .errors li {{ margin-bottom: 4px; font-size: 0.85em; color: #742a2a; }}

    details {{
        background: white;
        border-radius: 8px;
        padding: 16px 20px;
        margin-bottom: 16px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }}
    details summary {{
        cursor: pointer;
        font-weight: 600;
        color: #16213e;
    }}
    details pre {{
        margin-top: 12px;
        white-space: pre-wrap;
        word-break: break-all;
        font-size: 0.8em;
        max-height: 300px;
        overflow-y: auto;
        background: #f8f9fa;
        padding: 12px;
        border-radius: 4px;
    }}

    .status-msg {{
        padding: 12px 20px;
        background: #ebf8ff;
        border: 1px solid #90cdf4;
        border-radius: 8px;
        margin-bottom: 16px;
        display: none;
        font-size: 0.9em;
        color: #2a4365;
    }}
    .status-msg.error {{
        background: #fff5f5;
        border-color: #feb2b2;
        color: #742a2a;
    }}
    .status-msg.active {{ display: block; }}
</style>
</head>
<body>

<div class="header">
    <div>
        <h1>מעקב תקציב — מית"ר</h1>
        <div class="meta">
            <span>סמל מוסד: {SCHOOL_SYMBOL}</span>
            <span>{school_name}</span>
            <span id="last-update">עדכון אחרון: {last_update or 'טרם עודכן'}</span>
        </div>
    </div>
    <div class="actions">
        <div class="spinner" id="spinner"></div>
        <button class="btn" id="refresh-btn" onclick="doRefresh()">רענן נתונים</button>
    </div>
</div>

<div class="container">
    <div class="status-msg" id="status-msg"></div>
    {errors_html}
    <div id="tables-area">
        {tables_html}
    </div>
    {raw_html}
</div>

<script>
async function doRefresh() {{
    const btn = document.getElementById('refresh-btn');
    const spinner = document.getElementById('spinner');
    const status = document.getElementById('status-msg');

    btn.disabled = true;
    spinner.classList.add('active');
    status.className = 'status-msg active';
    status.textContent = 'מרענן נתונים מאתר מית\\"ר... (עלול לקחת 10-30 שניות)';

    try {{
        const resp = await fetch('/api/refresh', {{ method: 'POST' }});
        const data = await resp.json();
        if (data.error) {{
            status.className = 'status-msg active error';
            status.textContent = 'שגיאה: ' + data.error;
        }} else {{
            // Reload the page to show updated data
            window.location.reload();
        }}
    }} catch (e) {{
        status.className = 'status-msg active error';
        status.textContent = 'שגיאת רשת: ' + e.message;
    }} finally {{
        btn.disabled = false;
        spinner.classList.remove('active');
    }}
}}
</script>

</body>
</html>"""


# ---------------------------------------------------------------------------
# HTTP Server
# ---------------------------------------------------------------------------

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/" or parsed.path == "":
            data = load_data()
            html = build_html(data)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))

        elif parsed.path == "/api/data":
            data = load_data()
            self._json_response(data or {"error": "No data yet"})

        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/api/refresh":
            if not _scrape_lock.acquire(blocking=False):
                self._json_response({"error": "Scrape already in progress"}, 409)
                return
            try:
                data = scrape_mitrat()
                save_data(data)
                self._json_response(data)
            except Exception as e:
                self._json_response({"error": str(e)}, 500)
            finally:
                _scrape_lock.release()
        else:
            self.send_response(404)
            self.end_headers()

    def _json_response(self, data, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def log_message(self, format, *args):
        # Print to stdout for debugging
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {args[0] if args else ''}")


def main():
    port = PORT
    if "--port" in sys.argv:
        idx = sys.argv.index("--port")
        if idx + 1 < len(sys.argv):
            port = int(sys.argv[idx + 1])

    server = http.server.HTTPServer(("127.0.0.1", port), Handler)
    print(f"School Funding Monitor running at http://localhost:{port}")
    print("Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()


if __name__ == "__main__":
    main()
