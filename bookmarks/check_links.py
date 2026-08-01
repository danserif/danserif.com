#!/usr/bin/env python3
"""
Link rot checker for bookmarks.json
Checks all URLs in the bookmarks file to see if they're still accessible.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Lock
from urllib.parse import urlparse

try:
    import requests
    from requests.adapters import HTTPAdapter

    try:
        from urllib3.util.retry import Retry
    except ImportError:
        from requests.packages.urllib3.util.retry import Retry
except ImportError:
    print("Error: 'requests' library is required.")
    print("Install it with: pip install -r bookmarks/requirements.txt")
    sys.exit(1)

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_JSON = SCRIPT_DIR / "bookmarks.json"

# Hard failures: link is very likely dead.
DEAD_STATUS_CODES = {404, 410, 451}
# Soft failures: often bot-blocks or flaky hosts; need human review.
SUSPICIOUS_STATUS_CODES = {401, 403, 429, 503}


@dataclass
class CheckResult:
    url: str
    title: str
    category: str
    status_code: int | None
    status_text: str
    severity: str  # ok | dead | suspicious
    error: str | None = None
    final_url: str | None = None


class DomainThrottle:
    """Simple per-domain minimum interval between requests."""

    def __init__(self, interval: float):
        self.interval = interval
        self._last: dict[str, float] = {}
        self._lock = Lock()

    def wait(self, domain: str) -> None:
        if self.interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            last = self._last.get(domain, 0.0)
            delay = self.interval - (now - last)
            if delay > 0:
                time.sleep(delay)
            self._last[domain] = time.monotonic()


def create_session() -> requests.Session:
    """Create a requests session with retry strategy and timeout."""
    session = requests.Session()

    retry_strategy = Retry(
        total=2,
        backoff_factor=0.5,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["HEAD", "GET"],
    )

    adapter = HTTPAdapter(
        max_retries=retry_strategy,
        pool_connections=20,
        pool_maxsize=20,
        pool_block=False,
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
    )
    session.verify = True
    return session


def classify(status_code: int | None, error_kind: str | None = None) -> tuple[str, str]:
    """
    Return (severity, status_text).
    severity: ok | dead | suspicious
    """
    if error_kind == "invalid":
        return "dead", "✗ Invalid URL"
    if error_kind == "ssl":
        return "suspicious", "? SSL Error"
    if error_kind == "timeout":
        return "suspicious", "? Timeout"
    if error_kind == "connection":
        return "dead", "✗ Connection Error"
    if error_kind == "redirects":
        return "dead", "✗ Too Many Redirects"
    if error_kind == "request":
        return "suspicious", "? Request Error"
    if error_kind == "error":
        return "suspicious", "? Error"

    if status_code is None:
        return "suspicious", "? Unknown"

    if 200 <= status_code < 300:
        return "ok", "✓ OK"
    if status_code in DEAD_STATUS_CODES:
        label = {
            404: "✗ Not Found",
            410: "✗ Gone",
            451: "✗ Unavailable For Legal Reasons",
        }.get(status_code, f"✗ Dead ({status_code})")
        return "dead", label
    if status_code in SUSPICIOUS_STATUS_CODES:
        label = {
            401: "? Unauthorized",
            403: "? Forbidden",
            429: "? Rate Limited",
            503: "? Unavailable",
        }.get(status_code, f"? Suspicious ({status_code})")
        return "suspicious", label
    if 300 <= status_code < 400:
        # With allow_redirects=True this is rare; treat as ok if we somehow land here.
        return "ok", f"→ Redirect ({status_code})"
    if 400 <= status_code < 500:
        return "dead", f"✗ Client Error ({status_code})"
    if 500 <= status_code < 600:
        return "suspicious", f"? Server Error ({status_code})"
    return "suspicious", f"? Unknown ({status_code})"


def check_url(
    session: requests.Session,
    url: str,
    title: str,
    category: str,
    throttle: DomainThrottle,
    timeout: float = 10,
) -> CheckResult:
    """Check if a URL is accessible."""
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        severity, status_text = classify(None, "invalid")
        return CheckResult(
            url=url,
            title=title,
            category=category,
            status_code=None,
            status_text=status_text,
            severity=severity,
            error="Missing scheme or domain",
        )

    domain = parsed.netloc.lower()
    throttle.wait(domain)

    try:
        # Prefer GET with a tiny range: many hosts block or mishandle HEAD.
        response = session.get(
            url,
            timeout=timeout,
            allow_redirects=True,
            stream=True,
            headers={"Range": "bytes=0-0"},
        )
        # Drain/close without downloading the body.
        response.close()

        status_code = response.status_code
        # Some servers reject Range with 416 but the resource exists.
        if status_code == 416:
            throttle.wait(domain)
            response = session.get(
                url,
                timeout=timeout,
                allow_redirects=True,
                stream=True,
            )
            response.close()
            status_code = response.status_code

        severity, status_text = classify(status_code)
        error = None
        if status_code == 429:
            error = "Too many requests - server rate limiting"
        elif severity != "ok":
            error = f"HTTP {status_code}"

        return CheckResult(
            url=url,
            title=title,
            category=category,
            status_code=status_code,
            status_text=status_text,
            severity=severity,
            error=error,
            final_url=response.url if response.url != url else None,
        )

    except requests.exceptions.SSLError as e:
        severity, status_text = classify(None, "ssl")
        return CheckResult(url, title, category, None, status_text, severity, str(e))
    except requests.exceptions.Timeout:
        severity, status_text = classify(None, "timeout")
        return CheckResult(url, title, category, None, status_text, severity, "Request timed out")
    except requests.exceptions.ConnectionError as e:
        severity, status_text = classify(None, "connection")
        error_msg = str(e)
        if "HTTPSConnectionPool" in error_msg or "Connection pool" in error_msg:
            error_msg = "Connection pool exhausted or connection error"
        return CheckResult(url, title, category, None, status_text, severity, error_msg)
    except requests.exceptions.TooManyRedirects:
        severity, status_text = classify(None, "redirects")
        return CheckResult(
            url, title, category, None, status_text, severity, "Redirect loop detected"
        )
    except requests.exceptions.RequestException as e:
        error_msg = str(e)
        if "429" in error_msg or "too many" in error_msg.lower():
            severity, status_text = classify(429)
            return CheckResult(
                url,
                title,
                category,
                429,
                status_text,
                severity,
                "Too many requests - server rate limiting",
            )
        severity, status_text = classify(None, "request")
        return CheckResult(url, title, category, None, status_text, severity, error_msg)
    except Exception as e:
        severity, status_text = classify(None, "error")
        return CheckResult(url, title, category, None, status_text, severity, str(e))


def extract_urls(data, path: str = "") -> list[tuple[str, str, str]]:
    """
    Recursively extract all URLs from the JSON structure.
    Returns a list of tuples: (url, title, category_path)
    """
    urls: list[tuple[str, str, str]] = []

    if isinstance(data, dict):
        if "url" in data:
            title = data.get("title", "Untitled")
            urls.append((data["url"], title, path))

        # If this object names a category, apply it to nested children.
        child_path = path
        name = data.get("name")
        if isinstance(name, str) and name:
            child_path = f"{path} > {name}" if path else name

        for key, value in data.items():
            if key in ("url", "title", "name", "note", "urlDisplay", "urlMobile", "titleMobile"):
                continue
            urls.extend(extract_urls(value, child_path))

    elif isinstance(data, list):
        for item in data:
            urls.extend(extract_urls(item, path))

    return urls


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check bookmarks.json for dead links.")
    parser.add_argument(
        "--file",
        type=Path,
        default=DEFAULT_JSON,
        help=f"Path to bookmarks JSON (default: {DEFAULT_JSON})",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Concurrent request workers (default: 8)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.35,
        help="Minimum seconds between requests to the same domain (default: 0.35)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10,
        help="Per-request timeout in seconds (default: 10)",
    )
    parser.add_argument(
        "--json",
        dest="json_out",
        type=Path,
        metavar="PATH",
        help="Write full machine-readable results to PATH",
    )
    parser.add_argument(
        "--fail-on",
        choices=("dead", "suspicious", "none"),
        default="dead",
        help="Exit non-zero when this severity (or worse) is present (default: dead)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    json_file: Path = args.file

    try:
        with open(json_file, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: {json_file} not found.")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {json_file}: {e}")
        sys.exit(1)

    print(f"Extracting URLs from {json_file}...")
    raw_urls = extract_urls(data)
    if not raw_urls:
        print("No URLs found.")
        sys.exit(0)

    # Deduplicate by URL, keep first title/category.
    seen: dict[str, tuple[str, str]] = {}
    for url, title, category in raw_urls:
        if url not in seen:
            seen[url] = (title, category)
    urls = [(url, title, category) for url, (title, category) in seen.items()]

    dupes = len(raw_urls) - len(urls)
    print(f"Found {len(raw_urls)} URLs ({len(urls)} unique" + (f", {dupes} duplicates skipped" if dupes else "") + ").\n")
    print(f"Checking links with {args.workers} workers...\n")

    session = create_session()
    throttle = DomainThrottle(args.delay)
    results: list[CheckResult] = []

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {
            executor.submit(
                check_url,
                session,
                url,
                title,
                category,
                throttle,
                args.timeout,
            ): (url, title)
            for url, title, category in urls
        }

        completed = 0
        for future in as_completed(futures):
            completed += 1
            result = future.result()
            results.append(result)
            print(f"[{completed}/{len(urls)}] {result.status_text}: {result.title}")
            if result.error and result.severity != "ok":
                print(f"         {result.url}")
                print(f"         {result.error}")

    # Stable order matching original bookmark order.
    order = {url: i for i, (url, _, _) in enumerate(urls)}
    results.sort(key=lambda r: order.get(r.url, 0))

    dead = [r for r in results if r.severity == "dead"]
    suspicious = [r for r in results if r.severity == "suspicious"]
    ok = [r for r in results if r.severity == "ok"]

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total unique URLs checked: {len(results)}")
    print(f"Working:    {len(ok)}")
    print(f"Dead:       {len(dead)}")
    print(f"Suspicious: {len(suspicious)}")

    def print_group(label: str, items: list[CheckResult]) -> None:
        if not items:
            return
        print("\n" + "=" * 70)
        print(label)
        print("=" * 70)
        for r in items:
            print(f"\n{r.status_text}: {r.title}")
            if r.category:
                print(f"Category: {r.category}")
            print(f"URL: {r.url}")
            if r.final_url:
                print(f"Final URL: {r.final_url}")
            if r.error:
                print(f"Error: {r.error}")

    print_group("DEAD LINKS", dead)
    print_group("SUSPICIOUS LINKS (review manually)", suspicious)

    if args.json_out:
        report = {
            "file": str(json_file),
            "total": len(results),
            "ok": len(ok),
            "dead": len(dead),
            "suspicious": len(suspicious),
            "results": [asdict(r) for r in results],
        }
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
            f.write("\n")
        print(f"\nWrote report to {args.json_out}")

    if args.fail_on == "none":
        sys.exit(0)
    if args.fail_on == "suspicious" and (dead or suspicious):
        sys.exit(1)
    if args.fail_on == "dead" and dead:
        sys.exit(1)

    if not dead and not suspicious:
        print("\n✓ All links are working!")
    elif not dead:
        print("\n✓ No dead links (some suspicious — review manually).")
    sys.exit(0)


if __name__ == "__main__":
    main()
