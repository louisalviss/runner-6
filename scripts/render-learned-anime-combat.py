#!/usr/bin/env python3
import argparse, json, math, random, subprocess, wave
from pathlib import Path
import cv2, numpy as np

W,H=1080,1920
FPS=30
TARGET=20.0


def probe(path):
    r=subprocess.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)],capture_output=True,text=True,check=True)
    return json.loads(r.stdout)


def source_duration(path):
    p=probe(path)
    return float(p['format']['duration'])


def choose_window(sa, duration, target=TARGET):
    impacts=sorted(float(x) for x in sa.get('impact_times_sec',[]) if 0.5 < float(x) < duration-0.5)
    if duration <= target+0.2:
        return 0.0, max(1.0,duration-0.05), impacts
    candidates=set([0.0,max(0.0,duration-target)])
    for t in impacts:
        for lead in (0.25,0.6,1.0,2.0):
            candidates.add(max(0.0,min(duration-target,t-lead)))
    best=None
    for s in sorted(candidates):
        e=s+target
        inside=[t for t in impacts if s+0.15 <= t <= e-0.25]
        if inside:
            first=inside[0]-s; last=inside[-1]-s
            clusters=1
            for a,b in zip(inside,inside[1:]):
                if b-a>1.5: clusters+=1
            spread=(last-first)/target
            score=len(inside)*2.0 + min(clusters,6)*0.7 + min(spread,1.0)*1.2 - max(0,first-1.2)*0.25
        else:
            score=-10
        if best is None or score>best[0]: best=(score,s,inside)
    return round(best[1],3), target, best[2]


