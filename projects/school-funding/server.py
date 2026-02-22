"""
School Funding Monitor — MitRat Scraper + Static Site Generator
================================================================
Scrapes financial data from MitRat (מית"ר) for school 144097,
saves to data.json, generates a static index.html, and uploads
both to yisumatica via FTP.

Usage:
    python -B server.py                # scrape + generate + upload
    python -B server.py --scrape-only  # scrape + generate, no upload
    python -B server.py --serve        # local preview server on :8300
"""

import http.server
import json
import os
import subprocess
import sys
import traceback
from datetime import datetime

PORT = 8300
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "data.json")
HTML_FILE = os.path.join(BASE_DIR, "index.html")
SCHOOL_SYMBOL = "144097"
MITRAT_URL = "https://apps.education.gov.il/mtrnet/home.aspx"

FTP_HOST = "109.207.77.32"
FTP_USER = "yisumonimyisumat"
FTP_PASS = "mzaiyns217mzaiyns217"
FTP_PATH = "/public_html/school-funding"


# ---------------------------------------------------------------------------
# Data persistence
# ---------------------------------------------------------------------------

def load_data():
    if not os.path.isfile(DATA_FILE):
        return None
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# MitRat Scraper (Playwright)
# ---------------------------------------------------------------------------

def scrape_mitrat():
    """Scrape MitRat for school 144097. Returns dict with financial tables."""
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
            page.wait_for_timeout(2000)

            # Step 2: Click "מוסד" radio button
            mosad_radio = page.locator("input[type='radio'][value='מוסד']")
            if mosad_radio.count() == 0:
                mosad_radio = page.get_by_label("מוסד")
            if mosad_radio.count() == 0:
                mosad_radio = page.locator("input[id*='Mosad'], input[id*='mosad'], input[id*='rdo'][value*='מוסד']")
            if mosad_radio.count() > 0:
                mosad_radio.first.click()
                page.wait_for_timeout(1500)
            else:
                result["errors"].append("Could not find מוסד radio button")

            # Step 3: Enter school symbol
            symbol_input = page.locator("input[id*='Semel'], input[id*='semel'], input[id*='Symbol'], input[id*='symbol'], input[id*='txt'][type='text']")
            if symbol_input.count() == 0:
                symbol_input = page.locator("input[type='text']")
            if symbol_input.count() > 0:
                symbol_input.first.fill(SCHOOL_SYMBOL)
                page.wait_for_timeout(1000)
            else:
                result["errors"].append("Could not find symbol input field")

            # Step 4: Click search
            search_btn = page.locator("input[value='חפש'], input[value*='חפש'], button:has-text('חפש'), input[id*='btn'][type='submit']")
            if search_btn.count() == 0:
                search_btn = page.locator("input[type='submit'], input[type='button']").filter(has_text="חפש")
            if search_btn.count() > 0:
                search_btn.first.click()
                # Wait for navigation away from home.aspx
                try:
                    page.wait_for_url("**/RptList*", timeout=10000)
                except Exception:
                    page.wait_for_timeout(5000)
            else:
                result["errors"].append("Could not find search button")

            # Step 5: Check if we made it past the home page
            current_url = page.url.lower()
            if "home.aspx" in current_url:
                # Search didn't navigate — try clicking result row
                result_links = page.locator("a[href*='144097'], a:has-text('144097'), td:has-text('144097')")
                if result_links.count() > 0:
                    result_links.first.click()
                    page.wait_for_timeout(3000)
                else:
                    rows = page.locator("tr:has-text('144097')")
                    if rows.count() > 0:
                        rows.first.click()
                        page.wait_for_timeout(3000)

            # Verify we're on the report list or report page
            current_url = page.url.lower()
            if "home.aspx" in current_url:
                result["errors"].append(f"Failed to navigate past home page. Still on: {page.url}")

            # Step 6: Extract school name
            page_text = page.inner_text("body")
            for line in page_text.split("\n"):
                line = line.strip()
                if SCHOOL_SYMBOL in line and len(line) > len(SCHOOL_SYMBOL) + 2:
                    result["school_name"] = line
                    break

            # Step 7: We're on RptList.aspx — report selection page.
            # Find report links in the sidebar/menu and click each one,
            # then click "הצגת הדו"ח" to load the report.

            # First, try the sidebar report links
            report_selectors = [
                ("ריכוז תשלומים", "a:has-text('ריכוז תשלומים')"),
                ("שכר לימוד", "a:has-text('שכר לימוד')"),
                ("ריכוז משרות", "a:has-text('ריכוז משרות')"),
                ("שעורי עזר לעולים", "a:has-text('שעורי עזר לעולים')"),
                ("שרתים ומזכירים", "a:has-text('שרתים ומזכירים')"),
            ]

            for report_name, selector in report_selectors:
                try:
                    link = page.locator(selector)
                    if link.count() == 0:
                        continue
                    link.first.click()
                    page.wait_for_timeout(2000)

                    # Click "הצגת הדו"ח" button if present
                    show_btn = page.locator("input[value*='הצגת'], button:has-text('הצגת'), a:has-text('הצגת הדו')")
                    if show_btn.count() > 0:
                        show_btn.first.click()
                        page.wait_for_timeout(4000)

                    # Wait for data to actually render (ASP.NET postbacks are slow)
                    try:
                        page.wait_for_function(
                            "() => document.body.innerText.length > 500",
                            timeout=10000)
                    except Exception:
                        page.wait_for_timeout(5000)

                    # Extract tables — try HTML tables first, fall back to text parsing
                    tables = _extract_tables(page, prefix=report_name)
                    if not tables:
                        tables = _extract_tables_from_text(page, prefix=report_name)
                    if tables:
                        result["tables"].extend(tables)
                    else:
                        try:
                            text = page.inner_text("body")[:2000]
                            result["raw_texts"].append({
                                "page": f"{page.url} [{report_name}]",
                                "text": text,
                            })
                        except Exception:
                            pass

                    # Navigate back to report list
                    back_link = page.locator("a:has-text('בחר דו'), a:has-text('חזור')")
                    if back_link.count() > 0:
                        back_link.first.click()
                        page.wait_for_timeout(2000)
                    else:
                        page.go_back()
                        page.wait_for_timeout(2000)

                except Exception as e:
                    result["errors"].append(f"Error on report '{report_name}': {str(e)}")

            # Also try "ריכוז תשלומים" from the top menu (different nav path)
            if not result["tables"]:
                try:
                    menu_link = page.locator("a[href*='Rikuz'], a[href*='rikuz'], a[href*='Payment']")
                    if menu_link.count() > 0:
                        menu_link.first.click()
                        page.wait_for_timeout(4000)
                        tables = _extract_tables(page, prefix="ריכוז תשלומים (תפריט)")
                        if tables:
                            result["tables"].extend(tables)
                except Exception as e:
                    result["errors"].append(f"Menu nav error: {str(e)}")

            # Final raw text snapshot
            try:
                visible_text = page.inner_text("body")
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
    """Extract all HTML tables from the page as structured data."""
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
                if row and any(c for c in row):
                    rows_data.append(row)
            if len(rows_data) > 1:
                table_name = f"{prefix} — טבלה {i+1}" if prefix else f"טבלה {i+1}"
                tables.append({
                    "name": table_name,
                    "headers": rows_data[0],
                    "rows": rows_data[1:],
                })
        except Exception:
            continue
    return tables


