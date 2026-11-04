#!/usr/bin/env python3
"""Preserve UT BIBLE locally with source attribution, SHA256 and a Wayback inventory.
Requires Python 3.10+. No third-party dependencies.
Downloaded original content stays in local/ (gitignored) pending rights review.
"""
import argparse, datetime, hashlib, json, pathlib, re, time, urllib.parse, urllib.request
from html.parser import HTMLParser

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "local"
BASE = "https://digdilem.org/ut-bible/"
CDX = "https://web.archive.org/cdx/search/cdx?url=www.ocrana.de%2Futbible%2F%2A&output=json&filter=statuscode%3A200&collapse=urlkey"
SEEDS = ["info.htm", "timing.htm", "underdog.htm", "feign_death.htm", "tricks.htm", "shield_bug.htm"]
EXT = {".htm", ".html", ".jpg", ".jpeg", ".gif", ".png", ".bmp", ".zip", ".rar", ".uz", ".dem", ".txt", ".wav", ".mid"}
class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []
    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        for k in (("href",) if tag == "a" else ("src",) if tag in ("img", "script", "iframe") else ()):
            if d.get(k): self.urls.append(d[k])
def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "UTBiblePreservation/1.0 (noncommercial archival inventory)"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read(), r.headers.get("Content-Type", "")
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--max-files", type=int, default=500)
    p.add_argument("--delay", type=float, default=1.5)
    args = p.parse_args()
    OUT.mkdir(exist_ok=True)
    queue = list(SEEDS)
    seen = set()
    entries = []
    while queue and len(seen) < args.max_files:
        path = queue.pop(0)
        if path in seen: continue
        seen.add(path)
        url = urllib.parse.urljoin(BASE, path)
        entry = {"url": url, "path": path, "retrieved_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}
        try:
            data, ctype = get(url)
            dest = OUT / "mirror" / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            entry.update(status="downloaded", bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), content_type=ctype)
            if path.lower().endswith((".htm", ".html")):
                parser = Links()
                parser.feed(data.decode("latin-1", errors="replace"))
                for link in parser.urls:
                    target = urllib.parse.urljoin(url, link).split("#")[0]
                    parsed = urllib.parse.urlsplit(target)
                    if parsed.netloc.lower() not in ("digdilem.org", "www.digdilem.org"): continue
                    rel = urllib.parse.unquote(parsed.path).removeprefix("/ut-bible/")
                    if not rel or rel.startswith("/") or ".." in pathlib.PurePosixPath(rel).parts: continue
                    if pathlib.PurePosixPath(rel).suffix.lower() in EXT and rel not in seen and rel not in queue:
                        queue.append(rel)
        except Exception as e:
            entry.update(status="failed", error=str(e))
        entries.append(entry)
        print(entry["status"], url)
        time.sleep(max(args.delay, 0))
    (OUT / "mirror-manifest.json").write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n")
    try:
        data, _ = get(CDX)
        rows = json.loads(data)
        (OUT / "wayback-cdx.json").write_text(json.dumps(rows, indent=2) + "\n")
        old = {urllib.parse.urlsplit(row[2]).path.lower().removeprefix("/utbible/") for row in rows[1:] if len(row) > 2}
        mirrored = {e["path"].lower() for e in entries if e["status"] == "downloaded"}
        report = {"mirror_downloaded":len(mirrored), "wayback_unique_paths":len(old), "wayback_only":sorted(old - mirrored), "mirror_only":sorted(mirrored - old)}
        (OUT / "comparison.json").write_text(json.dumps(report, indent=2) + "\n")
        print("Comparison:", report)
    except Exception as e:
        (OUT / "wayback-error.txt").write_text(str(e) + "\n")
        print("Wayback inventory unavailable:", e)
    print("Local original files are intentionally excluded from git until rights are reviewed.")
if __name__ == "__main__":
    main()
