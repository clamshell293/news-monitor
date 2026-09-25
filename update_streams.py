import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

API_KEY = os.environ.get("YOUTUBE_API_KEY", "").strip()
if not API_KEY:
    raise SystemExit("Missing YOUTUBE_API_KEY")

CHANNELS = {
    "abc": {
        "title": "ABC News Australia",
        "channel_id": "UCVgO39Bk5sMo66-6o6Spn6Q",
        "mode": "search_live",
    },
    "cnn": {
        "title": "CNN",
        "channel_id": "UCupvZG-5ko_eiXAupbDfxWw",
        "mode": "search_live",
    },
    "global": {
        "title": "寰宇新聞",
        "channel_id": "UCp2f7tGJGN6R9Muxipem8Nw",
        "mode": "uploads",
    },
    "tbs": {
        "title": "TBS NEWS DIG",
        "channel_id": "UC6AG81pAkf6Lbi_1VC5NmPA",
        "mode": "uploads",
    },
}

STREAMS_PATH = Path("streams.json")
BASE = "https://www.googleapis.com/youtube/v3"

def api_get(endpoint, **params):
    params["key"] = API_KEY
    url = f"{BASE}/{endpoint}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "news-monitor/4.1"}
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

def inspect_video_ids(video_ids):
    if not video_ids:
        return []

    data = api_get(
        "videos",
        part="snippet,status,liveStreamingDetails",
        id=",".join(video_ids),
        maxResults=50,
    )
    return data.get("items", [])

def is_usable_live(video, expected_channel_id):
    snippet = video.get("snippet", {})
    status = video.get("status", {})

    return (
        snippet.get("channelId") == expected_channel_id
        and snippet.get("liveBroadcastContent") == "live"
        and status.get("privacyStatus") == "public"
        and status.get("embeddable", True) is not False
    )

def validate_previous(video_id, expected_channel_id):
    if not video_id:
        return None

    items = inspect_video_ids([video_id])
    if items and is_usable_live(items[0], expected_channel_id):
        return items[0]

    return None

def search_current_live(channel_id):
    """
    Directly ask YouTube for currently-live videos from this channel.
    Used for ABC and CNN because long-running live streams may be buried
    deep in the uploads playlist.
    """
    data = api_get(
        "search",
        part="snippet",
        channelId=channel_id,
        eventType="live",
        type="video",
        maxResults=10,
        order="date",
    )

    ids = []
    for item in data.get("items", []):
        vid = item.get("id", {}).get("videoId")
        if vid:
            ids.append(vid)

    if not ids:
        return None

    videos = inspect_video_ids(ids)
    by_id = {v.get("id"): v for v in videos}

    # Preserve search result order
    for vid in ids:
        video = by_id.get(vid)
        if video and is_usable_live(video, channel_id):
            return video

    return None

def get_upload_playlist(channel_id):
    data = api_get(
        "channels",
        part="contentDetails",
        id=channel_id,
        maxResults=1,
    )

    items = data.get("items", [])
    if not items:
        return ""

    return (
        items[0]
        .get("contentDetails", {})
        .get("relatedPlaylists", {})
        .get("uploads", "")
    )

def find_live_in_uploads(playlist_id, expected_channel_id, max_pages=10):
    token = ""

    for _ in range(max_pages):
        params = {
            "part": "contentDetails",
            "playlistId": playlist_id,
            "maxResults": 50,
        }
        if token:
            params["pageToken"] = token

        page = api_get("playlistItems", **params)

        ids = []
        for item in page.get("items", []):
            vid = item.get("contentDetails", {}).get("videoId")
            if vid:
                ids.append(vid)

        videos = inspect_video_ids(ids)
        by_id = {v.get("id"): v for v in videos}

        for vid in ids:
            video = by_id.get(vid)
            if video and is_usable_live(video, expected_channel_id):
                return video

        token = page.get("nextPageToken", "")
        if not token:
            break

    return None

def load_old():
    if not STREAMS_PATH.exists():
        return {}

    try:
        return json.loads(STREAMS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}

old = load_old()
out = {}

for key, cfg in CHANNELS.items():
    title = cfg["title"]
    channel_id = cfg["channel_id"]
    mode = cfg["mode"]

    previous_id = ""
    if isinstance(old.get(key), dict):
        previous_id = old[key].get("video_id", "") or ""

    # First validate an existing stream ID. This keeps long-running streams
    # without spending another search query if they are still live.
    live_video = validate_previous(previous_id, channel_id)

    if live_video is None:
        if mode == "search_live":
            live_video = search_current_live(channel_id)
        else:
            playlist_id = get_upload_playlist(channel_id)
            if playlist_id:
                live_video = find_live_in_uploads(
                    playlist_id,
                    channel_id,
                    max_pages=10,
                )

    if live_video:
        snippet = live_video.get("snippet", {})
        out[key] = {
            "title": title,
            "video_id": live_video["id"],
            "status": "live",
            "video_title": snippet.get("title", ""),
        }
        print(
            f"{key}: LIVE {live_video['id']} | "
            f"{snippet.get('title', '')}"
        )
    else:
        out[key] = {
            "title": title,
            "video_id": "",
            "status": "offline",
            "video_title": "",
        }
        print(f"{key}: no verified public embeddable livestream found")

STREAMS_PATH.write_text(
    json.dumps(out, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
