#!/usr/bin/env python3
"""
Link rot checker for bookmarks.json
Checks all URLs in the bookmarks file to see if they're still accessible.
"""

import json
import sys
import time
from urllib.parse import urlparse
from collections import defaultdict

try:
    import requests
    from requests.adapters import HTTPAdapter
    try:
        from urllib3.util.retry import Retry
    except ImportError:
        # Fallback for older requests versions
        from requests.packages.urllib3.util.retry import Retry
except ImportError:
    print("Error: 'requests' library is required.")
    print("Install it with: pip install requests")
    sys.exit(1)


def create_session():
    """Create a requests session with retry strategy and timeout."""
    session = requests.Session()
    
    # Retry strategy for transient errors (exclude 429 to avoid retry loops)
    retry_strategy = Retry(
        total=2,
        backoff_factor=0.5,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["HEAD", "GET"]
    )
    
    # Configure connection pool settings to avoid pool exhaustion
    adapter = HTTPAdapter(
        max_retries=retry_strategy,
        pool_connections=10,
        pool_maxsize=20,
        pool_block=False
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    # Set browser-like headers to avoid being blocked
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    })
    
    # Verify SSL certificates
    session.verify = True
    
    return session


def check_url(session, url, timeout=10):
    """
    Check if a URL is accessible.
    Returns a tuple: (status_code, status_text, error_message)
    """
    try:
        # First try HEAD request (faster, doesn't download content)
        response = session.head(url, timeout=timeout, allow_redirects=True)
        status_code = response.status_code
        
        # If HEAD is not allowed or returns 403, try GET
        # Some servers block HEAD requests but allow GET
        if status_code == 405 or status_code == 403:
            response = session.get(url, timeout=timeout, allow_redirects=True, stream=True)
            status_code = response.status_code
        
        # Determine status text
        if 200 <= status_code < 300:
            status_text = "✓ OK"
        elif 300 <= status_code < 400:
            status_text = f"→ Redirect ({status_code})"
        elif status_code == 403:
            status_text = "✗ Forbidden"
        elif status_code == 404:
            status_text = "✗ Not Found"
        elif status_code == 429:
            status_text = "✗ Rate Limited"
            return status_code, status_text, "Too many requests - server rate limiting"
        elif 400 <= status_code < 500:
            status_text = f"✗ Client Error ({status_code})"
        elif 500 <= status_code < 600:
            status_text = f"✗ Server Error ({status_code})"
        else:
            status_text = f"? Unknown ({status_code})"
        
        return status_code, status_text, None
        
    except requests.exceptions.SSLError as e:
        return None, "✗ SSL Error", str(e)
    except requests.exceptions.Timeout:
        return None, "✗ Timeout", "Request timed out"
    except requests.exceptions.ConnectionError as e:
        # Handle connection pool errors more gracefully
        error_msg = str(e)
        if "HTTPSConnectionPool" in error_msg or "Connection pool" in error_msg:
            error_msg = "Connection pool exhausted or connection error"
        return None, "✗ Connection Error", error_msg
    except requests.exceptions.TooManyRedirects:
        return None, "✗ Too Many Redirects", "Redirect loop detected"
    except requests.exceptions.RequestException as e:
        error_msg = str(e)
        # Check if it's a 429 error in the exception message
        if "429" in error_msg or "too many" in error_msg.lower():
            return 429, "✗ Rate Limited", "Too many requests - server rate limiting"
        return None, "✗ Request Error", error_msg
    except Exception as e:
        return None, "✗ Error", str(e)


def extract_urls(data, path=""):
    """
    Recursively extract all URLs from the JSON structure.
    Returns a list of tuples: (url, title, category_path)
    """
    urls = []
    
    if isinstance(data, dict):
        # Check if this is a link object with a URL
        if "url" in data:
            title = data.get("title", "Untitled")
            category_path = path
            urls.append((data["url"], title, category_path))
        
        # Recursively process nested structures
        for key, value in data.items():
            if key == "name" and path:
                # Update path when we encounter a category name
                new_path = f"{path} > {value}" if path else value
            else:
                new_path = path
            urls.extend(extract_urls(value, new_path))
    
    elif isinstance(data, list):
        for item in data:
            urls.extend(extract_urls(item, path))
    
    return urls


def main():
    """Main function to check all bookmarks."""
    json_file = "bookmarks.json"
    
    # Load JSON file
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: {json_file} not found in current directory.")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {json_file}: {e}")
        sys.exit(1)
    
    # Extract all URLs
    print("Extracting URLs from bookmarks.json...")
    urls = extract_urls(data)
    
    if not urls:
        print("No URLs found in bookmarks.json")
        sys.exit(0)
    
    print(f"Found {len(urls)} URLs to check.\n")
    print("Checking links (this may take a while)...\n")
    
    # Create session
    session = create_session()
    
    # Check each URL
    results = []
    broken_links = []
    
    for i, (url, title, category) in enumerate(urls, 1):
        # Validate URL format
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            status_code, status_text, error = None, "✗ Invalid URL", "Missing scheme or domain"
            results.append((url, title, category, status_code, status_text, error))
            broken_links.append((url, title, category, status_text, error))
            print(f"[{i}/{len(urls)}] {status_text}: {title}")
            print(f"         {url}")
            continue
        
        # Check the URL
        status_code, status_text, error = check_url(session, url)
        results.append((url, title, category, status_code, status_text, error))
        
        # Track broken links (non-2xx status codes or errors)
        if status_code is None or not (200 <= status_code < 300):
            broken_links.append((url, title, category, status_text, error))
        
        # Print progress
        print(f"[{i}/{len(urls)}] {status_text}: {title}")
        if error:
            print(f"         {url}")
            print(f"         Error: {error}")
        
        # Delay between requests to avoid rate limiting
        # Longer delay if we hit a rate limit
        if status_code == 429:
            print(f"         Waiting 5 seconds due to rate limiting...")
            time.sleep(5)
        else:
            time.sleep(0.5)  # Increased from 0.2 to 0.5 seconds
    
    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    print(f"Total URLs checked: {len(urls)}")
    print(f"Working links: {len(urls) - len(broken_links)}")
    print(f"Broken links: {len(broken_links)}")
    
    if broken_links:
        print("\n" + "="*70)
        print("BROKEN LINKS")
        print("="*70)
        for url, title, category, status_text, error in broken_links:
            print(f"\n{status_text}: {title}")
            if category:
                print(f"Category: {category}")
            print(f"URL: {url}")
            if error:
                print(f"Error: {error}")
    
    # Exit with error code if broken links found
    if broken_links:
        sys.exit(1)
    else:
        print("\n✓ All links are working!")
        sys.exit(0)


if __name__ == "__main__":
    main()
