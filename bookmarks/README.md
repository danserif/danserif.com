# Bookmarks Link Rot Checker

A simple script to check for broken links (link rot) in the bookmarks collection.

## Summary

The `check_links.py` script extracts all URLs from `bookmarks.json`, checks each one to verify it's still accessible, and reports any broken links. It handles timeouts, redirects, connection errors, and provides a detailed summary at the end.

## Requirements

Install the `requests` library:

```bash
pip install requests
```

## Usage

From the `/bookmarks` directory, run:

```bash
python3 check_links.py
```

Or if the script is executable:

```bash
./check_links.py
```

## Features

- **Extracts all URLs** from the nested JSON structure
- **Checks each URL** using HTTP HEAD requests (faster) with GET fallback
- **Handles timeouts, redirects, and errors** gracefully
- **Shows progress** as it checks each link
- **Provides a summary** with broken links listed at the end
- **Respectful rate limiting** with small delays between requests

## Output

The script will:
- Show progress for each URL as it checks
- Display a summary at the end with total URLs, working links, and broken links
- List all broken links with their status codes and error messages
- Exit with code 1 if any broken links are found (useful for automation)

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
