# School Funding Monitor

## What it is
Local web UI that scrapes MitRat (מית"ר) financial data for school symbol 144097 and displays it. MitRat is the Ministry of Education's budgeting system at `apps.education.gov.il/mtrnet/`.

## Architecture
- Single-file Python server (`server.py`) on port 8300
- Playwright headless Chromium for scraping
- stdlib `http.server` for the web UI (same pattern as `context_ui.py`)
- `data.json` for persisting scraped data between restarts

## Scraper flow
1. Navigate to `https://apps.education.gov.il/mtrnet/home.aspx`
2. Click "מוסד" radio button (switch from מוטב to institution search)
3. Enter `144097` in symbol field
4. Click "חפש" (search)
5. Click matching institution row in results
6. Navigate to available reports (payment summary, allocations)
7. Extract table data, save to `data.json`

## API endpoints
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Serve HTML UI |
| GET | `/api/data` | Return current scraped data |
| POST | `/api/refresh` | Trigger scraper, return updated data |

## Running
```bash
python -B projects/school-funding/server.py
# Open http://localhost:8300
```

## Key constraints
- MitRat is a legacy ASP.NET WebForms app — lots of postbacks and ViewState
- Scraping takes 10-20 seconds
- The scraper is exploratory — the exact reports available depend on the school
- Always use `python -B` to avoid pyc caching
