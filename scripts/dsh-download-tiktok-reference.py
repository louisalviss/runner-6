#!/usr/bin/env python3
import argparse
import html
import json
import re
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15"
TIKWM = "https://tikwm.com/api"
WORKER = "https://tdownv4.sl-bjs.workers.dev/"


def http_bytes(url, timeout=35, referer=None):
    headers={"User-Agent": UA, "Accept": "application/json,text/plain,text/html,*/*"}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def http_json(url, timeout=35):
    return json.loads(http_bytes(url, timeout=timeout).decode("utf-8", errors="replace"))


def http_text(url, timeout=35):
    return http_bytes(url, timeout=timeout).decode("utf-8", errors="replace")


def norm(s):
    s = html.unescape(s or "").lower()
    s = re.sub(r"<[^>]+>", " ", s)
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


def card_score(href, context, query):
    href_score = score_title(href, query)
    context_score = score_title(context, query)
    # The URL slug belongs to exactly one Urlebird card. Give it overwhelming
    # priority over neighboring card text to avoid cross-card false matches.
    if href_score >= 1000:
        return 100000 + href_score, href_score, context_score
    if href_score >= 200:
        return 10000 + href_score, href_score, context_score
    return context_score, href_score, context_score


def tikwm_post(identifier):
    qs = urllib.parse.urlencode({"url": identifier, "hd": "1"})
    obj = http_json(f"{TIKWM}/?{qs}")
    if int(obj.get("code", -1)) != 0 or not isinstance(obj.get("data"), dict):
        raise RuntimeError(f"TikWM post lookup failed: {obj.get('msg')} code={obj.get('code')}")
    return obj["data"]


def scan_user_tikwm(username, query, max_pages=8):
    cursor = "0"
    seen = []
    best = None
    best_score = -10**9
    for _ in range(max_pages):
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
        raise RuntimeError(f"No credible TikWM match for {query!r} on @{username}; best_score={best_score}")
    return best, seen


def discover_id_urlebird(username, query):
    profile = f"https://urlebird.com/user/{urllib.parse.quote(username)}/"
    page = http_text(profile)
    candidates = []
    for m in re.finditer(r'href=["\']([^"\']*/video/[^"\']+)["\']', page, flags=re.I):
        href = html.unescape(m.group(1))
        lo=max(0,m.start()-500); hi=min(len(page),m.end()+800)
        context=page[lo:hi]
        score,href_score,context_score=card_score(href,context,query)
        ids=re.findall(r'(?<!\d)(\d{15,22})(?!\d)',href)
        candidates.append((score,href,ids[-1] if ids else "",norm(context)[:500],href_score,context_score))
    for m in re.finditer(r'(?:https?:\\?/\\?/urlebird\.com)?\\?/video\\?/([^"<\\]+)', page, flags=re.I):
        frag=m.group(0).replace('\\/','/')
        lo=max(0,m.start()-500); hi=min(len(page),m.end()+800)
        context=page[lo:hi]
        score,href_score,context_score=card_score(frag,context,query)
        ids=re.findall(r'(?<!\d)(\d{15,22})(?!\d)',frag)
        candidates.append((score,frag,ids[-1] if ids else "",norm(context)[:500],href_score,context_score))
    candidates.sort(key=lambda x:x[0],reverse=True)
    if not candidates or candidates[0][0] < 200:
        raise RuntimeError(f"Urlebird could not identify a credible {query!r} post; candidates={len(candidates)}")
    s,href,vid,ctx,href_score,context_score=candidates[0]
    detail=""
    if not vid:
        detail=urllib.parse.urljoin(profile,href)
        detail_html=http_text(detail)
        ids=re.findall(r'(?<!\d)(\d{15,22})(?!\d)', detail_html)
        if ids:
            mm=re.search(r'tiktok\.com/@[^/"\']+/video/(\d{15,22})',detail_html,re.I)
            vid=mm.group(1) if mm else ids[-1]
    if not vid:
        raise RuntimeError(f"Urlebird matched the title but exposed no TikTok video id: href={href}")
    return vid,{"score":s,"href_score":href_score,"context_score":context_score,"urlebird_href":href,"urlebird_detail_url":detail or urllib.parse.urljoin(profile,href),"context":ctx}


def worker_post(tiktok_url):
    url = WORKER + "?" + urllib.parse.urlencode({"down": tiktok_url})
    obj=http_json(url,timeout=60)
    if not isinstance(obj,dict) or not obj.get("download_url"):
        raise RuntimeError(f"Worker resolver returned no download_url: {str(obj)[:500]}")
    return obj


def pick_tikwm_video_url(post):
    for k in ("hdplay", "play", "wmplay"):
        u = post.get(k)
        if u:
            return urllib.parse.urljoin("https://tikwm.com", u), k
    raise RuntimeError("TikWM returned no downloadable video URL")


def download(url, out):
    headers={"User-Agent": UA,"Referer":"https://www.tiktok.com/","Accept":"*/*"}
    req=urllib.request.Request(url,headers=headers)
    with urllib.request.urlopen(req,timeout=90) as r,open(out,"wb") as f:
        while True:
            chunk=r.read(1024*1024)
            if not chunk: break
            f.write(chunk)
    if out.stat().st_size < 200_000:
        raise RuntimeError(f"Downloaded file suspiciously small: {out.stat().st_size} bytes")


