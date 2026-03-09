#!/usr/bin/env python3
"""
reddit-political-monitor
========================
Read-only Reddit monitoring tool for political keyword tracking.

IMPORTANT: This script is strictly read-only. It uses Reddit's
application-only OAuth flow (client_credentials) and performs
zero write operations — no posting, voting, commenting, or any
other interaction with Reddit users or content.

Usage:
    python monitor.py [--config config.json]

Requirements:
    pip install requests
"""

import json
import logging
import time
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
log = logging.getLogger("reddit-monitor")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

USER_AGENT = "political-research-monitor/1.0 (read-only)"
TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
API_BASE = "https://oauth.reddit.com"
DEFAULT_CONFIG = "config.json"
MIN_REQUEST_INTERVAL = 1.0  # seconds between requests (Reddit rate limit)

# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_config(path: str) -> dict:
    """Load and validate configuration from a JSON file."""
    config_path = Path(path)
    if not config_path.exists():
        log.error(f"Config file not found: {path}")
        sys.exit(1)

    with config_path.open() as f:
        config = json.load(f)

    required = ["reddit_client_id", "reddit_client_secret", "keywords", "subreddits"]
    for key in required:
        if key not in config:
            log.error(f"Missing required config key: {key}")
            sys.exit(1)

    # Apply defaults for optional fields
    config.setdefault("poll_interval_seconds", 60)
    config.setdefault("output_file", "matched_posts.json")
    config.setdefault("fetch_limit", 25)  # posts per subreddit per poll

    return config


# ---------------------------------------------------------------------------
# Reddit OAuth (application-only, read-only)
# ---------------------------------------------------------------------------