def _extract_tables_from_text(page, prefix=""):
    """
    Fallback: parse visible page text into table data.
    MitRat renders GridView data that inner_text() returns as tab-separated lines.
    We detect the header row (known columns) and parse subsequent rows.
    """
    try:
        text = page.inner_text("body")
    except Exception:
        return []

    lines = [l.strip() for l in text.split("\n") if l.strip()]
    tables = []

    # Known header patterns from MitRat reports
    header_markers = ["קוד נושא", "תאור נושא", "חודש תחולה", "סך הכל מגיע"]

    header_idx = None
    for i, line in enumerate(lines):
        if any(m in line for m in header_markers):
            header_idx = i
            break

    if header_idx is None:
        return []

    # Parse header — split by tab
    header_line = lines[header_idx]
    headers = [h.strip() for h in header_line.split("\t") if h.strip()]
    if len(headers) < 3:
        return []

    # MitRat duplicates headers as individual lines (sortable column headers).
    # Skip until we find a tab-separated data row (3+ tab-separated fields,
    # first field is a number).
    rows = []
    for line in lines[header_idx + 1:]:
        # Replace \xa0 (nbsp) with space
        line = line.replace("\xa0", " ").strip()
        if not line or line == "\t":
            continue
        cols = [c.strip() for c in line.split("\t")]
        # Filter out empty columns but keep structure
        cols = [c for c in cols if c]
        if len(cols) < 3:
            # Single-cell lines from the duplicate header block — skip
            continue
        # Check if this is a data row (first column is numeric code)
        if cols[0].isdigit():
            rows.append(cols)
        elif rows:
            # We had data and hit a non-data line — stop
            break

    if rows:
        tables.append({
            "name": prefix or "טבלת נתונים",
            "headers": headers,
            "rows": rows,
        })

    return tables