def validate(path):
    p=subprocess.run(["ffprobe","-v","error","-select_streams","v:0","-show_entries","stream=codec_name,width,height,duration","-show_entries","format=duration,size","-of","json",str(path)],capture_output=True,text=True)
    if p.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {p.stderr[-2000:]}")
    data=json.loads(p.stdout or "{}")
    if not data.get("streams"):
        raise RuntimeError("No video stream in downloaded file")
    return data


def persist_discovery(out_dir, discovery):
    (out_dir/"discovery.json").write_text(json.dumps(discovery,ensure_ascii=False,indent=2),encoding="utf-8")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--url",default="")
    ap.add_argument("--username",default="")
    ap.add_argument("--query",default="")
    ap.add_argument("--out-dir",default="reference-out")
    args=ap.parse_args()
    out_dir=Path(args.out_dir); out_dir.mkdir(parents=True,exist_ok=True)
    scanned=[]; discovery={}

    if args.url:
        original_url=args.url
        username=args.username.lstrip("@") or "unknown"
        vid=(re.findall(r'/video/(\d{15,22})',original_url) or [""])[-1]
        try:
            post=tikwm_post(original_url)
            media_url,media_field=pick_tikwm_video_url(post)
            resolver="tikwm-url"
            title=post.get("title") or ""
            username=((post.get("author") or {}).get("unique_id") or username).lstrip("@")
            vid=str(post.get("id") or post.get("video_id") or vid)
            counts={"play_count":post.get("play_count"),"digg_count":post.get("digg_count"),"comment_count":post.get("comment_count"),"share_count":post.get("share_count")}
        except Exception as e:
            discovery={"tikwm_error":repr(e),"video_id":vid,"original_tiktok_url":original_url}
            persist_discovery(out_dir,discovery)
            print(f"DISCOVERED_TIKTOK_ID={vid}")
            print(f"DISCOVERED_TIKTOK_URL={original_url}")
            try:
                obj=worker_post(original_url)
            except Exception as worker_e:
                discovery["worker_error"]=repr(worker_e)
                persist_discovery(out_dir,discovery)
                raise
            resolver="worker-url"
            media_url=obj["download_url"]; media_field="download_url"
            title=obj.get("title") or ""; vid=str(obj.get("video_id") or vid)
            author=obj.get("author") or {}; username=(author.get("username") or username).lstrip("@")
            counts={"play_count":author.get("view_count"),"digg_count":author.get("like_count"),"comment_count":None,"share_count":None}
    else:
        if not args.username or not args.query:
            ap.error("provide --url or both --username and --query")
        username=args.username.lstrip("@")
        try:
            candidate,scanned=scan_user_tikwm(username,args.query)
            vid=str(candidate.get("id") or candidate.get("video_id") or "")
            if not vid: raise RuntimeError("Matched TikWM post has no video id")
            post=tikwm_post(vid)
            resolver="tikwm-user-feed+post-refresh"
            original_url=f"https://www.tiktok.com/@{username}/video/{vid}"
            media_url,media_field=pick_tikwm_video_url(post)
            title=post.get("title") or candidate.get("title") or ""
            username=((post.get("author") or {}).get("unique_id") or username).lstrip("@")
            counts={"play_count":post.get("play_count"),"digg_count":post.get("digg_count"),"comment_count":post.get("comment_count"),"share_count":post.get("share_count")}
        except Exception as e:
            vid,discovery=discover_id_urlebird(username,args.query)
            original_url=f"https://www.tiktok.com/@{username}/video/{vid}"
            discovery.update({"tikwm_error":repr(e),"video_id":vid,"original_tiktok_url":original_url})
            persist_discovery(out_dir,discovery)
            print(f"DISCOVERED_TIKTOK_ID={vid}")
            print(f"DISCOVERED_TIKTOK_URL={original_url}")
            print(f"URLEBIRD_HREF={discovery.get('urlebird_href','')}")
            try:
                obj=worker_post(original_url)
            except Exception as worker_e:
                discovery["worker_error"]=repr(worker_e)
                persist_discovery(out_dir,discovery)
                raise
            resolver="urlebird-id+cloudflare-worker+tiktok-cdn"
            media_url=obj["download_url"]; media_field="download_url"
            title=obj.get("title") or args.query
            author=obj.get("author") or {}; username=(author.get("username") or username).lstrip("@")
            counts={"play_count":author.get("view_count"),"digg_count":author.get("like_count"),"comment_count":None,"share_count":None}

    safe=re.sub(r"[^A-Za-z0-9._-]+","_",f"{username}_{vid}").strip("_") or "tiktok-reference"
    video_path=out_dir/f"{safe}.mp4"
    download(media_url,video_path)
    probe=validate(video_path)
    meta={"status":"success","resolver":resolver,"username":username,"query":args.query or None,"title":title,"video_id":vid,"original_tiktok_url":original_url,"media_field":media_field,**counts,"downloaded_file":str(video_path),"bytes":video_path.stat().st_size,"ffprobe":probe,"discovery":discovery,"scanned_candidates":scanned}
    (out_dir/"tiktok-reference.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:meta[k] for k in ("status","resolver","username","title","video_id","original_tiktok_url","bytes")},ensure_ascii=False))


if __name__=="__main__":
    main()
