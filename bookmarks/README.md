# Link Rot Checker

Check for broken links in `bookmarks.json`.

Results are split into:

- **Dead** — likely gone (404/410, bad URL, connection refused, etc.)
- **Suspicious** — often bot blocks or flaky hosts (403/429/timeouts); review manually

By default the script exits non-zero only when dead links are found.

## Install

```bash
pip install -r bookmarks/requirements.txt
```

Or:

```bash
pip install requests
```

## Run

From the repo root:

```bash
python3 bookmarks/check_links.py
```

### Options

```bash
python3 bookmarks/check_links.py --workers 8 --delay 0.35
python3 bookmarks/check_links.py --json bookmarks/link-report.json
python3 bookmarks/check_links.py --fail-on suspicious   # also fail on soft errors
python3 bookmarks/check_links.py --fail-on none         # always exit 0
```

## Example Output

```
Extracting URLs from .../bookmarks/bookmarks.json...
Found 138 URLs (134 unique, 4 duplicates skipped).

Checking links with 8 workers...

[1/134] ✓ OK: Phosphor Icons
[2/134] ✗ Not Found: Example Link
         https://example.com/broken
         HTTP 404
...

======================================================================
SUMMARY
======================================================================
Total unique URLs checked: 134
Working:    130
Dead:       1
Suspicious: 3

======================================================================
DEAD LINKS
======================================================================

✗ Not Found: Example Link
Category: Latest
URL: https://example.com/broken
Error: HTTP 404
```
