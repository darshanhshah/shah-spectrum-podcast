#!/usr/bin/env python3
"""Make time-synced subtitles (SRT and VTT) for one episode from its voice text and finished mp3.
Usage: make_subtitles.py EPISODE.mp3 VOICE.txt [--out transcripts/NAME]
Timing: the voice text has known pause markers <#s#>. Speech time = audio length minus those pauses, shared out by character count,
then each cue boundary snaps to the nearest real silence found by ffmpeg (within 0.7 s). Cues are sentence level, readable length."""
import sys, re, subprocess, argparse, os
ap=argparse.ArgumentParser(); ap.add_argument('mp3'); ap.add_argument('txt'); ap.add_argument('--out'); a=ap.parse_args()
raw=open(a.txt,encoding='utf-8').read()
dur=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',a.mp3]).decode())
# silences
r=subprocess.run(['ffmpeg','-i',a.mp3,'-af','silencedetect=noise=-33dB:d=0.22','-f','null','-'],capture_output=True,text=True).stderr
st=[float(x) for x in re.findall(r'silence_start: ([\d.]+)',r)]; en=[float(x) for x in re.findall(r'silence_end: ([\d.]+)',r)]
sil=[((s+e)/2) for s,e in zip(st,en)]
# pieces: (kind,value)
parts=re.split(r'<#([\d.]+)#>',raw)
items=[]  # ('t',text) or ('p',seconds)
for i,p in enumerate(parts):
    if i%2: items.append(('p',float(p)))
    else:
        for line in p.split('\n'):
            if line.strip(): items.append(('t',line.strip()))
# sentences, each with trailing pause
sents=[]  # [text, pause_after]
for k,v in items:
    if k=='t':
        for s in re.split(r'(?<=[.!?:])\s+',v):
            if s.strip(): sents.append([s.strip(),0.0])
    elif sents: sents[-1][1]+=v
# split long sentences into cues (<=84 chars) at commas / spaces
def split(s,n=84):
    if len(s)<=n: return [s]
    out=[];cur=''
    for w in s.split(' '):
        if cur and len(cur)+1+len(w)>n and (cur.endswith(',') or len(cur)>n*0.7): out.append(cur);cur=w
        else: cur=(cur+' '+w).strip()
    if cur: out.append(cur)
    return out
cues=[]  # [text, weight, pause_after]
for t,p in sents:
    ch=split(t)
    for j,c in enumerate(ch): cues.append([c,len(c),p if j==len(ch)-1 else 0.0])
pause_total=sum(c[2] for c in cues); speech=max(dur-pause_total-0.3,1)
def syl(t):
    return max(1,sum(max(1,len(re.findall(r'[aeiouy]+',w.lower()))) for w in re.findall(r"[A-Za-z']+",t)))+0.3*len(re.findall(r'[,;:]',t))
for c in cues: c[1]=syl(c[0])
tot=sum(c[1] for c in cues); t=0.15; bounds=[]
for c in cues:
    s0=t; t+=speech*c[1]/tot; e0=t; t+=c[2]; bounds.append([s0,e0])
# re-anchor: match each cue end to a real silence (monotonic, minimum total distance), then stretch time between anchors
# silence intervals as (start,end)
ivs=list(zip(st,en))
n=len(cues); m=len(ivs); INF=1e9; NOMATCH=0.9
pred=[bounds[i][1]+(cues[i][2]/2) for i in range(n-1)]   # predicted middle of the gap after cue i
# dp[i][j]: best cost for first i boundaries, using silences < j
import functools
dp=[[0.0]*(m+1) for _ in range(n)]; back=[[None]*(m+1) for _ in range(n)]
for i in range(1,n):
    for j in range(m+1):
        # boundary i-1 unmatched
        best=dp[i-1][j]+NOMATCH; bk=('u',j)
        if j>0:
            d=abs(pred[i-1]-(ivs[j-1][0]+ivs[j-1][1])/2)
            c1=dp[i-1][j-1]+min(d,NOMATCH*1.5) if d<2.0 else INF
            if c1<best: best=c1; bk=('m',j-1)
            # skip silence j-1 (use earlier)
            c2=dp[i][j-1]
            if c2<best: best=c2; bk=('s',j-1)
        dp[i][j]=best; back[i][j]=bk
# backtrack
anch={}; i=n-1; j=m
while i>0:
    k,jj=back[i][j]
    if k=='m': anch[i-1]=(ivs[j-1][0]+ivs[j-1][1])/2; i-=1; j=jj
    elif k=='u': i-=1
    else: j=jj
# piecewise linear remap of the proportional timeline using anchors (anchor = mid of gap after cue i)
pts=[(0.0,0.0)]+[(pred[i],anch[i]) for i in sorted(anch)]+[(bounds[-1][1]+0.0,dur-0.3)]
pts=[pts[0]]+[q for k,q in enumerate(pts[1:],1) if q[0]>pts[k-1][0] and q[1]>pts[k-1][1]]
def remap(x):
    for (x0,y0),(x1,y1) in zip(pts,pts[1:]):
        if x<=x1: return y0+(x-x0)*(y1-y0)/(x1-x0)
    return pts[-1][1]
nb=[]
for i in range(n):
    s0=remap(bounds[i][0]); e0=remap(bounds[i][1]); nb.append([s0,e0])
bounds=nb
for i in range(len(bounds)):
    s0,e0=bounds[i]
    if i+1<len(bounds): e0=min(e0,bounds[i+1][0]) if bounds[i+1][0]>s0+0.5 else e0
    bounds[i]=[s0,min(max(e0,s0+0.6),dur)]
def ts(x,c):
    h=int(x//3600);m=int(x%3600//60);s=x%60
    return f'{h:02d}:{m:02d}:{s:06.3f}'.replace('.',c)
clean=lambda s:re.sub(r'\s+',' ',s)
srt=''.join(f'{i+1}\n{ts(b[0],",")} --> {ts(b[1],",")}\n{clean(c[0])}\n\n' for i,(c,b) in enumerate(zip(cues,bounds)))
vtt='WEBVTT\n\n'+''.join(f'{ts(b[0],".")} --> {ts(b[1],".")}\n{clean(c[0])}\n\n' for c,b in zip(cues,bounds))
out=a.out or os.path.join('transcripts',os.path.splitext(os.path.basename(a.mp3))[0])
os.makedirs(os.path.dirname(out) or '.',exist_ok=True)
open(out+'.srt','w',encoding='utf-8').write(srt); open(out+'.vtt','w',encoding='utf-8').write(vtt)
print('cues',len(cues),'dur',round(dur,1),'silences',len(sil),'->',out+'.srt/.vtt')
