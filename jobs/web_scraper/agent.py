"""
ScraperAgent — fetch pages, extract links, learn dead URLs, track success rates.

Usage:
    from agent_framework import load_team, save_team
    from jobs.web_scraper.agent import ScraperAgent

    team = load_team("team.json")
    agent = ScraperAgent("scraper", team)
    results = agent.run()
    save_team(team)
"""

import time
import urllib.request
import urllib.error
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from agent_framework import Agent


class _LinkExtractor(HTMLParser):
    """Simple HTML parser that extracts href links."""

    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            for name, value in attrs:
                if name == "href" and value:
                    self.links.append(value)


class ScraperAgent(Agent):
    """
    Fetches web pages and extracts links. Learns which URLs are dead,
    which redirected, and what patterns work.
    """

    def _apply_experience(self):
        """Build skip list from known dead URLs."""
        dead_lessons = self.recall("dead_url")
        self._dead_urls = {l.get("context", "") for l in dead_lessons}
        self.log(f"Loaded {len(self._dead_urls)} known dead URLs to skip")

    def _fetch(self, url):
        """Fetch a URL and return (status_code, content) or (error_code, None)."""
        timeout = self.config.get("timeout_seconds", 30)
        user_agent = self.config.get("user_agent", "persistent-team-scraper/1.0")

        req = urllib.request.Request(url, headers={"User-Agent": user_agent})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                content = response.read().decode("utf-8", errors="replace")
                return response.status, content
        except urllib.error.HTTPError as e:
            return e.code, None
        except urllib.error.URLError as e:
            self.learn("connection_error", f"Cannot reach {url}", str(e), context=url)
            return 0, None
        except Exception as e:
            self.learn("unexpected_error", f"Error fetching {url}", str(e), context=url)
            return -1, None

    def _extract_links(self, html, base_url):
        """Extract absolute links from HTML content."""
        parser = _LinkExtractor()
        parser.feed(html)
        links = set()
        allowed = self.config.get("allowed_domains", [])
        for href in parser.links:
            absolute = urljoin(base_url, href)
            parsed = urlparse(absolute)
            if parsed.scheme in ("http", "https"):
                if not allowed or parsed.netloc in allowed:
                    links.add(absolute)
        return links

    def run(self, urls=None, **kwargs):
        """
        Fetch entry URLs and extract links.

        Args:
            urls: list of URLs to fetch (overrides config entry_urls)

        Returns:
            dict with discovered_urls, successes, failures
        """
        self._apply_experience()

        entry_urls = urls or self.config.get("entry_urls", [])
        delay = self.config.get("request_delay_seconds", 1.0)
        max_retries = self.config.get("max_retries", 3)

        all_links = set()
        successes = 0
        failures = 0

        for url in entry_urls:
            if url in self._dead_urls:
                self.log(f"Skipping known dead URL: {url}")
                continue

            status = 0
            content = None
            for attempt in range(max_retries):
                status, content = self._fetch(url)
                if status == 200:
                    break
                if status == 429:
                    self.log(f"Rate limited on {url}, waiting...")
                    time.sleep(delay * (attempt + 2))
                else:
                    break

            if status == 200 and content:
                links = self._extract_links(content, url)
                all_links.update(links)
                successes += 1
                self.log(f"OK {url} → {len(links)} links")
            else:
                failures += 1
                if status in (404, 410):
                    self.learn("dead_url", f"URL is dead ({status})",
                               "Skip in future runs", context=url)
                elif status == 301:
                    self.learn("redirect", f"URL redirected ({status})",
                               "Check new location", context=url)
                self.log(f"FAIL {url} → status {status}")

            if delay > 0:
                time.sleep(delay)

        # Update experience stats
        self.experience["success_count"] = self.experience.get("success_count", 0) + successes
        self.experience["failure_count"] = self.experience.get("failure_count", 0) + failures
        self.experience["discovered_urls"] = list(
            set(self.experience.get("discovered_urls", [])) | all_links
        )

        self.save_state()

        return {
            "discovered_urls": list(all_links),
            "successes": successes,
            "failures": failures,
        }
