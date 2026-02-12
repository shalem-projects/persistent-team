#!/usr/bin/env python3
"""
Merge city ranking scores from two data streams:
  Stream A: Municipal protocol orientation analysis (PROOCOLS)
  Stream B: Educational program exposure scores (EDUCATIONAL_PROGRAMS)

Outputs:
  - merged_city_ranking.json  (combined data)
  - site/index.html           (public-facing results page)
"""

import json
import os
from pathlib import Path

BASE = Path(__file__).parent
PROOCOLS_FILE = BASE.parent / "דירוג ערים קודם" / "PROOCOLS" / "city_orientation_results.json"
EXPOSURE_FILE = BASE.parent / "EDUCATIONAL_PROGRAMS" / "city_exposure_scores.json"
OUTPUT_JSON = BASE / "merged_city_ranking.json"
OUTPUT_HTML = BASE / "site" / "index.html"

# City name normalization: PROOCOLS uses English keys, Exposure uses Hebrew
CITY_NAME_MAP = {
    "ariel":         "אריאל",
    "BEER_SHEVA":    "באר שבע",
    "EFRAT":         "אפרת",
    "EMANUEL":       "עמנואל",
    "GIVAT_SHMUEL":  "גבעת שמואל",
    "GIVATAYIM":     "גבעתיים",
    "HAIFA":         "חיפה",
    "HERZLIYA":      "הרצליה",
    "HOD_HASHARON":  "הוד השרון",
    "KARMIEL":       "כרמיאל",
    "KIRYAT_GAT":    "קרית גת",
    "KIRYAT_ONO":    "קרית אונו",
    "NETIVOT":       "נתיבות",
    "RAANANA":       "רעננה",
    "ROSH_HAAYIN":   "ראש העין",
}

# Reverse: Hebrew -> English key
HEBREW_TO_KEY = {v: k for k, v in CITY_NAME_MAP.items()}

# Some exposure cities have slightly different Hebrew names
EXPOSURE_HEBREW_ALIASES = {
    "תל אביב-יפו": None,       # no protocol data
    "ירושלים": None,             # no protocol data
    "רמת גן": None,             # no protocol data
    "רמת השרון": None,           # no protocol data (different from הוד השרון)
    "קרית שמונה": None,         # no protocol data
}


