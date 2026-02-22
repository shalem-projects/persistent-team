# School Funding Monitor

## What it is
Scrapes MitRat (מית"ר) financial data for school symbol 144097, generates a static HTML page, and uploads it to yisumatica via FTP. Run locally ~once a week.

Live page: https://www.yisumatica.org.il/school-funding/

## Architecture
- Single Python file (`server.py`) — scraper + HTML generator + FTP uploader
- Playwright headless Chromium for scraping
- Output: `data.json` (raw data) + `index.html` (static page)
- FTP to `yisumatica.org.il/school-funding/`

## Usage
```bash
python -B server.py                # scrape + generate + FTP upload
python -B server.py --scrape-only  # scrape + generate, no upload
python -B server.py --serve        # local preview at localhost:8300
```

## Scraper flow
1. Navigate to `https://apps.education.gov.il/mtrnet/home.aspx`
2. Click "מוסד" radio button (switch from מוטב to institution search)
3. Enter `144097` in symbol field
4. Click "חפש" (search)
5. Click matching institution row in results
6. Navigate to available reports (payment summary, allocations)
7. Extract table data, save to `data.json`
8. Generate static `index.html`
9. Upload both files via FTP

## Key constraints
- MitRat is a legacy ASP.NET WebForms app — lots of postbacks and ViewState
- Scraping takes 10-20 seconds
- The scraper is exploratory — the exact reports available depend on the school
- Always use `python -B` to avoid pyc caching
