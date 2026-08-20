#!/usr/bin/env python3
import argparse
import asyncio
import json
import re
import shutil
import urllib.parse
import urllib.request
from pathlib import Path

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"


def likely_media(url):
    u=(url or "").lower()
    return ("tiktokcdn" in u or "byteoversea" in u or "muscdn" in u or "/video/tos/" in u or "media-video" in u) and not any(x in u for x in (".jpeg",".jpg",".png",".webp","avatar"))


def download_candidate(url, out, cookies, referer):
    cookie_header="; ".join(f"{c['name']}={c['value']}" for c in cookies if c.get('name'))
    headers={"User-Agent":UA,"Referer":referer,"Accept":"*/*","Range":"bytes=0-"}
    if cookie_header:
        headers["Cookie"]=cookie_header
    req=urllib.request.Request(url,headers=headers)
    with urllib.request.urlopen(req,timeout=90) as r,open(out,"wb") as f:
        while True:
            chunk=r.read(1024*1024)
            if not chunk: break
            f.write(chunk)
    return out.stat().st_size


async def main_async(args):
    from playwright.async_api import async_playwright
    out_dir=Path(args.out_dir); out_dir.mkdir(parents=True,exist_ok=True)
    chrome=shutil.which("google-chrome") or shutil.which("google-chrome-stable") or shutil.which("chromium") or shutil.which("chromium-browser")
    if not chrome:
        raise RuntimeError("No Chrome/Chromium executable found")
    candidates=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path=chrome,headless=True,args=["--no-sandbox","--disable-dev-shm-usage","--autoplay-policy=no-user-gesture-required"])
        context=await browser.new_context(user_agent=UA,viewport={"width":1280,"height":900},locale="en-US")
        page=await context.new_page()
        page.on("request",lambda req: candidates.append(req.url) if likely_media(req.url) else None)
        page.on("response",lambda resp: candidates.append(resp.url) if likely_media(resp.url) else None)
        try:
            await page.goto(args.url,wait_until="domcontentloaded",timeout=60000)
        except Exception:
            pass
        await page.wait_for_timeout(12000)
        try:
            video_srcs=await page.locator("video").evaluate_all("els => els.flatMap(v => [v.currentSrc, v.src, ...Array.from(v.querySelectorAll('source')).map(s => s.src)]).filter(Boolean)")
            candidates.extend(video_srcs)
        except Exception:
            pass
        try:
            perf=await page.evaluate("performance.getEntriesByType('resource').map(e => e.name)")
            candidates.extend([u for u in perf if likely_media(u)])
        except Exception:
            pass
        try:
            html=await page.content()
            for pat in (r'"playAddr":"([^"]+)',r'"downloadAddr":"([^"]+)',r'"play_addr":\{"url_list":\["([^"]+)'):
                for m in re.finditer(pat,html):
                    u=m.group(1).replace("\\u002F","/").replace("\\/","/").replace("&amp;","&")
                    if likely_media(u): candidates.append(u)
        except Exception:
            pass
        cookies=await context.cookies()
        title=await page.title()
        current_url=page.url
        await browser.close()

    uniq=[]
    for u in candidates:
        if not u: continue
        u=u.replace("\\u002F","/").replace("\\/","/")
        if u not in uniq: uniq.append(u)
    diag={"input_url":args.url,"page_url":current_url,"page_title":title,"candidate_count":len(uniq),"candidates":uniq[:80]}
    (out_dir/"playwright-candidates.json").write_text(json.dumps(diag,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"page_url":current_url,"page_title":title,"candidate_count":len(uniq)},ensure_ascii=False))

    # Prefer likely full media URLs; try each with browser cookies and referer.
    for i,u in enumerate(uniq[:30]):
        tmp=out_dir/f"browser_candidate_{i:02d}.mp4"
        try:
            size=download_candidate(u,tmp,cookies,args.url)
            if size>=300000:
                final=out_dir/"mahoraga_reference.mp4"
                tmp.replace(final)
                (out_dir/"browser-success.json").write_text(json.dumps({"source_url":u,"bytes":size},indent=2),encoding="utf-8")
                print(f"BROWSER_DOWNLOAD_SUCCESS={size}")
                return 0
        except Exception as e:
            try: tmp.unlink()
            except: pass
            print(f"candidate {i} failed: {type(e).__name__}: {e}")
    raise RuntimeError(f"Playwright found {len(uniq)} media candidates but none downloaded successfully")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--out-dir",default="reference-exact")
    args=ap.parse_args()
    raise SystemExit(asyncio.run(main_async(args)))

if __name__=="__main__":
    main()
