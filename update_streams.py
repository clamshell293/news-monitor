import json, os, urllib.parse, urllib.request
from pathlib import Path

API_KEY=os.environ.get('YOUTUBE_API_KEY','').strip()
if not API_KEY: raise SystemExit('Missing YOUTUBE_API_KEY')
BASE='https://www.googleapis.com/youtube/v3'
channels=json.loads(Path('channels.json').read_text(encoding='utf-8')).get('channels',[])
yt=[c for c in channels if c.get('source')=='youtube']
try: old=json.loads(Path('streams.json').read_text(encoding='utf-8'))
except Exception: old={}

def api_get(endpoint, **params):
    params['key']=API_KEY
    url=f"{BASE}/{endpoint}?"+urllib.parse.urlencode(params)
    req=urllib.request.Request(url,headers={'User-Agent':'news-monitor-v5'})
    with urllib.request.urlopen(req,timeout=30) as r:
        return json.loads(r.read().decode('utf-8'))

def videos(ids):
    if not ids:return []
    return api_get('videos',part='snippet,status,liveStreamingDetails',id=','.join(ids),maxResults=50).get('items',[])

def valid(v,cid):
    s=v.get('snippet',{}); st=v.get('status',{})
    return s.get('channelId')==cid and s.get('liveBroadcastContent')=='live' and st.get('privacyStatus')=='public' and st.get('embeddable',True) is not False

def search_live(cid):
    d=api_get('search',part='snippet',channelId=cid,eventType='live',type='video',maxResults=10,order='date')
    ids=[x.get('id',{}).get('videoId') for x in d.get('items',[])]
    ids=[x for x in ids if x]
    by={v.get('id'):v for v in videos(ids)}
    for vid in ids:
        v=by.get(vid)
        if v and valid(v,cid): return v
    return None

def uploads_live(cid,max_pages=5):
    c=api_get('channels',part='contentDetails',id=cid,maxResults=1).get('items',[])
    if not c:return None
    pl=c[0].get('contentDetails',{}).get('relatedPlaylists',{}).get('uploads','')
    if not pl:return None
    token=''
    for _ in range(max_pages):
        p={'part':'contentDetails','playlistId':pl,'maxResults':50}
        if token:p['pageToken']=token
        page=api_get('playlistItems',**p)
        ids=[x.get('contentDetails',{}).get('videoId') for x in page.get('items',[])]
        ids=[x for x in ids if x]
        by={v.get('id'):v for v in videos(ids)}
        for vid in ids:
            v=by.get(vid)
            if v and valid(v,cid): return v
        token=page.get('nextPageToken','')
        if not token:break
    return None

previous=[]; owners={}
for c in yt:
    vid=(old.get(c['id']) or {}).get('video_id','')
    if vid: previous.append(vid); owners[vid]=c
valid_old={}
for i in range(0,len(previous),50):
    for v in videos(previous[i:i+50]):
        c=owners.get(v.get('id'))
        if c and valid(v,c['channel_id']): valid_old[c['id']]=v

out={}
for c in yt:
    v=valid_old.get(c['id'])
    if not v:
        try:
            v=uploads_live(c['channel_id']) if c.get('discovery')=='uploads' else search_live(c['channel_id'])
        except Exception as e:
            print(c['id'],'lookup failed:',e); v=None
    if v:
        out[c['id']]={'video_id':v['id'],'status':'live','video_title':v.get('snippet',{}).get('title','')}
        print(c['id'],'LIVE',v['id'])
    else:
        out[c['id']]={'video_id':'','status':'offline','video_title':''}
        print(c['id'],'OFFLINE')
Path('streams.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