def load_protocols():
    with open(PROOCOLS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    cities = {}
    for key, vals in data["cities"].items():
        hebrew = CITY_NAME_MAP.get(key, key)
        cities[hebrew] = {
            "key": key,
            "pole_a": vals["pole_a_score"],
            "pole_b": vals["pole_b_score"],
            "red_flag": vals["red_flag_score"],
            "ab_ratio": round(vals["pole_a_score"] / max(vals["pole_b_score"], 0.01), 2),
            "files_scanned": vals["files_scanned"],
            "files_total": vals["files_total"],
            "text_length": vals["text_length"],
        }
    return cities, data


def load_exposure():
    with open(EXPOSURE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    cities = {}
    for entry in data["rankings"]:
        name = entry["city"]
        cities[name] = {
            "exposure_normalized": entry["exposure_normalized"],
            "exposure_raw": entry["exposure_raw"],
            "subversive_budget": entry["subversive_budget"],
            "subversive_ratio": entry["subversive_ratio"],
            "total_budget": entry["total_budget"],
            "total_deployments": entry["total_deployments"],
            "subversive_deployments": entry["subversive_deployments"],
            "rating_breakdown": entry["rating_breakdown"],
        }
    return cities, data


def compute_combined_score(proto, expo):
    """
    Combined score formula:
      - Pole B (progressive signal in protocols): 0-10, weight 30%
      - Red flags (institutional capture): 0-1 (capped), weight 20%
      - Educational exposure: 0-100, weight 50%

    All normalized to 0-100 scale. Higher = more ideological penetration.
    """
    pole_b_norm = min(proto["pole_b"] / 3.0, 1.0) * 100  # 3.0 is ~max observed (Givatayim 2.25)
    red_flag_norm = min(proto["red_flag"] / 0.15, 1.0) * 100  # 0.15 is ~max (Hod HaSharon 0.09 * ~1.5 headroom)
    expo_norm = expo["exposure_normalized"]  # already 0-100

    combined = (pole_b_norm * 0.30) + (red_flag_norm * 0.20) + (expo_norm * 0.50)
    return round(combined, 2)


def merge():
    proto_cities, proto_raw = load_protocols()
    expo_cities, expo_raw = load_exposure()

    merged = []

    # Cities in both datasets
    all_hebrew = set(proto_cities.keys()) | set(expo_cities.keys())

    for city in sorted(all_hebrew):
        entry = {"city": city}

        has_proto = city in proto_cities
        has_expo = city in expo_cities

        if has_proto:
            entry.update({
                "protocol_key": proto_cities[city]["key"],
                "pole_a": proto_cities[city]["pole_a"],
                "pole_b": proto_cities[city]["pole_b"],
                "red_flag": proto_cities[city]["red_flag"],
                "ab_ratio": proto_cities[city]["ab_ratio"],
                "protocol_files_scanned": proto_cities[city]["files_scanned"],
                "protocol_coverage": f"{proto_cities[city]['files_scanned']}/{proto_cities[city]['files_total']}",
            })

        if has_expo:
            entry.update({
                "exposure_score": expo_cities[city]["exposure_normalized"],
                "subversive_ratio": expo_cities[city]["subversive_ratio"],
                "subversive_budget": expo_cities[city]["subversive_budget"],
                "total_edu_budget": expo_cities[city]["total_budget"],
                "edu_deployments": expo_cities[city]["total_deployments"],
                "subversive_deployments": expo_cities[city]["subversive_deployments"],
            })

        # Combined score (only for cities with both)
        if has_proto and has_expo:
            entry["combined_score"] = compute_combined_score(proto_cities[city], expo_cities[city])
            entry["data_sources"] = "both"
        elif has_proto:
            entry["combined_score"] = None
            entry["data_sources"] = "protocols_only"
        else:
            entry["combined_score"] = None
            entry["data_sources"] = "education_only"

        merged.append(entry)

    # Sort by combined score (cities with both sources first, highest score first)
    both = [e for e in merged if e["data_sources"] == "both"]
    proto_only = [e for e in merged if e["data_sources"] == "protocols_only"]
    edu_only = [e for e in merged if e["data_sources"] == "education_only"]

    both.sort(key=lambda x: x["combined_score"], reverse=True)

    # Assign ranks
    for i, e in enumerate(both, 1):
        e["rank"] = i

    output = {
        "metadata": {
            "generated": "2026-02-12",
            "methodology": {
                "combined_score": "weighted: Pole B protocol signals (30%) + red flags (20%) + educational exposure (50%)",
                "pole_a": "Jewish/Zionist identity keywords per 10K chars in municipal protocols",
                "pole_b": "Progressive/critical pedagogy keywords per 10K chars in municipal protocols",
                "red_flags": "Institutional capture indicators (UNESCO, external consultants) per 10K chars",
                "exposure": "Budget-weighted subversive program ratio from Gefen marketplace",
            },
            "sources": {
                "protocols": str(PROOCOLS_FILE),
                "education": str(EXPOSURE_FILE),
            },
            "cities_with_both_sources": len(both),
            "cities_protocols_only": len(proto_only),
            "cities_education_only": len(edu_only),
        },
        "rankings": both,
        "protocols_only": proto_only,
        "education_only": edu_only,
    }

    os.makedirs(OUTPUT_JSON.parent, exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Merged {len(both)} cities with both sources")
    print(f"  + {len(proto_only)} protocols-only, {len(edu_only)} education-only")
    print(f"Output: {OUTPUT_JSON}")

    # Build site
    build_site(output)
    return output


def build_site(data):
    """Generate a static HTML page showing merged rankings."""

    both = data["rankings"]
    proto_only = data["protocols_only"]
    edu_only = data["education_only"]

    # Build table rows for combined rankings
    rows_html = ""
    for e in both:
        pole_a = e.get("pole_a", "—")
        pole_b = e.get("pole_b", "—")
        red_flag = e.get("red_flag", "—")
        exposure = e.get("exposure_score", "—")
        combined = e.get("combined_score", "—")
        sub_ratio = e.get("subversive_ratio", "—")
        coverage = e.get("protocol_coverage", "—")

        # Color coding based on combined score
        if combined != "—":
            if combined >= 50:
                color = "#ff4444"
            elif combined >= 30:
                color = "#ff8800"
            elif combined >= 15:
                color = "#ffcc00"
            else:
                color = "#44cc44"
        else:
            color = "#888"

        rows_html += f"""
        <tr>
            <td class="rank">{e.get('rank', '—')}</td>
            <td class="city">{e['city']}</td>
            <td class="score" style="color:{color};font-weight:bold">{combined}</td>
            <td>{exposure}%</td>
            <td>{sub_ratio}%</td>
            <td>{pole_b}</td>
            <td>{red_flag}</td>
            <td>{pole_a}</td>
            <td class="dim">{coverage}</td>
        </tr>"""

    # Partial-data rows
    partial_rows = ""
    for e in proto_only:
        partial_rows += f"""
        <tr class="partial">
            <td>—</td>
            <td class="city">{e['city']}</td>
            <td class="dim">פרוטוקולים בלבד</td>
            <td>—</td>
            <td>—</td>
            <td>{e.get('pole_b', '—')}</td>
            <td>{e.get('red_flag', '—')}</td>
            <td>{e.get('pole_a', '—')}</td>
            <td class="dim">{e.get('protocol_coverage', '—')}</td>
        </tr>"""
    for e in edu_only:
        partial_rows += f"""
        <tr class="partial">
            <td>—</td>
            <td class="city">{e['city']}</td>
            <td class="dim">חינוך בלבד</td>
            <td>{e.get('exposure_score', '—')}%</td>
            <td>{e.get('subversive_ratio', '—')}%</td>
            <td>—</td>
            <td>—</td>
            <td>—</td>
            <td>—</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>דירוג ערים — ציון משולב</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
            background: #0a0a0a;
            color: #e0e0e0;
            padding: 20px;
            direction: rtl;
        }}
        h1 {{
            text-align: center;
            margin: 20px 0 5px;
            font-size: 1.8em;
            color: #fff;
        }}
        .subtitle {{
            text-align: center;
            color: #888;
            margin-bottom: 30px;
            font-size: 0.95em;
        }}
        .method-box {{
            background: #1a1a2e;
            border: 1px solid #333;
            border-radius: 8px;
            padding: 20px;
            margin: 0 auto 30px;
            max-width: 900px;
        }}
        .method-box h3 {{
            color: #7eb8da;
            margin-bottom: 10px;
        }}
        .method-box ul {{
            list-style: none;
            padding: 0;
        }}
        .method-box li {{
            padding: 4px 0;
            color: #bbb;
        }}
        .method-box li strong {{
            color: #e0e0e0;
        }}
        .weight {{
            display: inline-block;
            background: #2a2a4a;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.85em;
            color: #7eb8da;
            margin-left: 8px;
        }}
        table {{
            width: 100%;
            max-width: 1100px;
            margin: 0 auto 40px;
            border-collapse: collapse;
        }}
        th {{
            background: #1a1a2e;
            color: #7eb8da;
            padding: 12px 8px;
            text-align: center;
            font-weight: 600;
            border-bottom: 2px solid #333;
            font-size: 0.85em;
        }}
        td {{
            padding: 10px 8px;
            text-align: center;
            border-bottom: 1px solid #222;
        }}
        tr:hover {{ background: #1a1a1a; }}
        .city {{ text-align: right; font-weight: 600; }}
        .rank {{ font-size: 1.2em; color: #7eb8da; }}
        .score {{ font-size: 1.1em; }}
        .dim {{ color: #666; font-size: 0.85em; }}
        .partial td {{ opacity: 0.5; }}
        .section-title {{
            text-align: center;
            color: #666;
            font-size: 0.9em;
            padding: 15px 0 5px;
            border-top: 1px solid #333;
        }}
        .legend {{
            display: flex;
            justify-content: center;
            gap: 20px;
            margin: 10px 0 25px;
            font-size: 0.85em;
        }}
        .legend span {{
            display: flex;
            align-items: center;
            gap: 5px;
        }}
        .dot {{
            width: 12px; height: 12px;
            border-radius: 50%;
            display: inline-block;
        }}
        .links {{
            text-align: center;
            margin: 30px 0;
        }}
        .links a {{
            color: #7eb8da;
            text-decoration: none;
            margin: 0 15px;
        }}
        .links a:hover {{ text-decoration: underline; }}
        footer {{
            text-align: center;
            color: #555;
            font-size: 0.8em;
            margin-top: 40px;
            padding: 20px 0;
            border-top: 1px solid #222;
        }}
        @media (max-width: 768px) {{
            body {{ padding: 10px; }}
            th, td {{ padding: 6px 4px; font-size: 0.8em; }}
            h1 {{ font-size: 1.3em; }}
        }}
    </style>
</head>
<body>
    <h1>דירוג ערים — ציון משולב</h1>
    <p class="subtitle">שילוב ניתוח פרוטוקולים עירוניים + חשיפה לתוכניות חינוך</p>

    <div class="method-box">
        <h3>מתודולוגיה</h3>
        <ul>
            <li><strong>ציון משולב</strong> = שקלול של שלושה מקורות מידע:</li>
            <li>• חשיפה חינוכית (תוכניות גפ"ן) <span class="weight">50%</span></li>
            <li>• אותות פרוגרסיביים בפרוטוקולים (Pole B) <span class="weight">30%</span></li>
            <li>• דגלים אדומים — שיתוף UNESCO, יועצים חיצוניים <span class="weight">20%</span></li>
            <li class="dim" style="margin-top:8px">Pole A (זהות יהודית/ציונית) מוצג לייחוס אך לא נכלל בציון המשולב</li>
        </ul>
    </div>

    <div class="legend">
        <span><span class="dot" style="background:#ff4444"></span> 50+ קריטי</span>
        <span><span class="dot" style="background:#ff8800"></span> 30-49 גבוה</span>
        <span><span class="dot" style="background:#ffcc00"></span> 15-29 בינוני</span>
        <span><span class="dot" style="background:#44cc44"></span> &lt;15 נמוך</span>
    </div>

    <table>
        <thead>
            <tr>
                <th>#</th>
                <th>עיר</th>
                <th>ציון משולב</th>
                <th>חשיפה חינוכית</th>
                <th>% תקציב חתרני</th>
                <th>Pole B</th>
                <th>דגלים אדומים</th>
                <th>Pole A (זהות)</th>
                <th>כיסוי פרוטוקולים</th>
            </tr>
        </thead>
        <tbody>
            {rows_html}
            <tr><td colspan="9" class="section-title">ערים עם מקור נתונים חלקי</td></tr>
            {partial_rows}
        </tbody>
    </table>

    <div class="links">
        <a href="merged_city_ranking.json" download>⬇ הורד JSON מלא</a>
        <a href="https://aosshalem-dev.github.io/educational-programs/">📊 ניתוח תוכניות חינוך</a>
    </div>

    <footer>
        נוצר: 2026-02-12 | פרויקט אלכסון — דירוג ערים<br>
        מקורות: ניתוח פרוטוקולים עירוניים (15 ערים) + ניתוח תוכניות גפ"ן (6,064 תוכניות, 20 ערים)
    </footer>
</body>
</html>"""

    os.makedirs(OUTPUT_HTML.parent, exist_ok=True)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Site built: {OUTPUT_HTML}")


if __name__ == "__main__":
    merge()
