# reddit-political-monitor

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/)
[![Read-only](https://img.shields.io/badge/Reddit-Read--Only-orange.svg)]()

> **Read-only. Does not post, vote, comment, or interact with users.**

A passive monitoring tool for tracking political keywords across public Reddit subreddits. Designed for academic and professional political research use.

---

## Description

`reddit-political-monitor` continuously polls a configurable list of public subreddits and saves posts matching specified keywords to a local JSON file. All access is read-only using Reddit's application-only OAuth flow — no user account required, no write operations of any kind.

This tool is intended for:
- Academic political research
- Campaign issue tracking
- Public sentiment analysis
- Civic engagement monitoring

---

## Features

- 🔍 **Keyword matching** — configurable list of political research terms
- ⏱ **Scheduled polling** — continuous loop with configurable interval
- 🚫 **No write operations** — never posts, votes, comments, or messages
- 🔐 **Application-only OAuth** — `client_credentials` grant, no user login
- 📁 **Local JSON output** — matched posts saved to `matched_posts.json`
- 🛡 **Rate limiting** — 1 request/sec baseline, exponential backoff on 429s
- 📋 **Structured logging** — timestamped console output

---

## Monitored Subreddits

| Subreddit | Region |
|-----------|--------|
| r/Ohio | Ohio (state) |
| r/OhioPolitics | Ohio politics |
| r/Columbus | Columbus, OH |
| r/Cleveland | Cleveland, OH |
| r/Iowa | Iowa (state) |
| r/desmoines | Des Moines, IA |
| r/IowaPolitics | Iowa politics |
| r/Arkansas | Arkansas (state) |
| r/Portland | Portland, OR |
| r/oregon | Oregon (state) |
| r/politics | National politics |
| r/PoliticalDiscussion | Political discussion |
| r/Election2026 | 2026 elections |
| r/Conservative | Conservative politics |
| r/Democrats | Democratic politics |

---

## Setup

### 1. Prerequisites

- Python 3.8+
- A Reddit application (free, read-only scope)

### 2. Create a Reddit Application

1. Go to [https://www.reddit.com/prefs/apps](https://www.reddit.com/prefs/apps)
2. Click **Create App**
3. Select type: **script**
4. Note your `client_id` (under the app name) and `client_secret`

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure

```bash
cp config.example.json config.json
# Edit config.json with your Reddit credentials and desired keywords
```

### 5. Run

```bash
python monitor.py
```

Matched posts will be saved to `matched_posts.json` in the working directory.

---

## Configuration

See [`config.example.json`](config.example.json) for a full example. Key fields:

| Field | Description |
|-------|-------------|
| `reddit_client_id` | Your Reddit app client ID |
| `reddit_client_secret` | Your Reddit app client secret |
| `keywords` | List of keywords to match (case-insensitive) |
| `subreddits` | List of subreddit names to monitor |
| `poll_interval_seconds` | Seconds between polling cycles (default: 60) |
| `output_file` | Path to save matched posts JSON |

---

## Output Format

Each matched post is saved as a JSON object:

```json
{
  "id": "abc123",
  "subreddit": "Ohio",
  "title": "Post title here",
  "author": "username",
  "url": "https://reddit.com/r/Ohio/...",
  "score": 42,
  "created_utc": 1700000000,
  "matched_keywords": ["keyword1"],
  "captured_at": "2026-01-01T12:00:00Z"
}
```

---

## Privacy & Ethics

- Only monitors **public** subreddits
- Stores only publicly available post metadata (no private data)
- Does not track individual users across subreddits
- Does not interact with Reddit in any way (no votes, comments, or posts)
- Complies with [Reddit's API Terms of Service](https://www.redditinc.com/policies/data-api-terms)

---

## License

MIT License — see [LICENSE](LICENSE) for details.

Copyright © 2026 Break Something Tools
