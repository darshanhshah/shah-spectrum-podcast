#!/usr/bin/env python3
"""Add one episode to feed.xml (newest first).
Usage: add_episode.py EPISODE.mp3 "Title" "Description" [--date "2026-10-17T07:00:00+08:00"] [--number N]
The mp3 must already be in episodes/. Audio is labelled as AI-generated in the description."""
import sys, os, subprocess, argparse, datetime, html, re
ap=argparse.ArgumentParser(); ap.add_argument('mp3'); ap.add_argument('title'); ap.add_argument('desc')
ap.add_argument('--date'); ap.add_argument('--number',type=int); a=ap.parse_args()
root=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
base='https://darshanhshah.github.io/shah-spectrum-podcast'
path=os.path.join(root,'episodes',os.path.basename(a.mp3))
size=os.path.getsize(path)
dur=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',path]).decode().strip())
d=datetime.datetime.fromisoformat(a.date) if a.date else datetime.datetime.now(datetime.timezone.utc)
pub=d.strftime('%a, %d %b %Y %H:%M:%S %z')
guid=os.path.basename(path)
e=html.escape
item=f'''    <item>
      <title>{e(a.title)}</title>
      <description>{e(a.desc)}</description>
      <itunes:summary>{e(a.desc)}</itunes:summary>
      <pubDate>{pub}</pubDate>
      <guid isPermaLink="false">{e(guid)}</guid>
      <enclosure url="{base}/episodes/{e(os.path.basename(path))}" length="{size}" type="audio/mpeg"/>
      <itunes:duration>{int(dur)}</itunes:duration>
      <itunes:explicit>false</itunes:explicit>
      <itunes:episodeType>full</itunes:episodeType>{f"{chr(10)}      <itunes:episode>{a.number}</itunes:episode>" if a.number else ""}
    </item>
'''
fp=os.path.join(root,'feed.xml'); s=open(fp,encoding='utf-8').read()
marker='<!-- EPISODES: newest first. Add items with scripts/add_episode.py -->\n'
s=s.replace(marker,marker+item,1); open(fp,'w',encoding='utf-8').write(s); print('added',guid,int(dur),'s')
