"""
DNA Framework — Context Generator UI
======================================
Left: project cards + email inbox
Right: two distinct panels — project knowledge (top) + general reference (bottom)

Bookmark http://localhost:7890 in Chrome.

Usage:
    python context_ui.py              # start server
    pythonw context_ui.py             # start without console window
    python context_ui.py --port 8080  # custom port
"""

import hashlib
import http.server
import json
import os
import subprocess
import sys
import urllib.parse

PORT = 7890
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHEATSHEET = os.path.join(BASE_DIR, "dna", "cheatsheet.md")
CONTEXT_GENERATOR = os.path.join(BASE_DIR, "context_generator.py")
TOOLS_DIR = os.path.join(BASE_DIR, "dna", "nodes", "tools")
EMAIL_CACHE = os.path.join(BASE_DIR, "email", "email_cache.jsonl")
EMAIL_CACHE_PY = os.path.join(BASE_DIR, "email", "email_cache.py")
EMAIL_META = os.path.join(BASE_DIR, "email", "email_meta.json")


PROJECTS_DIR = os.path.join(BASE_DIR, "dna", "projects")


def load_project_urls():
    """Read deploy.url or top-level url from each project JSON."""
    urls = {}
    if not os.path.isdir(PROJECTS_DIR):
        return urls
    for fname in os.listdir(PROJECTS_DIR):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(PROJECTS_DIR, fname), "r", encoding="utf-8") as f:
                data = json.load(f)
            url = (data.get("deploy") or {}).get("url") or data.get("url")
            if url:
                urls[data.get("project_id", fname[:-5])] = url
        except (json.JSONDecodeError, OSError):
            continue
    return urls


def parse_tools():
    tools = []
    if not os.path.isdir(TOOLS_DIR):
        return tools
    for fname in sorted(os.listdir(TOOLS_DIR)):
        if not fname.endswith(".md"):
            continue
        name = fname[:-3]
        filepath = os.path.join(TOOLS_DIR, fname)
        desc = ""
        with open(filepath, "r", encoding="utf-8") as f:
            in_front = False
            for line in f:
                if line.strip() == "---":
                    in_front = not in_front
                    continue
                if not in_front and line.startswith("# "):
                    desc = line.strip("# \n")
                    break
        tools.append({
            "name": name,
            "description": desc or name,
            "type": "tool",
            "location": f"dna/nodes/tools/{fname}",
        })
    return tools


def parse_projects():
    projects = []
    if not os.path.exists(CHEATSHEET):
        return projects
    with open(CHEATSHEET, "r", encoding="utf-8") as f:
        content = f.read()

    in_table = False
    header_passed = False
    for line in content.split("\n"):
        if "## Active Projects" in line:
            in_table = True
            continue
        if in_table and line.startswith("##"):
            break
        if in_table and line.startswith("|"):
            if "Project" in line and ("What it is" in line or "Type" in line):
                continue
            if line.startswith("|---"):
                header_passed = True
                continue
            if header_passed:
                cols = [c.strip() for c in line.split("|")[1:-1]]
                if len(cols) >= 4:
                    projects.append({
                        "name": cols[0],
                        "description": cols[1],
                        "type": cols[2],
                        "location": cols[3],
                    })
    urls = load_project_urls()
    for p in projects:
        if p["name"] in urls:
            p["url"] = urls[p["name"]]
    return projects


def categorize_projects(projects):
    order = ["Web Apps", "Research & Sites", "Data & Backend", "Philosophical", "Tools"]
    categories = {k: [] for k in order}
    type_to_cat = {
        "web-app": "Web Apps",
        "research": "Research & Sites",
        "research+site": "Research & Sites",
        "data-tool": "Data & Backend",
        "backend": "Data & Backend",
        "telegram-bot": "Data & Backend",
        "philosophical": "Philosophical",
        "tool": "Tools",
    }
    for p in projects:
        base_type = p["type"].split("(")[0].strip().lower()
        cat = type_to_cat.get(base_type, "Web Apps")
        categories[cat].append(p)
    return {k: v for k, v in categories.items() if v}


