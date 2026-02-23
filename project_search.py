"""
DNA Framework — Project Search
================================
Input:  free-text query string
Output: JSON with auto-matched project or ranked candidates

Scoring:
  100  Exact project_id match
   80  Alias substring match
   60  project_id substring in query
   10  Per tag word overlap
   40  Category match
    1  Per description word overlap (capped at 15)

Zero LLM cost. Pure string matching.
"""

import json
import os
import re
import sys

PROJECTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dna", "projects")

STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "is", "it", "my", "that", "this", "was", "are",
    "be", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "work", "project", "app", "open", "thing", "about", "like",
}


def tokenize(text):
    return set(re.findall(r'[\w\u0590-\u05FF]+', text.lower()))


def load_all_projects():
    projects = []
    if not os.path.isdir(PROJECTS_DIR):
        return projects
    for fname in os.listdir(PROJECTS_DIR):
        if fname.endswith(".json"):
            fpath = os.path.join(PROJECTS_DIR, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                projects.append(json.load(f))
    return projects


def search(query):
    projects = load_all_projects()
    query_lower = query.lower().strip()
    query_words = tokenize(query)
    content_words = query_words - STOP_WORDS

    results = []

    for proj in projects:
        pid = proj.get("project_id", "")
        score = 0

        # Tier 1: Exact project_id match
        normalized = query_lower.replace(" ", "-")
        normalized_us = query_lower.replace(" ", "_")
        if query_lower == pid.lower() or normalized == pid.lower() or normalized_us == pid.lower():
            score += 100

        # Tier 2: Alias match
        for alias in proj.get("aliases", []):
            if alias.lower() in query_lower or query_lower in alias.lower():
                score += 80
                break

        # Tier 3: project_id substring
        if score < 100 and pid.lower() in query_lower:
            score += 60

        # Tier 4: Tag overlap
        tags = set(proj.get("tags", []))
        tag_overlap = content_words & tags
        score += len(tag_overlap) * 10

        # Tier 5: Category match
        category = proj.get("category", "").lower()
        if category and category in content_words:
            score += 40

        # Tier 6: Description word overlap
        desc_words = tokenize(proj.get("description", "")) - STOP_WORDS
        desc_overlap = content_words & desc_words
        score += min(len(desc_overlap), 15)

        if score > 0:
            results.append({
                "project_id": pid,
                "score": score,
                "description": proj.get("description", ""),
            })

    results.sort(key=lambda r: (-r["score"], r["project_id"]))

    if not results:
        return {"match": None, "candidates": []}

    top = results[0]
    auto_select = False
    if top["score"] >= 60:
        if len(results) == 1 or results[1]["score"] * 2 <= top["score"]:
            auto_select = True

    return {
        "match": top["project_id"] if auto_select else None,
        "candidates": results[:8],
    }


def main():
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
    else:
        query = input("Search: ")

    result = search(query)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
