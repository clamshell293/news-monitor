import json, re, urllib.request, html
from pathlib import Path

CHANNELS = {
    "abc": ("ABC News Australia", "UCVgO39Bk5sMo66-6o6Spn6Q"),
    "nbc": ("NBC News NOW", "UCeY0bbntWzzVIaj2z3QigXg"),
    "global": ("寰宇新聞", "UCp2f7tGJGN6R9Muxipem8Nw"),
    "tbs": ("TBS NEWS DIG", "UC6AG81pAkf6Lbi_1VC5NmPA"),
}

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language":"en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="ignore")

def current_live_video(channel_id):
    # YouTube's /live endpoint redirects to the active livestream when one exists.
    req = urllib.request.Request(f"https://www.youtube.com/channel/{channel_id}/live", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        final = r.geturl()
        body = r.read().decode("utf-8", errors="ignore")
    m = re.search(r"[?&]v=([A-Za-z0-9_-]{11})", final)
    if m: return m.group(1)
    # Fallbacks for pages that render the current watch id in HTML.
    patterns = [
        r'"videoId":"([A-Za-z0-9_-]{11})"',
        r'watch\?v=([A-Za-z0-9_-]{11})',
    ]
    for pat in patterns:
        m = re.search(pat, body)
        if m: return m.group(1)
    return ""

out = {}
old_path = Path("streams.json")
old = {}
if old_path.exists():
    try: old = json.loads(old_path.read_text(encoding="utf-8"))
    except Exception: pass

for key, (title, cid) in CHANNELS.items():
    vid = ""
    try:
        vid = current_live_video(cid)
    except Exception as e:
        print(f"{key}: lookup failed: {e}")
    if not vid:
        vid = (old.get(key) or {}).get("video_id", "")
    out[key] = {"title": title, "video_id": vid}
    print(key, vid)

old_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
