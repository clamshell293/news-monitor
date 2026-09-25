import json
import subprocess
from pathlib import Path

CHANNELS = {
    "abc": {
        "title": "ABC News Australia",
        "channel_id": "UCVgO39Bk5sMo66-6o6Spn6Q",
    },
    "cnn": {
        "title": "CNN",
        "channel_id": "UCupvZG-5ko_eiXAupbDfxWw",
    },
    "global": {
        "title": "寰宇新聞",
        "channel_id": "UCp2f7tGJGN6R9Muxipem8Nw",
    },
    "tbs": {
        "title": "TBS NEWS DIG",
        "channel_id": "UC6AG81pAkf6Lbi_1VC5NmPA",
    },
}

STREAMS_PATH = Path("streams.json")

def run_yt_dlp(url, flat=False):
    cmd = [
        "yt-dlp",
        "--dump-single-json",
        "--no-warnings",
        "--ignore-errors",
    ]
    if flat:
        cmd += ["--flat-playlist", "--playlist-end", "40"]
    cmd.append(url)

    p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if p.returncode != 0 or not p.stdout.strip():
        return None

    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError:
        return None

def find_live_from_streams(channel_id):
    """Inspect the channel's Streams tab and accept only entries explicitly marked live."""
    url = f"https://www.youtube.com/channel/{channel_id}/streams"
    data = run_yt_dlp(url, flat=True)
    if not data:
        return ""

    entries = data.get("entries") or []
    for entry in entries:
        if not entry:
            continue

        # yt-dlp commonly reports active streams as live_status == "is_live".
        if entry.get("live_status") == "is_live":
            vid = entry.get("id")
            if vid:
                return vid

    # Some flat-playlist entries omit live_status, so validate candidates individually.
    for entry in entries[:15]:
        if not entry:
            continue
        vid = entry.get("id")
        if not vid:
            continue
        details = run_yt_dlp(f"https://www.youtube.com/watch?v={vid}", flat=False)
        if details and details.get("is_live") is True and details.get("live_status") == "is_live":
            return vid

    return ""

def find_live_from_live_endpoint(channel_id):
    """Fallback: validate the channel /live endpoint, but never accept a non-live video."""
    data = run_yt_dlp(f"https://www.youtube.com/channel/{channel_id}/live", flat=False)
    if not data:
        return ""

    if data.get("is_live") is True and data.get("live_status") == "is_live":
        return data.get("id") or ""

    return ""

def get_current_live(channel_id):
    vid = find_live_from_streams(channel_id)
    if vid:
        return vid
    return find_live_from_live_endpoint(channel_id)

old = {}
if STREAMS_PATH.exists():
    try:
        old = json.loads(STREAMS_PATH.read_text(encoding="utf-8"))
    except Exception:
        old = {}

out = {}

for key, info in CHANNELS.items():
    title = info["title"]
    channel_id = info["channel_id"]

    try:
        vid = get_current_live(channel_id)
    except Exception as exc:
        print(f"{key}: lookup error: {exc}")
        vid = ""

    # Important: do NOT substitute a random ordinary video.
    # If there is no verified live stream, write an empty value.
    out[key] = {
        "title": title,
        "video_id": vid,
        "status": "live" if vid else "offline",
    }

    print(f"{key}: {vid or 'NO VERIFIED LIVE STREAM'}")

STREAMS_PATH.write_text(
    json.dumps(out, ensure_ascii=False, indent=2),
    encoding="utf-8"
)