# ---------------------------------------------------------------------------
# Static HTML generator
# ---------------------------------------------------------------------------

def build_html(data):
    """Generate a self-contained static HTML page from scraped data."""
    last_update = ""
    school_name = "בית ספר 144097"
    tables_html = '<p class="empty">אין נתונים עדיין.</p>'
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

        tables = data.get("tables", [])
        if tables:
            parts = []
            for t in tables:
                headers = t.get("headers", [])
                rows = t.get("rows", [])
                name = t.get("name", "")
                header_html = "".join(f"<th>{_esc(h)}</th>" for h in headers)
                rows_html = ""
                for row in rows:
                    cells = "".join(f"<td>{_esc(c)}</td>" for c in row)
                    rows_html += f"<tr>{cells}</tr>"
                parts.append(f"""
                <div class="table-section">
                    <h3>{_esc(name)}</h3>
                    <div class="table-wrap">
                        <table>
                            <thead><tr>{header_html}</tr></thead>
                            <tbody>{rows_html}</tbody>
                        </table>
                    </div>
                </div>""")
            tables_html = "\n".join(parts)
        else:
            tables_html = "<p>לא נמצאו טבלאות.</p>"

        errors = data.get("errors", [])
        if errors:
            items = "".join(f"<li>{_esc(e[:200])}</li>" for e in errors)
            errors_html = f'<div class="errors"><h3>שגיאות בגריפה</h3><ul>{items}</ul></div>'

        raw_texts = data.get("raw_texts", [])
        if raw_texts:
            parts = []
            for rt in raw_texts:
                text = _esc(rt.get("text", "")[:3000])
                url = _esc(rt.get("page", ""))
                parts.append(f'<details><summary>טקסט גולמי — {url}</summary><pre>{text}</pre></details>')
            raw_html = "\n".join(parts)

    return f"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>מעקב תקציב — מית&quot;ר — {_esc(SCHOOL_SYMBOL)}</title>
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
.header h1 {{ font-size: 1.5em; font-weight: 600; }}
.header .meta {{ font-size: 0.85em; opacity: 0.8; }}
.header .meta span {{ margin-inline-start: 16px; }}
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
.table-wrap {{ overflow-x: auto; }}
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
details summary {{ cursor: pointer; font-weight: 600; color: #16213e; }}
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
.empty {{ padding: 40px; text-align: center; color: #666; font-size: 1.1em; }}
</style>
</head>
<body>

<div class="header">
    <div>
        <h1>מעקב תקציב — מית&quot;ר</h1>
        <div class="meta">
            <span>סמל מוסד: {_esc(SCHOOL_SYMBOL)}</span>
            <span>{_esc(school_name)}</span>
            <span>עדכון אחרון: {_esc(last_update) or 'טרם עודכן'}</span>
        </div>
    </div>
</div>

<div class="container">
    {errors_html}
    {tables_html}
    {raw_html}
</div>

</body>
</html>"""


def _esc(text):
    """Minimal HTML escaping."""
    return (str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


# ---------------------------------------------------------------------------
# FTP upload
# ---------------------------------------------------------------------------

def ftp_upload():
    """Upload index.html and data.json to yisumatica via curl."""
    files = []
    if os.path.isfile(HTML_FILE):
        files.append(("index.html", HTML_FILE))
    if os.path.isfile(DATA_FILE):
        files.append(("data.json", DATA_FILE))

    if not files:
        print("Nothing to upload.")
        return False

    # Ensure remote directory exists (curl mkdir)
    mkdir_cmd = [
        "curl", "--ftp-create-dirs",
        f"ftp://{FTP_HOST}{FTP_PATH}/",
        "--user", f"{FTP_USER}:{FTP_PASS}",
        "-Q", f"MKD {FTP_PATH}",
        "--silent", "--output", "/dev/null",
    ]
    subprocess.run(mkdir_cmd, capture_output=True)

    ok = True
    for remote_name, local_path in files:
        remote_url = f"ftp://{FTP_HOST}{FTP_PATH}/{remote_name}"
        cmd = [
            "curl", "-T", local_path, remote_url,
            "--user", f"{FTP_USER}:{FTP_PASS}",
        ]
        print(f"Uploading {remote_name}...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  FAILED: {result.stderr.strip()}")
            ok = False
        else:
            print(f"  OK")
    return ok


# ---------------------------------------------------------------------------
# Local preview server (optional)
# ---------------------------------------------------------------------------

def serve_local(port):
    """Start a local HTTP server for previewing the static page."""
    import urllib.parse

    class PreviewHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path in ("/", ""):
                if os.path.isfile(HTML_FILE):
                    with open(HTML_FILE, "r", encoding="utf-8") as f:
                        html = f.read()
                else:
                    html = build_html(load_data())
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(html.encode("utf-8"))
            elif parsed.path == "/data.json":
                data = load_data()
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps(data or {}, ensure_ascii=False).encode("utf-8"))
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {args[0] if args else ''}")

    server = http.server.HTTPServer(("127.0.0.1", port), PreviewHandler)
    print(f"Preview server at http://localhost:{port}")
    print("Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if "--serve" in sys.argv:
        port = PORT
        if "--port" in sys.argv:
            idx = sys.argv.index("--port")
            if idx + 1 < len(sys.argv):
                port = int(sys.argv[idx + 1])
        serve_local(port)
        return

    # Step 1: Scrape
    print(f"Scraping MitRat for school {SCHOOL_SYMBOL}...")
    data = scrape_mitrat()
    save_data(data)
    n_tables = len(data.get("tables", []))
    n_errors = len(data.get("errors", []))
    print(f"  {n_tables} tables found, {n_errors} errors")
    if data.get("school_name"):
        print(f"  School: {data['school_name']}")

    # Step 2: Generate static HTML
    html = build_html(data)
    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Generated {HTML_FILE}")

    # Step 3: Upload (unless --scrape-only)
    if "--scrape-only" not in sys.argv:
        print("Uploading to yisumatica...")
        ok = ftp_upload()
        if ok:
            print(f"Done! View at https://www.yisumatica.org.il/school-funding/")
        else:
            print("Upload had errors. Check output above.")
    else:
        print("Scrape-only mode. Skipping upload.")
        print(f"Preview: python -B server.py --serve")


if __name__ == "__main__":
    main()
