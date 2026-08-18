import json, os, re, time, urllib.request, urllib.error
from pathlib import Path

URL = Path('request.txt').read_text(encoding='utf-8').strip()
m = re.search(r'(?:x|twitter)\.com/([^/]+)/status/(\d+)', URL)
if not m:
    raise SystemExit('Invalid X/Twitter status URL')
handle, status_id = m.group(1), m.group(2)

out = {
    'requested_url': URL,
    'handle': handle,
    'status_id': status_id,
    'fetched_at_utc': __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
    'api': {},
    'browser': {}
}

def fetch_json(name, url):
    try:
        req = urllib.request.Request(url, headers={'User-Agent':'LouisRunner6-XFetch/1.0'})
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode('utf-8', 'replace')
            out['api'][name] = {'url': url, 'http_status': r.status, 'json': json.loads(body)}
            return True
    except Exception as e:
        out['api'][name] = {'url': url, 'error': repr(e)}
        return False

fetch_json('fxtwitter', f'https://api.fxtwitter.com/{handle}/status/{status_id}')
fetch_json('vxtwitter', f'https://api.vxtwitter.com/{handle}/status/{status_id}')

try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled'])
        context = browser.new_context(
            viewport={'width': 1280, 'height': 1600},
            user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
            locale='en-US'
        )
        page = context.new_page()
        response = page.goto(URL, wait_until='domcontentloaded', timeout=60000)
        page.wait_for_timeout(8000)
        out['browser']['http_status'] = response.status if response else None
        out['browser']['final_url'] = page.url
        out['browser']['title'] = page.title()
        try:
            out['browser']['body_text'] = page.locator('body').inner_text(timeout=10000)[:50000]
        except Exception as e:
            out['browser']['body_text_error'] = repr(e)
        try:
            page.screenshot(path='x-page.png', full_page=True)
            out['browser']['screenshot'] = 'x-page.png'
        except Exception as e:
            out['browser']['screenshot_error'] = repr(e)
        browser.close()
except Exception as e:
    out['browser']['error'] = repr(e)

Path('x-result.json').write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(out, ensure_ascii=False, indent=2)[:12000])
