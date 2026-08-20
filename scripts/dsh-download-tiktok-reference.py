#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15"
TIKWM = "https://tikwm.com/api"


def http_json(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json,text/plain,*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def norm(s):
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def score_title(title, query):
    t, q = norm(title), norm(query)
    if not q:
        return 0
    if q in t:
        return 1000 + len(q)
    toks = [x for x in q.split() if len(x) >= 3]
    hit = sum(1 for x in toks if x in t)
    return hit * 100 - abs(len(t) - len(q))


def tikwm_post(identifier):
    qs = urllib.parse.urlencode({"url": identifier, "hd": "1"})
    obj = http_json(f"{TIKWM}/?{qs}")
    if int(obj.get("code", -1)) != 0 or not isinstance(obj.get("data"), dict):
        raise RuntimeError(f"TikWM post lookup failed: {obj.get('msg')} code={obj.get('code')}")
    return obj["data"]


def scan_user(username, query, max_pages=8):
    cursor = "0"
    seen = []
    best = None
    best_score = -10**9
    for page in range(max_pages):
        qs = urllib.parse.urlencode({"unique_id": username, "count": "34", "cursor": cursor})
        obj = http_json(f"{TIKWM}/user/posts?{qs}")
        if int(obj.get("code", -1)) != 0 or not isinstance(obj.get("data"), dict):
            raise RuntimeError(f"TikWM user feed failed: {obj.get('msg')} code={obj.get('code')}")
        data = obj["data"]
        videos = data.get("videos") or []
        for v in videos:
            title = v.get("title") or ""
            s = score_title(title, query)
            seen.append({"id": v.get("id") or v.get("video_id"), "title": title, "score": s, "play_count": v.get("play_count")})
            if s > best_score:
                best, best_score = v, s
        if best_score >= 1000:
            break
        if not data.get("hasMore"):
            break
        new_cursor = str(data.get("cursor") or "")
        if not new_cursor or new_cursor == cursor:
            break
        cursor = new_cursor
        time.sleep(1.15)
    if not best or best_score < 100:
        raise RuntimeError(f"No credible match for {query!r} on @{username}; best_score={best_score}")
    return best, seen


def pick_video_url(post):
    for k in ("hdplay", "play", "wmplay"):
        u = post.get(k)
        if u:
            return urllib.parse.urljoin("https://tikwm.com", u), k
    raise RuntimeError("TikWM returned no downloadable video URL")


def download(url, out):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://www.tiktok.com/", "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=60) as r, open(out, "wb") as f:
        while True:
            chunk = r.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
    if out.stat().st_size < 200_000:
        raise RuntimeError(f"Downloaded file suspiciously small: {out.stat().st_size} bytes")


def validate(path):
    p = subprocess.run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=codec_name,width,height,duration",
        "-show_entries", "format=duration,size", "-of", "json", str(path)
    ], capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {p.stderr[-2000:]}")
    data = json.loads(p.stdout or "{}")
    if not data.get("streams"):
        raise RuntimeError("No video stream in downloaded file")
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="")
    ap.add_argument("--username", default="")
    ap.add_argument("--query", default="")
    ap.add_argument("--out-dir", default="reference-out")
    args = ap.parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    scanned = []
    if args.url:
        post = tikwm_post(args.url)
        resolver = "tikwm-url"
    else:
        if not args.username or not args.query:
            ap.error("provide --url or both --username and --query")
        candidate, scanned = scan_user(args.username, args.query)
        vid = str(candidate.get("id") or candidate.get("video_id") or "")
        if not vid:
            raise RuntimeError("Matched post has no video id")
        post = tikwm_post(vid)
        resolver = "tikwm-user-feed+post-refresh"

    vid = str(post.get("id") or post.get("video_id") or "")
    username = ((post.get("author") or {}).get("unique_id") or args.username or "unknown").lstrip("@")
    title = post.get("title") or ""
    original_url = f"https://www.tiktok.com/@{username}/video/{vid}" if vid else args.url
    media_url, media_field = pick_video_url(post)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", f"{username}_{vid}").strip("_") or "tiktok-reference"
    video_path = out_dir / f"{safe}.mp4"
    download(media_url, video_path)
    probe = validate(video_path)

    meta = {
        "status": "success",
        "resolver": resolver,
        "username": username,
        "query": args.query or None,
        "title": title,
        "video_id": vid,
        "original_tiktok_url": original_url,
        "media_field": media_field,
        "play_count": post.get("play_count"),
        "digg_count": post.get("digg_count"),
        "comment_count": post.get("comment_count"),
        "share_count": post.get("share_count"),
        "duration": post.get("duration"),
        "downloaded_file": str(video_path),
        "bytes": video_path.stat().st_size,
        "ffprobe": probe,
        "scanned_candidates": scanned,
    }
    (out_dir / "tiktok-reference.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: meta[k] for k in ("status", "resolver", "username", "title", "video_id", "original_tiktok_url", "bytes")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