def load_cached_emails(last=10):
    """Read emails from local cache. Instant, no IMAP."""
    emails = []
    if os.path.exists(EMAIL_CACHE):
        with open(EMAIL_CACHE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        emails.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    return emails[:last]


def email_cache_age():
    """Cache age in minutes, or None if no cache."""
    if not os.path.exists(EMAIL_CACHE):
        return None
    import time
    mtime = os.path.getmtime(EMAIL_CACHE)
    return round((time.time() - mtime) / 60, 1)


def email_id(message_id):
    """SHA-256 hash of message_id -> 10-char ID (matches internal_inbox.py scheme)."""
    raw = message_id or ""
    return hashlib.sha256(raw.encode()).hexdigest()[:10]


def load_email_meta():
    """Read email metadata JSON. Returns empty structure if missing."""
    if os.path.exists(EMAIL_META):
        try:
            with open(EMAIL_META, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"emails": {}, "sender_projects": {}}


def save_email_meta(meta):
    """Write email metadata JSON back to disk."""
    os.makedirs(os.path.dirname(EMAIL_META), exist_ok=True)
    with open(EMAIL_META, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def extract_sender(from_header):
    """Pull bare email address from 'Name <email>' format."""
    if "<" in from_header:
        return from_header.split("<")[1].rstrip(">").strip().lower()
    return from_header.strip().lower()


def load_constant_context():
    """Load the constant general reference (credentials + shared tools)."""
    if not os.path.exists(CHEATSHEET):
        return ""
    with open(CHEATSHEET, "r", encoding="utf-8") as f:
        content = f.read()
    lines = content.split("\n")
    result = []
    include = False
    for line in lines:
        if line.startswith("## "):
            section = line.strip("# ").strip()
            include = section in ("Credentials", "Shared Tools")
        if include:
            result.append(line)
    return "\n".join(result).strip()


def build_html(projects):
    all_items = projects + parse_tools()
    grouped = categorize_projects(all_items)
    project_names_js = json.dumps([p["name"] for p in projects])

    sections_html = ""
    for cat_name, cat_projects in grouped.items():
        cards = ""
        for p in cat_projects:
            link_html = ""
            if p.get("url"):
                url = p["url"]
                # Shorten URL for display: strip protocol, keep domain+path
                display = url.split("://", 1)[-1].lstrip("www.")
                link_html = f'\n                <a class="card-link" href="{url}" target="_blank" onclick="event.stopPropagation()">{display} ↗</a>'
            cards += f"""
            <div class="card" onclick="selectProject(this, '{p["name"]}')" title="{p["location"]}">
                <div class="card-name">
                    {p["name"]}
                    <span class="learn-badge" id="badge-{p["name"]}" style="display:none" onclick="event.stopPropagation(); learnProject('{p["name"]}')"></span>
                </div>
                <div class="card-desc">{p["description"]}</div>
                <span class="card-type">{p["type"]}</span>{link_html}
            </div>"""
        sections_html += f"""
        <section class="category">
            <h2>{cat_name}</h2>
            <div class="grid">{cards}
            </div>
        </section>"""

    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>DNA Context</title>
<style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
        background: #fff; color: #1f2328; min-height: 100vh;
    }
    .container { display: flex; height: 100vh; }

    /* Left panel — projects + emails */
    .panel-left {
        width: 380px; min-width: 200px;
        display: flex; flex-direction: column;
        border-right: none; background: #fff;
    }
    .projects-area { flex: 1; overflow-y: auto; padding: 1.2rem; }
    .email-area {
        height: 220px; min-height: 100px;
        border-top: 2px solid #d8dee4; overflow-y: auto; padding: 0.8rem 1.2rem;
        background: #fafbfc;
    }

    /* Drag handles */
    .drag-v {
        width: 5px; cursor: col-resize; background: #d8dee4;
        flex-shrink: 0; transition: background 0.15s;
    }
    .drag-v:hover, .drag-v.active { background: #0969da; }
    .drag-h {
        height: 5px; cursor: row-resize; background: #d8dee4;
        flex-shrink: 0; transition: background 0.15s;
    }
    .drag-h:hover, .drag-h.active { background: #0969da; }
    h1 { font-size: 1.2rem; font-weight: 600; margin-bottom: 0.2rem; }
    .subtitle { color: #656d76; font-size: 0.75rem; margin-bottom: 0.8rem; }
    .custom-row { display: flex; gap: 0.4rem; margin-bottom: 1rem; }
    .custom-row input {
        flex: 1; padding: 0.4rem 0.6rem; background: #fff;
        border: 1px solid #d0d7de; border-radius: 6px;
        color: #1f2328; font-size: 0.8rem; outline: none;
    }
    .custom-row input:focus { border-color: #0969da; box-shadow: 0 0 0 3px rgba(9,105,218,0.12); }
    .btn {
        padding: 0.4rem 0.8rem; background: #2da44e; color: #fff; border: none;
        border-radius: 6px; cursor: pointer; font-size: 0.8rem; font-weight: 500; white-space: nowrap;
    }
    .btn:hover { background: #218838; }
    .category { margin-bottom: 1rem; }
    .category h2 {
        font-size: 0.68rem; font-weight: 600; text-transform: uppercase;
        letter-spacing: 0.05em; color: #656d76; margin-bottom: 0.4rem;
        padding-bottom: 0.2rem; border-bottom: 1px solid #d8dee4;
    }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.4rem; }
    .card {
        background: #fff; border: 1px solid #d0d7de; border-radius: 6px;
        padding: 0.5rem 0.7rem; cursor: pointer;
        transition: border-color 0.15s, box-shadow 0.15s;
        display: flex; flex-direction: column; gap: 0.15rem;
    }
    .card:hover { border-color: #0969da; box-shadow: 0 1px 3px rgba(9,105,218,0.1); }
    .card.selected { border-color: #0969da; background: #ddf4ff; }
    .card-name { font-weight: 600; font-size: 0.8rem; }
    .card-desc { color: #656d76; font-size: 0.65rem; line-height: 1.25; }
    .card-type {
        display: inline-block; margin-top: auto; padding: 0.05rem 0.35rem;
        border-radius: 10px; font-size: 0.55rem; font-weight: 500; width: fit-content;
        background: #ddf4ff; color: #0969da;
    }
    .card-link {
        display: block; font-size: 0.58rem; color: #656d76;
        text-decoration: none; margin-top: 0.15rem;
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    .card-link:hover { color: #0969da; text-decoration: underline; }
    .learn-badge {
        display: inline-block; padding: 0.05rem 0.35rem;
        border-radius: 10px; font-size: 0.5rem; font-weight: 600;
        background: #8250df; color: #fff; cursor: pointer; margin-left: 0.3rem;
        vertical-align: middle;
    }
    .learn-badge:hover { background: #6e3fc7; }
    .action-bar {
        display: flex; gap: 0.4rem; margin-bottom: 0.8rem; flex-wrap: wrap;
    }
    .action-bar .btn-sm {
        padding: 0.3rem 0.6rem; font-size: 0.65rem; font-weight: 500;
        border: none; border-radius: 5px; cursor: pointer; color: #fff;
    }

    /* Email items */
    .email-header {
        font-size: 0.7rem; font-weight: 600; text-transform: uppercase;
        letter-spacing: 0.05em; color: #656d76; margin-bottom: 0.5rem;
    }
    .email-item {
        padding: 0.4rem 0; border-bottom: 1px solid #e8eaed; cursor: pointer;
        display: flex; align-items: flex-start; gap: 0.3rem;
    }
    .email-item:hover { background: #f0f4ff; margin: 0 -0.4rem; padding: 0.4rem; border-radius: 4px; }
    .email-item-content { flex: 1; min-width: 0; }
    .email-from { font-weight: 600; font-size: 0.72rem; }
    .email-subject { font-size: 0.68rem; color: #1f2328; }
    .email-date { font-size: 0.58rem; color: #8b949e; }
    .email-body-popup {
        display: none; position: fixed; top: 10%; left: 20%; width: 60%; max-height: 70%;
        background: #fff; border: 1px solid #d8dee4; border-radius: 8px;
        box-shadow: 0 8px 30px rgba(0,0,0,0.2); z-index: 200; overflow-y: auto; padding: 1.5rem;
    }
    .email-body-popup.show { display: block; }
    .email-body-popup h3 { font-size: 0.9rem; margin-bottom: 0.5rem; }
    .email-body-popup .meta { font-size: 0.7rem; color: #656d76; margin-bottom: 1rem; }
    .email-body-popup pre {
        font-family: 'Cascadia Code', 'Consolas', monospace;
        font-size: 0.72rem; white-space: pre-wrap; word-wrap: break-word;
    }
    .email-body-popup .close-btn {
        position: absolute; top: 0.5rem; right: 0.8rem; cursor: pointer;
        font-size: 1.2rem; color: #656d76; background: none; border: none;
    }
    .overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.3); z-index: 199; }
    .overlay.show { display: block; }

    /* Right panel — two distinct sections */
    .panel-right { flex: 1; display: flex; flex-direction: column; }

    .section-project {
        flex: 1; display: flex; flex-direction: column;
        min-height: 100px;
    }
    .section-general {
        height: 220px; min-height: 100px;
        display: flex; flex-direction: column;
    }
    .section-hdr {
        padding: 0.5rem 1rem; border-bottom: 1px solid #d8dee4;
        display: flex; align-items: center; gap: 0.5rem; background: #fff;
        flex-shrink: 0;
    }
    .section-hdr h2 { font-size: 0.85rem; font-weight: 600; flex: 1; }
    .section-hdr .meta { color: #656d76; font-size: 0.7rem; }
    .section-hdr.project-hdr { background: #f0f7ff; border-left: 3px solid #0969da; }
    .section-hdr.general-hdr { background: #f6f8fa; border-left: 3px solid #8b949e; }
    .section-content {
        flex: 1; overflow-y: auto; padding: 0.8rem 1rem; background: #f6f8fa;
    }
    .section-project .section-content { background: #fafcff; }
    .section-content pre {
        font-family: 'Cascadia Code', 'Consolas', 'SF Mono', monospace;
        font-size: 0.7rem; line-height: 1.45; white-space: pre-wrap; word-wrap: break-word;
        color: #1f2328; background: #fff; border: 1px solid #d8dee4;
        border-radius: 6px; padding: 0.8rem;
    }
    .section-content .placeholder {
        color: #656d76; text-align: center; padding: 2rem; font-size: 0.85rem;
    }
    .section-content .loading {
        color: #0969da; text-align: center; padding: 2rem; font-size: 0.85rem;
    }

    /* Toast */
    .toast {
        position: fixed; bottom: 2rem; left: 50%;
        transform: translateX(-50%) translateY(100px);
        background: #2da44e; color: #fff; padding: 0.65rem 1.3rem;
        border-radius: 8px; font-size: 0.85rem; opacity: 0;
        transition: transform 0.3s, opacity 0.3s; z-index: 100;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }
    .toast.show { transform: translateX(-50%) translateY(0); opacity: 1; }
    .toast.error { background: #cf222e; }

    /* Email tabs */
    .email-tabs {
        display: flex; gap: 0; margin-bottom: 0.4rem; border-bottom: 1px solid #d8dee4;
    }
    .email-tab {
        flex: 1; padding: 0.3rem 0.2rem; font-size: 0.6rem; font-weight: 600;
        background: none; border: none; border-bottom: 2px solid transparent;
        cursor: pointer; color: #656d76; text-align: center; transition: all 0.15s;
    }
    .email-tab:hover { color: #1f2328; }
    .email-tab.active { color: #0969da; border-bottom-color: #0969da; }
    .tab-count {
        display: inline-block; min-width: 14px; padding: 0 0.2rem;
        border-radius: 8px; font-size: 0.5rem; font-weight: 600;
        background: #e8eaed; color: #656d76; margin-left: 0.15rem;
    }
    .email-tab.active .tab-count { background: #ddf4ff; color: #0969da; }

    /* Email dealt-with indicator */
    .email-status {
        display: inline-flex; align-items: center; justify-content: center;
        width: 14px; height: 14px; border-radius: 50%;
        border: 2px solid #d0d7de; background: #fff; cursor: pointer;
        flex-shrink: 0; transition: all 0.15s; font-size: 0; margin-top: 0.15rem;
    }
    .email-status.dealt {
        background: #2da44e; border-color: #2da44e; color: #fff; font-size: 9px;
    }
    .email-status:hover { border-color: #0969da; }

    /* Email project badge */
    .email-project-badge {
        font-size: 0.52rem; padding: 0.05rem 0.3rem; border-radius: 8px;
        background: #ddf4ff; color: #0969da; margin-left: 0.3rem; font-weight: 500;
    }

    /* Email filter header */
    .email-filter-header {
        display: none; padding: 0.3rem 0.5rem; margin-bottom: 0.4rem;
        background: #ddf4ff; border-radius: 5px; font-size: 0.65rem;
        color: #0969da; font-weight: 600; align-items: center; gap: 0.3rem;
    }
    .email-filter-header.active { display: flex; }
    .email-filter-clear {
        margin-left: auto; cursor: pointer; font-size: 0.85rem;
        color: #656d76; background: none; border: none; line-height: 1;
    }
    .email-filter-clear:hover { color: #cf222e; }

    /* Popup controls */
    .popup-controls {
        display: flex; gap: 0.6rem; align-items: center; margin-bottom: 0.8rem;
        padding: 0.5rem 0; border-bottom: 1px solid #e8eaed; flex-wrap: wrap;
    }
    .popup-controls select {
        padding: 0.3rem 0.5rem; border: 1px solid #d0d7de; border-radius: 5px;
        font-size: 0.72rem; background: #fff; color: #1f2328; outline: none;
    }
    .popup-controls select:focus { border-color: #0969da; }
    .popup-controls .btn-dealt {
        padding: 0.3rem 0.7rem; font-size: 0.68rem; border: 1px solid #d0d7de;
        border-radius: 5px; cursor: pointer; background: #fff; color: #1f2328;
        font-weight: 500; transition: all 0.15s;
    }
    .popup-controls .btn-dealt.active {
        background: #2da44e; color: #fff; border-color: #2da44e;
    }
    .popup-controls label { font-size: 0.68rem; color: #656d76; font-weight: 600; }
</style>
</head>
<body>
<div class="container">
    <div class="panel-left">
        <div class="projects-area">
            <h1>DNA Context</h1>
            <div class="action-bar">
                <button class="btn-sm" style="background:#0969da;font-size:0.72rem;padding:0.35rem 0.8rem" onclick="runReflection()" title="Full reflection: categorize + process + extract insights">Reflection</button>
                <button class="btn-sm" style="background:#8250df" onclick="runLearner()" title="Generate learner context for all unprocessed sessions">Learner</button>
                <button class="btn-sm" style="background:#bf8700" onclick="runCategorize()" title="Categorize uncategorized sessions into projects">Categorize</button>
                <span id="learnSummary" style="font-size:0.6rem;color:#656d76;line-height:1.8"></span>
            </div>
            <div class="custom-row">
                <input type="text" id="customTask" placeholder="Custom task description..."
                       onkeydown="if(event.key==='Enter') generateCustom()">
                <button class="btn" onclick="generateCustom()">Generate</button>
            </div>
            """ + sections_html + """
        </div>
        <div class="drag-h" id="dragHL"></div>
        <div class="email-area">
            <div class="email-header" style="display:flex;align-items:center;justify-content:space-between">
                <span>Emails</span>
                <span id="cacheAge" style="font-weight:400;font-size:0.6rem;color:#8b949e"></span>
                <button onclick="refreshEmails()" style="font-size:0.55rem;padding:0.15rem 0.5rem;background:#0969da;color:#fff;border:none;border-radius:4px;cursor:pointer">Refresh</button>
            </div>
            <div class="email-tabs">
                <button class="email-tab active" data-tab="uncategorized" onclick="switchEmailTab('uncategorized')">Uncategorized <span class="tab-count" id="countUncategorized">0</span></button>
                <button class="email-tab" data-tab="categorized" onclick="switchEmailTab('categorized')">Categorized <span class="tab-count" id="countCategorized">0</span></button>
                <button class="email-tab" data-tab="processed" onclick="switchEmailTab('processed')">Processed <span class="tab-count" id="countProcessed">0</span></button>
            </div>
            <div class="email-filter-header" id="emailFilterHeader">
                <span id="emailFilterLabel">Emails for project</span>
                <button class="email-filter-clear" onclick="clearEmailFilter()">&times;</button>
            </div>
            <div id="emailList"><span class="loading" style="padding:1rem;font-size:0.75rem">Loading emails...</span></div>
        </div>
    </div>

    <div class="drag-v" id="dragV"></div>
    <div class="panel-right">
        <div class="section-project" id="sectionProject">
            <div class="section-hdr project-hdr">
                <h2 id="projectTitle">Project Knowledge</h2>
                <span class="meta" id="projectMeta"></span>
                <button class="btn" id="copyBtn" onclick="copyContext()" style="display:none">Copy</button>
                <button class="btn" id="copyOpenBtn" onclick="copyAndOpen()" style="display:none;background:#8250df">Copy & Open Terminal</button>
            </div>
            <div class="section-content" id="projectBody">
                <div class="placeholder">Select a project to load its context</div>
            </div>
        </div>
        <div class="drag-h" id="dragH"></div>
        <div class="section-general" id="sectionGeneral">
            <div class="section-hdr general-hdr">
                <h2>General Reference</h2>
                <span class="meta" id="generalMeta"></span>
            </div>
            <div class="section-content" id="generalBody">
                <div class="loading">Loading...</div>
            </div>
        </div>
    </div>
</div>

<div class="overlay" id="overlay" onclick="closeEmailPopup()"></div>
<div class="email-body-popup" id="emailPopup">
    <button class="close-btn" onclick="closeEmailPopup()">&times;</button>
    <h3 id="popupSubject"></h3>
    <div class="meta" id="popupMeta"></div>
    <div class="popup-controls">
        <label>Project:</label>
        <select id="popupProject" onchange="setEmailProject(this.value)"></select>
        <button class="btn-dealt" id="popupDealt" onclick="toggleDealtFromPopup()">Mark dealt</button>
    </div>
    <pre id="popupBody"></pre>
</div>

<div class="toast" id="toast"></div>

<script>
    const PROJECT_NAMES = """ + project_names_js + """;
    let currentContext = '';
    let emailCache = [];
    let emailFilterProject = null;
    let currentPopupIdx = null;
    let currentEmailTab = 'uncategorized';

    function showToast(msg, isError) {
        const t = document.getElementById('toast');
        t.textContent = msg;
        t.className = 'toast show' + (isError ? ' error' : '');
        setTimeout(() => t.className = 'toast', 2500);
    }

    function esc(s) {
        const d = document.createElement('div');
        d.textContent = s || '';
        return d.innerHTML;
    }

    // === GENERAL REFERENCE (loads on page start) ===
    async function loadConstant() {
        try {
            const resp = await fetch('/constant');
            const data = await resp.json();
            const el = document.getElementById('generalBody');
            const meta = document.getElementById('generalMeta');
            if (data.content) {
                el.innerHTML = '<pre>' + esc(data.content) + '</pre>';
                meta.textContent = data.content.split('\\n').length + ' lines';
            } else {
                el.innerHTML = '<div class="placeholder">No general reference loaded</div>';
            }
        } catch(e) {
            document.getElementById('generalBody').innerHTML =
                '<div class="placeholder" style="color:#cf222e">Failed to load</div>';
        }
    }

    // === EMAILS (loads on page start) ===
    async function loadEmails() {
        try {
            const resp = await fetch('/emails?last=15');
            const data = await resp.json();
            const el = document.getElementById('emailList');
            const ageEl = document.getElementById('cacheAge');
            if (data.error) {
                el.innerHTML = '<div style="font-size:0.7rem;color:#cf222e">' + esc(data.error) + '</div>';
                return;
            }
            if (data.cache_age_min !== null) {
                const age = data.cache_age_min;
                ageEl.textContent = age < 60 ? Math.round(age) + 'm ago' : Math.round(age/60) + 'h ago';
            }
            emailCache = data.emails || [];
            renderEmailList();
        } catch(e) {
            document.getElementById('emailList').innerHTML =
                '<div style="font-size:0.7rem;color:#cf222e">Could not load emails</div>';
        }
    }

    async function refreshEmails() {
        const el = document.getElementById('emailList');
        el.innerHTML = '<div class="loading" style="padding:1rem;font-size:0.75rem">Fetching from IMAP... (may take ~45s)</div>';
        try {
            const resp = await fetch('/emails/refresh');
            const data = await resp.json();
            if (data.error) {
                el.innerHTML = '<div style="font-size:0.7rem;color:#cf222e">' + esc(data.error) + '</div>';
                return;
            }
            showToast('Email cache refreshed');
            await loadEmails();
        } catch(e) {
            el.innerHTML = '<div style="font-size:0.7rem;color:#cf222e">Refresh failed: ' + esc(e.message) + '</div>';
        }
    }

    function showEmail(idx) {
        const e = emailCache[idx];
        if (!e) return;
        currentPopupIdx = idx;
        document.getElementById('popupSubject').textContent = e.subject;
        document.getElementById('popupMeta').textContent = e.from + ' — ' + e.date;
        document.getElementById('popupBody').textContent = e.body_preview || '(no preview available)';
        // Populate project dropdown
        const sel = document.getElementById('popupProject');
        const senderProj = e.sender_project;
        let opts = '<option value="">(none)</option>';
        const ordered = [...PROJECT_NAMES];
        if (senderProj && ordered.includes(senderProj)) {
            ordered.splice(ordered.indexOf(senderProj), 1);
            ordered.unshift(senderProj);
        }
        ordered.forEach(p => {
            const hint = (p === senderProj && p !== e.project) ? ' (sender default)' : '';
            const selected = p === e.project ? ' selected' : '';
            opts += '<option value="' + esc(p) + '"' + selected + '>' + esc(p + hint) + '</option>';
        });
        sel.innerHTML = opts;
        // Dealt button state
        const dealtBtn = document.getElementById('popupDealt');
        if (e.dealt_with) {
            dealtBtn.textContent = 'Dealt with \\u2713';
            dealtBtn.classList.add('active');
        } else {
            dealtBtn.textContent = 'Mark dealt';
            dealtBtn.classList.remove('active');
        }
        document.getElementById('emailPopup').classList.add('show');
        document.getElementById('overlay').classList.add('show');
    }

    function closeEmailPopup() {
        document.getElementById('emailPopup').classList.remove('show');
        document.getElementById('overlay').classList.remove('show');
    }

    // === PROJECT CONTEXT ===
    async function generateContext(task) {
        const body = document.getElementById('projectBody');
        const title = document.getElementById('projectTitle');
        const meta = document.getElementById('projectMeta');
        const copyBtn = document.getElementById('copyBtn');

        body.innerHTML = '<div class="loading">Generating context...</div>';
        title.textContent = 'Generating...';
        meta.textContent = '';
        copyBtn.style.display = 'none';
        document.getElementById('copyOpenBtn').style.display = 'none';

        try {
            const resp = await fetch('/generate?task=' + encodeURIComponent(task));
            const data = await resp.json();
            if (data.error) {
                body.innerHTML = '<div class="placeholder" style="color:#cf222e">Error: ' + esc(data.error) + '</div>';
                title.textContent = 'Error';
                return;
            }
            currentContext = data.context;
            const marker = '\\n===GENERAL FRAMEWORK===\\n';
            const idx = data.context.indexOf(marker);
            if (idx >= 0) {
                const projectCtx = data.context.substring(0, idx).trim();
                body.innerHTML = '<pre>' + esc(projectCtx) + '</pre>';
                meta.textContent = projectCtx.split('\\n').length + ' lines';
            } else {
                body.innerHTML = '<pre>' + esc(data.context) + '</pre>';
                meta.textContent = data.lines + ' lines';
            }
            title.textContent = 'Project Knowledge';
            copyBtn.style.display = '';
            document.getElementById('copyOpenBtn').style.display = '';
        } catch(e) {
            body.innerHTML = '<div class="placeholder" style="color:#cf222e">Failed: ' + esc(e.message) + '</div>';
            title.textContent = 'Error';
        }
    }

    function selectProject(card, name) {
        document.querySelectorAll('.card.selected').forEach(c => c.classList.remove('selected'));
        card.classList.add('selected');
        generateContext('work on ' + name + ' project');
        filterEmailsByProject(name);
    }

    async function generateCustom() {
        const input = document.getElementById('customTask');
        const task = input.value.trim();
        if (!task) return;
        document.querySelectorAll('.card.selected').forEach(c => c.classList.remove('selected'));
        await generateContext(task);
    }

    async function copyContext() {
        if (!currentContext) {
            showToast('No context to copy', true);
            return;
        }
        try {
            await navigator.clipboard.writeText(currentContext);
            const lines = currentContext.split('\\n').length;
            showToast('Copied to clipboard (' + lines + ' lines)');
        } catch(e) {
            showToast('Clipboard failed: ' + e.message, true);
        }
    }

    async function copyAndOpen() {
        if (!currentContext) {
            showToast('No context to copy', true);
            return;
        }
        try {
            await navigator.clipboard.writeText(currentContext);
            showToast('Copied! Opening terminal...');
            await fetch('/open-terminal');
        } catch(e) {
            showToast('Failed: ' + e.message, true);
        }
    }

    // === EMAIL RENDERING + METADATA ===
    function tabFilter(e) {
        if (currentEmailTab === 'uncategorized') return !e.project && !e.dealt_with;
        if (currentEmailTab === 'categorized') return !!e.project && !e.dealt_with;
        if (currentEmailTab === 'processed') return !!e.dealt_with;
        return true;
    }

    function updateTabCounts() {
        const uncat = emailCache.filter(e => !e.project && !e.dealt_with).length;
        const cat = emailCache.filter(e => !!e.project && !e.dealt_with).length;
        const proc = emailCache.filter(e => !!e.dealt_with).length;
        document.getElementById('countUncategorized').textContent = uncat;
        document.getElementById('countCategorized').textContent = cat;
        document.getElementById('countProcessed').textContent = proc;
    }

    function switchEmailTab(tab) {
        currentEmailTab = tab;
        document.querySelectorAll('.email-tab').forEach(t => {
            t.classList.toggle('active', t.dataset.tab === tab);
        });
        renderEmailList();
    }

    function renderEmailList() {
        const el = document.getElementById('emailList');
        updateTabCounts();
        if (emailCache.length === 0) {
            el.innerHTML = '<div style="font-size:0.7rem;color:#656d76">No emails in cache. Click Refresh.</div>';
            return;
        }
        let filtered = emailCache.filter(tabFilter);
        if (emailFilterProject) {
            filtered = filtered.filter(e => e.project === emailFilterProject);
        }
        if (filtered.length === 0) {
            const labels = {uncategorized: 'uncategorized', categorized: 'categorized', processed: 'processed'};
            el.innerHTML = '<div style="font-size:0.7rem;color:#656d76">No ' + labels[currentEmailTab] + ' emails' + (emailFilterProject ? ' for ' + emailFilterProject : '') + '.</div>';
            return;
        }
        el.innerHTML = filtered.map(e => {
            const ri = emailCache.indexOf(e);
            const cls = e.dealt_with ? 'email-status dealt' : 'email-status';
            const tick = e.dealt_with ? '\\u2713' : '';
            const badge = e.project ? '<span class="email-project-badge">' + esc(e.project) + '</span>' : '';
            return '<div class="email-item">' +
                '<span class="' + cls + '" onclick="event.stopPropagation(); toggleDealt(' + ri + ')">' + tick + '</span>' +
                '<div class="email-item-content" onclick="showEmail(' + ri + ')">' +
                '<div class="email-from">' + esc(e.from_short) + badge + '</div>' +
                '<div class="email-subject">' + esc(e.subject) + '</div>' +
                '<div class="email-date">' + esc(e.date_short) + '</div>' +
                '</div></div>';
        }).join('');
    }

    async function toggleDealt(idx) {
        const e = emailCache[idx];
        if (!e) return;
        const newState = !e.dealt_with;
        try {
            await fetch('/email/dealt', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({id: e.id, message_id: e.message_id, dealt_with: newState})
            });
            e.dealt_with = newState;
            renderEmailList();
            if (currentPopupIdx === idx) {
                const btn = document.getElementById('popupDealt');
                if (newState) { btn.textContent = 'Dealt with \\u2713'; btn.classList.add('active'); }
                else { btn.textContent = 'Mark dealt'; btn.classList.remove('active'); }
            }
        } catch(err) { showToast('Failed to update', true); }
    }

    function toggleDealtFromPopup() {
        if (currentPopupIdx !== null) toggleDealt(currentPopupIdx);
    }

    async function setEmailProject(project) {
        const e = emailCache[currentPopupIdx];
        if (!e) return;
        try {
            await fetch('/email/project', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({id: e.id, message_id: e.message_id, project: project || null, sender: e.sender})
            });
            e.project = project || null;
            if (project) e.sender_project = project;
            renderEmailList();
            showToast(project ? 'Assigned to ' + project : 'Project removed');
        } catch(err) { showToast('Failed to set project', true); }
    }

    function filterEmailsByProject(name) {
        emailFilterProject = name;
        document.getElementById('emailFilterLabel').textContent = 'Emails for ' + name;
        document.getElementById('emailFilterHeader').classList.add('active');
        switchEmailTab('categorized');
    }

    function clearEmailFilter() {
        emailFilterProject = null;
        document.getElementById('emailFilterHeader').classList.remove('active');
        renderEmailList();
    }

    // === RESIZABLE PANELS ===
    (function() {
        const dragV = document.getElementById('dragV');
        const dragH = document.getElementById('dragH');
        const dragHL = document.getElementById('dragHL');
        const panelLeft = document.querySelector('.panel-left');
        const projectsArea = document.querySelector('.projects-area');
        const emailArea = document.querySelector('.email-area');
        const sectionProject = document.getElementById('sectionProject');
        const sectionGeneral = document.getElementById('sectionGeneral');
        const panelRight = document.querySelector('.panel-right');

        let dragging = null;

        dragV.addEventListener('mousedown', (e) => {
            dragging = 'v'; dragV.classList.add('active');
            e.preventDefault();
        });
        dragH.addEventListener('mousedown', (e) => {
            dragging = 'h'; dragH.classList.add('active');
            e.preventDefault();
        });
        dragHL.addEventListener('mousedown', (e) => {
            dragging = 'hl'; dragHL.classList.add('active');
            e.preventDefault();
        });

        document.addEventListener('mousemove', (e) => {
            if (!dragging) return;
            if (dragging === 'v') {
                const w = Math.max(200, Math.min(e.clientX, window.innerWidth - 300));
                panelLeft.style.width = w + 'px';
            } else if (dragging === 'h') {
                const rect = panelRight.getBoundingClientRect();
                const y = e.clientY - rect.top;
                const total = rect.height - 5;
                const projH = Math.max(100, Math.min(y, total - 100));
                sectionProject.style.flex = 'none';
                sectionProject.style.height = projH + 'px';
                sectionGeneral.style.flex = 'none';
                sectionGeneral.style.height = (total - projH) + 'px';
            } else if (dragging === 'hl') {
                const rect = panelLeft.getBoundingClientRect();
                const y = e.clientY - rect.top;
                const total = rect.height - 5;
                const projH = Math.max(100, Math.min(y, total - 100));
                projectsArea.style.flex = 'none';
                projectsArea.style.height = projH + 'px';
                emailArea.style.flex = 'none';
                emailArea.style.height = (total - projH) + 'px';
            }
        });

        document.addEventListener('mouseup', () => {
            if (dragging) {
                dragV.classList.remove('active');
                dragH.classList.remove('active');
                dragHL.classList.remove('active');
                dragging = null;
            }
        });
    })();

    // === LEARNER ===
    async function showInProjectPanel(title_text, fetchUrl, metaLabel) {
        const body = document.getElementById('projectBody');
        const title = document.getElementById('projectTitle');
        const meta = document.getElementById('projectMeta');
        const copyBtn = document.getElementById('copyBtn');

        body.innerHTML = '<div class="loading">Loading...</div>';
        title.textContent = title_text;
        meta.textContent = '';
        copyBtn.style.display = 'none';
        document.getElementById('copyOpenBtn').style.display = 'none';
        document.querySelectorAll('.card.selected').forEach(c => c.classList.remove('selected'));

        try {
            const resp = await fetch(fetchUrl);
            const data = await resp.json();
            if (data.error) {
                body.innerHTML = '<div class="placeholder" style="color:#cf222e">' + esc(data.error) + '</div>';
                return;
            }
            currentContext = data.context;
            body.innerHTML = '<pre>' + esc(data.context) + '</pre>';
            meta.textContent = metaLabel ? (data[metaLabel] || '') : '';
            title.textContent = title_text;
            copyBtn.style.display = '';
            document.getElementById('copyOpenBtn').style.display = '';
        } catch(e) {
            body.innerHTML = '<div class="placeholder" style="color:#cf222e">' + esc(e.message) + '</div>';
        }
    }

    function runLearner() {
        showInProjectPanel('Learner Context', '/learner', 'unprocessed_label');
    }

    function runCategorize() {
        showInProjectPanel('Categorize Sessions', '/categorize-context', 'uncategorized_label');
    }

    function runReflection() {
        showInProjectPanel('Reflection Session', '/reflection', 'reflection_label');
    }

    function learnProject(name) {
        showInProjectPanel('Learn: ' + name, '/learner?project=' + encodeURIComponent(name), 'unprocessed_label');
    }

    // === LEARN BADGES (load on start) ===
    async function loadLearnBadges() {
        try {
            const resp = await fetch('/project-counts');
            const data = await resp.json();
            const summary = [];
            for (const [proj, count] of Object.entries(data.counts || {})) {
                if (proj === '_uncategorized') {
                    summary.push(count + ' uncategorized');
                    continue;
                }
                const badge = document.getElementById('badge-' + proj);
                if (badge && count > 0) {
                    badge.textContent = count + ' unlearned';
                    badge.style.display = '';
                }
            }
            const total = Object.values(data.counts || {}).reduce((a,b) => a+b, 0);
            const el = document.getElementById('learnSummary');
            if (el && total > 0) {
                const uncat = data.counts._uncategorized || 0;
                el.textContent = total + ' unprocessed' + (uncat ? ' (' + uncat + ' uncategorized)' : '');
            }
        } catch(e) {}
    }

    // === INIT ===
    loadConstant();
    loadEmails();
    loadLearnBadges();
</script>
</body>
</html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/" or parsed.path == "":
            projects = parse_projects()
            html = build_html(projects)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))

        elif parsed.path == "/constant":
            content = load_constant_context()
            self._json_response({"content": content})

        elif parsed.path == "/generate":
            params = urllib.parse.parse_qs(parsed.query)
            task = params.get("task", [""])[0]
            if not task:
                self._json_response({"error": "No task provided"}, 400)
                return
            try:
                result = subprocess.run(
                    [sys.executable, CONTEXT_GENERATOR, task],
                    capture_output=True, text=True, timeout=30,
                    cwd=BASE_DIR
                )
                if result.returncode != 0:
                    self._json_response({"error": result.stderr[:500]}, 500)
                    return
                context = result.stdout
                lines = len(context.split("\n"))
                self._json_response({"context": context, "lines": lines})
            except subprocess.TimeoutExpired:
                self._json_response({"error": "Generation timed out (30s)"}, 500)
            except Exception as e:
                self._json_response({"error": str(e)}, 500)

        elif parsed.path == "/emails":
            params = urllib.parse.parse_qs(parsed.query)
            last = int(params.get("last", ["10"])[0])
            try:
                raw = load_cached_emails(last)
                age = email_cache_age()
                meta = load_email_meta()
                emails = []
                for e in raw:
                    from_addr = e.get("from", "")
                    from_short = from_addr.split("<")[0].strip().strip('"') or from_addr
                    date = e.get("date", "")
                    msg_id = e.get("message_id", "")
                    eid = email_id(msg_id)
                    sender = extract_sender(from_addr)
                    em = meta.get("emails", {}).get(eid, {})
                    emails.append({
                        "from": from_addr,
                        "from_short": from_short,
                        "subject": e.get("subject", "(no subject)"),
                        "date": date,
                        "date_short": date[:16] if date else "",
                        "body_preview": e.get("body_preview", ""),
                        "message_id": msg_id,
                        "id": eid,
                        "dealt_with": em.get("dealt_with", False),
                        "project": em.get("project", None),
                        "sender": sender,
                        "sender_project": meta.get("sender_projects", {}).get(sender, None),
                    })
                self._json_response({"emails": emails, "cache_age_min": age})
            except Exception as e:
                self._json_response({"error": str(e)}, 500)

        elif parsed.path == "/emails/refresh":
            # Run IMAP fetch in subprocess, save to cache
            try:
                result = subprocess.run(
                    [sys.executable, EMAIL_CACHE_PY, "refresh", "--last", "20"],
                    capture_output=True, text=True, timeout=60,
                    cwd=BASE_DIR
                )
                if result.returncode != 0:
                    self._json_response({"error": result.stderr[:300]}, 500)
                    return
                self._json_response({"ok": True, "message": result.stdout.strip()})
            except subprocess.TimeoutExpired:
                self._json_response({"error": "IMAP refresh timed out (60s)"}, 500)
            except Exception as e:
                self._json_response({"error": str(e)}, 500)

        elif parsed.path == "/learner":
            params = urllib.parse.parse_qs(parsed.query)
            project = params.get("project", [None])[0]
            try:
                learner_py = os.path.join(BASE_DIR, "learner.py")
                cmd = [sys.executable, learner_py, "context"]
                if project:
                    cmd += ["--project", project]
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=15, cwd=BASE_DIR
                )
                if result.returncode != 0:
                    self._json_response({"error": result.stderr[:300]}, 500)
                    return
                label = f"unprocessed for {project}" if project else "unprocessed sessions"
                self._json_response({
                    "context": result.stdout,
                    "unprocessed_label": label,
                })
            except Exception as e:
                self._json_response({"error": str(e)}, 500)

        elif parsed.path == "/categorize-context":
            try:
                learner_py = os.path.join(BASE_DIR, "learner.py")
                result = subprocess.run(
                    [sys.executable, learner_py, "categorize-context"],
                    capture_output=True, text=True, timeout=15, cwd=BASE_DIR
                )
                if result.returncode != 0:
                    self._json_response({"error": result.stderr[:300]}, 500)
                    return
                self._json_response({
                    "context": result.stdout,
                    "uncategorized_label": "uncategorized sessions",
                })
            except Exception as e:
                self._json_response({"error": str(e)}, 500)

        elif parsed.path == "/project-counts":
            try:
                learner_py = os.path.join(BASE_DIR, "learner.py")
                result = subprocess.run(
                    [sys.executable, learner_py, "project-counts"],
                    capture_output=True, text=True, timeout=10, cwd=BASE_DIR
                )
                if result.returncode != 0:
                    self._json_response({"error": result.stderr[:300]}, 500)
                    return
                counts = json.loads(result.stdout)
                self._json_response({"counts": counts})
            except Exception as e:
                self._json_response({"error": str(e)}, 500)

        elif parsed.path == "/open-terminal":
            # Open a new command window with context copied to clipboard
            try:
                subprocess.Popen(
                    ["cmd.exe", "/c", "start", "cmd.exe", "/k",
                     "echo Context copied. Paste into: claude && cd /d C:\\Users\\User"],
                    cwd="C:\\Users\\User"
                )
                self._json_response({"ok": True})
            except Exception as e:
                self._json_response({"error": str(e)}, 500)

        elif parsed.path == "/reflection":
            try:
                learner_py = os.path.join(BASE_DIR, "learner.py")
                learner_prompt_path = os.path.join(BASE_DIR, "learner_prompt.md")
                # Get project counts
                counts_result = subprocess.run(
                    [sys.executable, learner_py, "project-counts"],
                    capture_output=True, text=True, timeout=10, cwd=BASE_DIR
                )
                counts = {}
                if counts_result.returncode == 0:
                    counts = json.loads(counts_result.stdout)
                uncategorized = counts.pop("_uncategorized", 0)
                total = sum(counts.values()) + uncategorized
                parts = ["# Reflection Session\n"]
                parts.append(f"Total unprocessed: {total} sessions\n")
                # Step 1: Categorize
                if uncategorized > 0:
                    parts.append(f"## Step 1: Categorize ({uncategorized} uncategorized sessions)\n")
                    cat_result = subprocess.run(
                        [sys.executable, learner_py, "categorize-context"],
                        capture_output=True, text=True, timeout=15, cwd=BASE_DIR
                    )
                    if cat_result.returncode == 0:
                        parts.append(cat_result.stdout)
                else:
                    parts.append("## Step 1: Categorize\nAll sessions categorized. Skip to Step 2.\n")
                # Step 2: Process per project
                parts.append("\n## Step 2: Process & Extract Insights\n")
                project_sessions = {k: v for k, v in counts.items() if v > 0}
                if project_sessions:
                    parts.append("Launch parallel Sonnet agents per project. Each agent should:\n")
                    parts.append("1. Read session transcripts (use `grep -a '\"type\":\"human\"'` if files are large)")
                    parts.append("2. Look for corrections, failures, discoveries, decisions")
                    parts.append("3. Write insights to DNA nodes: `## Title (added DATE, source: session ID)`")
                    parts.append("4. Mark processed: `python Dropbox/persistent-team/learner.py mark <session_id>`\n")
                    parts.append("### Unprocessed counts:")
                    for proj, count in sorted(project_sessions.items()):
                        parts.append(f"- **{proj}**: {count} sessions")
                else:
                    parts.append("No unprocessed sessions remaining.\n")
                # Step 3: Email summary
                parts.append("\n## Step 3: Email Summary")
                parts.append("After writing insights, compile all DNA changes and email a summary to aos.shalem@gmail.com.")
                parts.append("Use: `python Dropbox/persistent-team/email/send.py 'aos.shalem@gmail.com' 'DNA Reflection Summary' 'body'`\n")
                # Reference
                if os.path.exists(learner_prompt_path):
                    with open(learner_prompt_path, "r", encoding="utf-8") as f:
                        parts.append("\n## Reference: Learner Workflow\n")
                        parts.append(f.read())
                context = "\n".join(parts)
                label = f"{total} sessions to process"
                self._json_response({"context": context, "reflection_label": label})
            except Exception as e:
                self._json_response({"error": str(e)}, 500)

        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self._json_response({"error": "Invalid JSON"}, 400)
            return

        if parsed.path == "/email/dealt":
            msg_id = data.get("message_id", "")
            eid = data.get("id") or email_id(msg_id)
            dealt = data.get("dealt_with", True)
            meta = load_email_meta()
            if eid not in meta["emails"]:
                meta["emails"][eid] = {}
            meta["emails"][eid]["dealt_with"] = dealt
            if dealt:
                from datetime import datetime
                meta["emails"][eid]["dealt_at"] = datetime.now().isoformat()
            else:
                meta["emails"][eid].pop("dealt_at", None)
            save_email_meta(meta)
            self._json_response({"ok": True, "id": eid, "dealt_with": dealt})

        elif parsed.path == "/email/project":
            msg_id = data.get("message_id", "")
            eid = data.get("id") or email_id(msg_id)
            project = data.get("project") or None
            sender = data.get("sender", "")
            meta = load_email_meta()
            if eid not in meta["emails"]:
                meta["emails"][eid] = {}
            meta["emails"][eid]["project"] = project
            if sender and project:
                meta["sender_projects"][sender] = project
            save_email_meta(meta)
            self._json_response({"ok": True, "id": eid, "project": project})

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
        pass


def main():
    port = PORT
    if "--port" in sys.argv:
        idx = sys.argv.index("--port")
        if idx + 1 < len(sys.argv):
            port = int(sys.argv[idx + 1])

    server = http.server.HTTPServer(("127.0.0.1", port), Handler)
    print(f"DNA Context UI running at http://localhost:{port}")
    print("Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()


if __name__ == "__main__":
    main()
