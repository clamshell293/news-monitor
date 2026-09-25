import json
import subprocess
from pathlib import Path

CHANNELS = {
    "abc": {
        "title": "ABC News Australia",
        "channel_id": "UCVgO39Bk5sMo66-6o6Spn6Q",
        "trusted_24h": True,
    },
    "cnn": {
        "title": "CNN",
        "channel_id": "UCupvZG-5ko_eiXAupbDfxWw",
        "trusted_24h": False,
    },
    "global": {
        "title": "寰宇新聞",
        "channel_id": "UCp2f7tGJGN6R9Muxipem8Nw",
        "trusted_24h": True,
    },
    "tbs": {
        "title": "TBS NEWS DIG",
        "channel_id": "UC6AG81pAkf6Lbi_1VC5NmPA",
        "trusted_24h": True,
    },
}

STREAMS_PATH = Path("streams.json")

def load_json_command(url, flat=False):
    cmd = [
        "yt-dlp",
        "--dump-single-json",
        "--no-warnings",
        "--ignore-errors",
        "--no-playlist",
    ]
    if flat:
        cmd += ["--flat-playlist", "--playlist-end", "30"]
    cmd.append(url)

    p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if not p.stdout.strip():
        return None

    try:
        return json.loads(p.stdout)
    except Exception:
        return None

def direct_live_endpoint(channel_id):
    """
    Ask YouTube for the channel's canonical /live destination.
    For trusted 24/7 news channels, a resolved video ID from this endpoint
    is considered usable even when YouTube omits is_live metadata.
    """
    url = f"https://www.youtube.com/channel/{channel_id}/live"
    data = load_json_command(url)
    if not data:
        return None

    vid = data.get("id")
    if not vid:
        return None

    return {
        "id": vid,
        "title": data.get("title") or "",
        "is_live": data.get("is_live"),
        "live_status": data.get("live_status"),
        "was_live": data.get("was_live"),
    }

def scan_streams_tab(channel_id):
    """
    Secondary path. Look at recent/current streams and verify candidates.
    """
    url = f"https://www.youtube.com/channel/{channel_id}/streams"

    cmd = [
        "yt-dlp",
        "--dump-single-json",
        "--flat-playlist",
        "--playlist-end", "30",
        "--no-warnings",
        "--ignore-errors",
        url,
    ]

    p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if not p.stdout.strip():
        return []

    try:
        data = json.loads(p.stdout)
    except Exception:
        return []

    candidates = []
    for e in data.get("entries") or []:
        if not e or not e.get("id"):
            continue
        candidates.append(e["id"])
    return candidates

def inspect_video(video_id):
    return load_json_command(f"https://www.youtube.com/watch?v={video_id}")

def definitely_live(data):
    if not data:
        return False
    return (
        data.get("is_live") is True
        or data.get("live_status") == "is_live"
    )

def find_verified_live(channel_id):
    # 1. Try canonical /live endpoint.
    direct = direct_live_endpoint(channel_id)
    if direct and (direct.get("is_live") is True or direct.get("live_status") == "is_live"):
        return direct["id"]

    # 2. Inspect candidates from Streams tab.
    for vid in scan_streams_tab(channel_id)[:12]:
        details = inspect_video(vid)
        if definitely_live(details):
            return vid

    return ""

def find_trusted_live(channel_id):
    """
    For known 24/7 channels:
    - accept a video ID resolved from /live
    - otherwise try fully verified candidates
    """
    direct = direct_live_endpoint(channel_id)
    if direct and direct.get("id"):
        return direct["id"]

    return find_verified_live(channel_id)

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
    trusted = info["trusted_24h"]

    previous_id = ""
    if isinstance(old.get(key), dict):
        previous_id = old[key].get("video_id") or ""

    try:
        if trusted:
            vid = find_trusted_live(channel_id)
        else:
            vid = find_verified_live(channel_id)
    except Exception as exc:
        print(f"{key}: lookup error: {exc}")
        vid = ""

    if vid:
        status = "live"
        source = "current"
    elif trusted and previous_id:
        # Keep the last known working ID for trusted 24/7 channels
        # when YouTube temporarily blocks/changes metadata.
        vid = previous_id
        status = "fallback"
        source = "previous"
    else:
        vid = ""
        status = "offline"
        source = "none"

    out[key] = {
        "title": title,
        "video_id": vid,
        "status": status,
        "source": source,
    }

    print(f"{key}: {status} {vid or '-'}")

STREAMS_PATH.write_text(
    json.dumps(out, ensure_ascii=False, indent=2),
    encoding="utf-8"
)
