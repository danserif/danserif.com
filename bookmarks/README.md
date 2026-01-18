# Link Rot Checker

Check for broken links in `bookmarks.json`.

## Install

```bash
pip install requests
```

## Run

```bash
python3 check_links.py
```

The script checks all URLs and reports any broken links at the end. \m/

## Example Output

```
Extracting URLs from bookmarks.json...
Found 100 URLs to check.

Checking links (this may take a while)...

[1/100] ✓ OK: Phosphor Icons
[2/100] ✓ OK: ASCII Rendering
[3/100] ✗ Not Found: Example Link
         https://example.com/broken
...

======================================================================
SUMMARY
======================================================================
Total URLs checked: 100
Working links: 98
Broken links: 2

======================================================================
BROKEN LINKS
======================================================================

✗ Not Found: Example Link
Category: Latest > Inspiration
URL: https://example.com/broken
```