def cluster_impacts(times, start, max_events=5):
    rel=[t-start for t in times if start <= t <= start+TARGET]
    groups=[]
    for t in rel:
        if not groups or t-groups[-1][-1] > 1.25: groups.append([t])
        else: groups[-1].append(t)
    reps=[g[len(g)//2] for g in groups]
    if len(reps)<=max_events: return reps
    idx=np.linspace(0,len(reps)-1,max_events).round().astype(int)
    return [reps[i] for i in sorted(set(idx.tolist()))]


def extract_window(source, out, start, duration):
    cmd=['ffmpeg','-nostdin','-hide_banner','-y','-ss',f'{start:.3f}','-i',str(source),'-t',f'{duration:.3f}',
         '-map','0:v:0','-map','0:a?','-vf',f'fps={FPS}','-c:v','libx264','-preset','veryfast','-crf','18','-pix_fmt','yuv420p',
         '-c:a','aac','-b:a','160k','-movflags','+faststart',str(out)]
    subprocess.run(cmd,check=True)


def fit_canvas(frame, zoom=1.0, dx=0, dy=0, flash=0.0, sat=1.0):
    h,w=frame.shape[:2]
    sb=max(W/w,H/h)
    bg=cv2.resize(frame,(max(W,int(w*sb)),max(H,int(h*sb))),interpolation=cv2.INTER_AREA)
    y=(bg.shape[0]-H)//2; x=(bg.shape[1]-W)//2
    bg=bg[y:y+H,x:x+W]
    bg=cv2.GaussianBlur(bg,(0,0),28)
    bg=(bg.astype(np.float32)*0.38).astype(np.uint8)

    sf=(W/w)*zoom
    fw=max(2,int(round(w*sf))); fh=max(2,int(round(h*sf)))
    fg=cv2.resize(frame,(fw,fh),interpolation=cv2.INTER_LANCZOS4)
    if abs(sat-1.0)>1e-3:
        hsv=cv2.cvtColor(fg,cv2.COLOR_BGR2HSV).astype(np.float32)
        hsv[:,:,1]=np.clip(hsv[:,:,1]*sat,0,255)
        fg=cv2.cvtColor(hsv.astype(np.uint8),cv2.COLOR_HSV2BGR)
    ox=(W-fw)//2+int(dx); oy=(H-fh)//2+int(dy)
    x0=max(0,ox); y0=max(0,oy); x1=min(W,ox+fw); y1=min(H,oy+fh)
    if x1>x0 and y1>y0:
        bg[y0:y1,x0:x1]=fg[y0-oy:y1-oy,x0-ox:x1-ox]
    if flash>0:
        bg=cv2.addWeighted(bg,1-flash,np.full_like(bg,255),flash,0)
    return bg


def synth_sfx(path,duration,events,sr=48000):
    n=int(duration*sr); y=np.zeros(n,dtype=np.float32); rng=np.random.default_rng(20260821)
    for k,t in enumerate(events):
        i=int(t*sr); L=min(n-i,int(.22*sr))
        if L<=0: continue
        tt=np.arange(L)/sr
        env=np.exp(-tt*22)
        f0=62 if k==len(events)-1 else 72
        bass=np.sin(2*np.pi*(f0-18*tt)*tt)*env
        noise=rng.normal(0,1,L)*np.exp(-tt*38)
        strength=.72 if k==len(events)-1 else .52
        y[i:i+L]+=strength*(.32*bass+.07*noise)
    y=np.clip(y,-.8,.8)
    stereo=np.column_stack([y,y])
    with wave.open(str(path),'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(sr); w.writeframes((stereo*32767).astype(np.int16).tobytes())


def has_audio(path):
    p=probe(path)
    return any(s.get('codec_type')=='audio' for s in p.get('streams',[]))


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('source'); ap.add_argument('music'); ap.add_argument('grammar'); ap.add_argument('source_analysis'); ap.add_argument('output'); ap.add_argument('plan')
    a=ap.parse_args()
    source=Path(a.source); music=Path(a.music); out=Path(a.output); planp=Path(a.plan)
    out.parent.mkdir(parents=True,exist_ok=True); planp.parent.mkdir(parents=True,exist_ok=True)
    grammar=json.loads(Path(a.grammar).read_text()); sa=json.loads(Path(a.source_analysis).read_text())
    sdur=source_duration(source)
    start,duration,inside=choose_window(sa,sdur,TARGET)
    emphasis=cluster_impacts(inside,start,5)
    emphasis=[t for t in emphasis if .25<t<duration-.25][:5]

    window=out.with_suffix('.window.mp4'); silent=out.with_suffix('.silent.avi'); sfx=out.with_suffix('.sfx.wav')
    extract_window(source,window,start,duration)
    cap=cv2.VideoCapture(str(window)); writer=cv2.VideoWriter(str(silent),cv2.VideoWriter_fourcc(*'MJPG'),FPS,(W,H))
    rng=random.Random(20260821); frame_i=0; prev=None
    while True:
        ok,f=cap.read()
        if not ok: break
        t=frame_i/FPS
        zoom=1.0; dx=dy=0; flash=0.0; sat=1.0
        nearest=None; dist=99
        for ev in emphasis:
            d=abs(t-ev)
            if d<dist: nearest=ev; dist=d
        if nearest is not None:
            final=(nearest==emphasis[-1]) if emphasis else False
            if dist <= .10:
                q=max(0.0,1-dist/.10)
                zoom=1.0 + (0.018 if final else 0.012)*q
                amp=(7 if final else 5)*q
                dx=rng.randint(-max(0,int(amp)),max(0,int(amp))) if amp>=1 else 0
                dy=rng.randint(-max(0,int(amp)),max(0,int(amp))) if amp>=1 else 0
                flash=(0.11 if final else 0.065)*q
                sat=1.0 + (0.08 if final else 0.045)*q
        canvas=fit_canvas(f,zoom,dx,dy,flash,sat)
        if prev is not None and nearest is not None and dist <= 1/FPS:
            canvas=cv2.addWeighted(canvas,.9,prev,.1,0)
        writer.write(canvas); prev=canvas; frame_i+=1
    cap.release(); writer.release()
    duration=frame_i/FPS
    if frame_i < int(17*FPS): raise SystemExit(f'window too short: {duration:.2f}s')
    synth_sfx(sfx,duration,emphasis)

    inputs=['-i',str(silent),'-stream_loop','-1','-i',str(music)]
    if has_audio(window):
        inputs += ['-i',str(window),'-i',str(sfx)]
        filt=(f'[1:a]atrim=duration={duration:.3f},asetpts=PTS-STARTPTS,volume=.88,loudnorm=I=-13:TP=-1.2:LRA=7[m];'
              f'[2:a]atrim=duration={duration:.3f},asetpts=PTS-STARTPTS,volume=.16[src];[3:a]volume=.58[fx];'
              f'[m][src][fx]amix=inputs=3:duration=first:dropout_transition=0,alimiter=limit=.96[a]')
    else:
        inputs += ['-i',str(sfx)]
        filt=(f'[1:a]atrim=duration={duration:.3f},asetpts=PTS-STARTPTS,volume=.90,loudnorm=I=-13:TP=-1.2:LRA=7[m];'
              f'[2:a]volume=.58[fx];[m][fx]amix=inputs=2:duration=first:dropout_transition=0,alimiter=limit=.96[a]')
    cmd=['ffmpeg','-nostdin','-hide_banner','-y']+inputs+['-filter_complex',filt,'-map','0:v','-map','[a]',
         '-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p','-r',str(FPS),'-c:a','aac','-b:a','192k','-movflags','+faststart','-t',f'{duration:.3f}',str(out)]
    subprocess.run(cmd,check=True)
    if not out.exists() or out.stat().st_size<800000: raise SystemExit('render failed')
    meta={
      'status':'success','mode':'continuous_choreography','output':str(out),'bytes':out.stat().st_size,
      'duration_sec':round(duration,3),'fps':FPS,'size':'1080x1920','source_duration_sec':round(sdur,3),
      'selected_source_window':{'start_sec':round(start,3),'end_sec':round(start+duration,3)},
      'source_impacts_in_window':[round(t-start,3) for t in inside],
      'impact_emphasis_sec':[round(t,3) for t in emphasis],
      'impact_emphasis_count':len(emphasis),
      'post_edit_cuts_added':0,
      'post_edit_freezes_added':0,
      'visual_policy':'preserve full-width choreography; no constant zoom; max 5 localized impact accents; no micro-cut montage',
      'music_policy':'audio extracted from top-ranked viral reference; source fight audio retained quietly for contact readability',
      'grammar_reference_count':grammar.get('reference_count'),
      'grammar_core_rules':grammar.get('core_rules',grammar.get('rules',[]))
    }
    planp.write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(meta,ensure_ascii=False))
    window.unlink(missing_ok=True); silent.unlink(missing_ok=True); sfx.unlink(missing_ok=True)

if __name__=='__main__': main()