class RedditClient:
    """
    Thin Reddit API client using application-only OAuth.

    This client ONLY performs GET requests. There are no methods
    for posting, voting, commenting, or any write operation.
    """

    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = None
        self.token_expiry = 0.0
        self._last_request_time = 0.0

        # Set up a requests Session with retry logic for transient errors
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

        retry = Retry(
            total=3,
            backoff_factor=1.0,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET"],  # only retry on safe methods
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)

    def _authenticate(self):
        """
        Obtain an application-only access token via client_credentials grant.

        This grant type does not require a user account and provides
        read-only access to public Reddit data.
        """
        log.info("Authenticating with Reddit (application-only OAuth)...")
        response = requests.post(
            TOKEN_URL,
            auth=(self.client_id, self.client_secret),
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        self.access_token = data["access_token"]
        # Token is valid for `expires_in` seconds; refresh 60s early
        self.token_expiry = time.time() + data.get("expires_in", 3600) - 60
        self.session.headers.update({"Authorization": f"Bearer {self.access_token}"})
        log.info("Authentication successful.")

    def _ensure_token(self):
        """Refresh the access token if it has expired."""
        if time.time() >= self.token_expiry:
            self._authenticate()

    def _rate_limit(self):
        """Enforce a minimum interval between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < MIN_REQUEST_INTERVAL:
            time.sleep(MIN_REQUEST_INTERVAL - elapsed)

    def get(self, path: str, params: dict = None, retry_count: int = 0) -> dict:
        """
        Perform a single authenticated GET request to the Reddit API.

        Handles 429 rate-limit responses with exponential backoff.
        This is the ONLY HTTP method used — all read-only.
        """
        self._ensure_token()
        self._rate_limit()

        url = f"{API_BASE}{path}"
        self._last_request_time = time.time()

        try:
            response = self.session.get(url, params=params, timeout=15)
        except requests.RequestException as exc:
            log.warning(f"Request error for {path}: {exc}")
            return {}

        # Handle rate limiting with exponential backoff
        if response.status_code == 429:
            wait = min(2 ** retry_count * 2, 120)  # cap at 2 minutes
            log.warning(f"Rate limited (429). Waiting {wait}s before retry...")
            time.sleep(wait)
            if retry_count < 5:
                return self.get(path, params=params, retry_count=retry_count + 1)
            else:
                log.error("Max retries exceeded after rate limiting.")
                return {}

        if not response.ok:
            log.warning(f"API error {response.status_code} for {path}")
            return {}

        return response.json()

    def get_new_posts(self, subreddit: str, limit: int = 25) -> list:
        """
        Fetch the newest posts from a subreddit.

        Returns a list of post data dicts. Read-only — no interaction.
        """
        data = self.get(
            f"/r/{subreddit}/new",
            params={"limit": limit, "raw_json": 1},
        )
        if not data:
            return []

        try:
            return [child["data"] for child in data["data"]["children"]]
        except (KeyError, TypeError):
            log.warning(f"Unexpected response structure for r/{subreddit}")
            return []


# ---------------------------------------------------------------------------
# Keyword matching
# ---------------------------------------------------------------------------

def matches_keywords(post: dict, keywords: list) -> list:
    """
    Check if a post's title or selftext contains any configured keywords.

    Returns the list of matched keywords (empty list = no match).
    Case-insensitive matching.
    """
    title = (post.get("title") or "").lower()
    body = (post.get("selftext") or "").lower()
    text = f"{title} {body}"

    return [kw for kw in keywords if kw.lower() in text]


# ---------------------------------------------------------------------------
# Output / storage
# ---------------------------------------------------------------------------

def load_seen_ids(output_file: str) -> set:
    """Load post IDs already saved to avoid duplicates."""
    path = Path(output_file)
    if not path.exists():
        return set()
    try:
        with path.open() as f:
            records = json.load(f)
        return {r["id"] for r in records if "id" in r}
    except (json.JSONDecodeError, IOError):
        return set()


def save_matched_posts(output_file: str, new_records: list):
    """Append new matched posts to the output JSON file."""
    path = Path(output_file)
    existing = []
    if path.exists():
        try:
            with path.open() as f:
                existing = json.load(f)
        except (json.JSONDecodeError, IOError):
            existing = []

    existing.extend(new_records)

    with path.open("w") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)

    log.info(f"Saved {len(new_records)} new record(s) to {output_file}")


# ---------------------------------------------------------------------------
# Main monitoring loop
# ---------------------------------------------------------------------------

def monitor(config: dict):
    """
    Main loop: poll each subreddit, match keywords, save results.

    Runs indefinitely until interrupted (Ctrl+C).
    """
    client = RedditClient(
        client_id=config["reddit_client_id"],
        client_secret=config["reddit_client_secret"],
    )

    keywords = config["keywords"]
    subreddits = config["subreddits"]
    poll_interval = config["poll_interval_seconds"]
    output_file = config["output_file"]
    fetch_limit = config["fetch_limit"]

    log.info(f"Starting monitor | subreddits={len(subreddits)} | keywords={len(keywords)}")
    log.info(f"Poll interval: {poll_interval}s | Output: {output_file}")
    log.info("Mode: READ-ONLY (no write operations)")

    cycle = 0
    while True:
        cycle += 1
        log.info(f"--- Poll cycle #{cycle} ---")
        seen_ids = load_seen_ids(output_file)
        new_records = []

        for subreddit in subreddits:
            log.debug(f"Fetching r/{subreddit}...")
            posts = client.get_new_posts(subreddit, limit=fetch_limit)

            for post in posts:
                post_id = post.get("id")
                if not post_id or post_id in seen_ids:
                    continue  # skip already-seen posts

                matched = matches_keywords(post, keywords)
                if not matched:
                    continue

                record = {
                    "id": post_id,
                    "subreddit": post.get("subreddit", subreddit),
                    "title": post.get("title", ""),
                    "author": post.get("author", "[deleted]"),
                    "url": post.get("url", ""),
                    "permalink": "https://reddit.com" + post.get("permalink", ""),
                    "score": post.get("score", 0),
                    "num_comments": post.get("num_comments", 0),
                    "created_utc": post.get("created_utc", 0),
                    "matched_keywords": matched,
                    "captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                }
                new_records.append(record)
                seen_ids.add(post_id)
                log.info(f"Match: r/{subreddit} | "{post.get('title','')[:60]}" | kw={matched}")

        if new_records:
            save_matched_posts(output_file, new_records)
        else:
            log.info("No new matches this cycle.")

        log.info(f"Cycle #{cycle} complete. Sleeping {poll_interval}s...")
        time.sleep(poll_interval)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Read-only Reddit political keyword monitor"
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG,
        help=f"Path to config JSON file (default: {DEFAULT_CONFIG})",
    )
    args = parser.parse_args()

    config = load_config(args.config)

    try:
        monitor(config)
    except KeyboardInterrupt:
        log.info("Interrupted by user. Exiting.")
        sys.exit(0)


if __name__ == "__main__":
    main()
