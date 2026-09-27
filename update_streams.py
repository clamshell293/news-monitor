import json
import os
import urllib.parse
import urllib.request
from pathlib import Path
from datetime import datetime, timezone, timedelta

API_KEY=os.environ.get("YOUTUBE_API_KEY","").strip()
if not API_KEY:
    raise SystemExit("Missing YOUTUBE_API_KEY")

BASE="https://www.googleapis.com/youtube/v3"
CHANNELS_PATH=Path("channels.json")
STREAMS_PATH=Path("streams.json")
OFFLINE_SEARCH_INTERVAL=timedelta(hours=6)

def api_get(endpoint, **params):
    params["key"]=API_KEY
    url=f"{BASE}/{endpoint}?"+urllib.parse.urlencode(params)
    req=urllib.request.Request(url,headers={"User-Agent":"news-monitor-v5.1"})
    with urllib.request.urlopen(req,timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

def resolve_channel_id(ch):
    cid=ch.get("channel_id","").strip()
    if cid:
        return cid
    handle=ch.get("handle","").strip().lstrip("@")
    if not handle:
        return ""
    data=api_get("channels",part="id",forHandle=handle,maxResults=1)
    items=data.get("items",[])
    return items[0]["id"] if items else ""

def videos(ids):
    if not ids:return []
    return api_get(
        "videos",
        part="snippet,status,liveStreamingDetails",
        id=",".join(ids),
        maxResults=50
    ).get("items",[])

def valid(v,cid):
    s=v.get("snippet",{}); st=v.get("status",{})
    return (
        s.get("channelId")==cid
        and s.get("liveBroadcastContent")=="live"
        and st.get("privacyStatus")=="public"
        and st.get("embeddable",True) is not False
    )

def search_live(cid):
    data=api_get(
        "search",
        part="snippet",
        channelId=cid,
        eventType="live",
        type="video",
        maxResults=10,
        order="date"
    )
    ids=[x.get("id",{}).get("videoId") for x in data.get("items",[])]
    ids=[x for x in ids if x]
    byid={v.get("id"):v for v in videos(ids)}
    for vid in ids:
        v=byid.get(vid)
        if v and valid(v,cid):
            return v
    return None

def uploads_live(cid,max_pages=5):
    c=api_get("channels",part="contentDetails",id=cid,maxResults=1).get("items",[])
    if not c:return None
    pl=c[0].get("contentDetails",{}).get("relatedPlaylists",{}).get("uploads","")
    if not pl:return None
    token=""
    for _ in range(max_pages):
        p={"part":"contentDetails","playlistId":pl,"maxResults":50}
        if token:p["pageToken"]=token
        page=api_get("playlistItems",**p)
        ids=[x.get("contentDetails",{}).get("videoId") for x in page.get("items",[])]
        ids=[x for x in ids if x]
        byid={v.get("id"):v for v in videos(ids)}
        for vid in ids:
            v=byid.get(vid)
            if v and valid(v,cid):
                return v
        token=page.get("nextPageToken","")
        if not token:break
    return None

def parse_time(s):
    if not s:return None
    try:
        return datetime.fromisoformat(s.replace("Z","+00:00"))
    except Exception:
        return None

def now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

channels=json.loads(CHANNELS_PATH.read_text(encoding="utf-8")).get("channels",[])
yt=[c for c in channels if c.get("source")=="youtube"]

try:
    old=json.loads(STREAMS_PATH.read_text(encoding="utf-8"))
except Exception:
    old={}

# Resolve handles first.
resolved={}
for c in yt:
    try:
        resolved[c["id"]]=resolve_channel_id(c)
        print(c["id"],"channel",resolved[c["id"]])
    except Exception as e:
        print(c["id"],"channel resolve failed:",e)
        resolved[c["id"]]=""

# Validate all existing live IDs in batches.
previous_ids=[]
owners={}
for c in yt:
    vid=(old.get(c["id"]) or {}).get("video_id","")
    if vid:
        previous_ids.append(vid);owners[vid]=c

valid_old={}
for i in range(0,len(previous_ids),50):
    try:
        for v in videos(previous_ids[i:i+50]):
            vid=v.get("id"); c=owners.get(vid)
            cid=resolved.get(c["id"],"") if c else ""
            if c and cid and valid(v,cid):
                valid_old[c["id"]]=v
    except Exception as e:
        print("validation batch failed:",e)

out={}
now=datetime.now(timezone.utc)

for c in yt:
    cid=resolved.get(c["id"],"")
    oldrec=old.get(c["id"]) or {}
    v=valid_old.get(c["id"])
    searched=False

    if not cid:
        out[c["id"]]={
            "video_id":"",
            "status":"offline",
            "video_title":"",
            "last_search":oldrec.get("last_search","")
        }
        continue

    if not v:
        last=parse_time(oldrec.get("last_search",""))
        should_search=(last is None) or (now-last>=OFFLINE_SEARCH_INTERVAL)

        if should_search:
            searched=True
            try:
                if c.get("discovery")=="uploads":
                    v=uploads_live(cid)
                else:
                    v=search_live(cid)
            except Exception as e:
                print(c["id"],"lookup failed:",e)
                v=None

    if v:
        out[c["id"]]={
            "video_id":v["id"],
            "status":"live",
            "video_title":v.get("snippet",{}).get("title",""),
            "last_search":now_iso() if searched else oldrec.get("last_search","")
        }
        print(c["id"],"LIVE",v["id"])
    else:
        out[c["id"]]={
            "video_id":"",
            "status":"offline",
            "video_title":"",
            "last_search":now_iso() if searched else oldrec.get("last_search","")
        }
        print(c["id"],"OFFLINE")

STREAMS_PATH.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
