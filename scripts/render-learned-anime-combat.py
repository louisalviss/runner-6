#!/usr/bin/env python3
import argparse, json, math, random, subprocess
from pathlib import Path
import cv2, numpy as np


def decode_onset(path,sr=8000,step=.02,maxsec=90):
    r=subprocess.run(['ffmpeg','-nostdin','-v','error','-i',str(path),'-t',str(maxsec),'-ac','1','-ar',str(sr),'-f','f32le','-'],capture_output=True,check=True)
    x=np.frombuffer(r.stdout,dtype=np.float32); win=max(1,int(sr*step)); n=len(x)//win
    if n<10:return np.zeros(1),step
    x=x[:n*win].reshape(n,win); rms=np.sqrt(np.mean(x*x,axis=1)+1e-12); y=np.log(rms+1e-6); sm=np.convolve(y,np.ones(5)/5,mode='same'); onset=np.maximum(0,np.diff(sm,prepend=sm[0])); onset/=max(onset.max(),1e-8); return onset,step

def estimate_bpm(onset,step):
    best=(0,130.)
    for bpm in np.arange(90,181,.5):
        lag=max(1,int(round((60/bpm)/step)))
        if lag>=len(onset):continue
        score=float(np.dot(onset[lag:],onset[:-lag]))
        if score>best[0]:best=(score,float(bpm))
    return best[1]

def fit_canvas(frame,zoom=1.0,dx=0,dy=0,flash=0.0,color_boost=1.0,aberr=0):
    H,W=1920,1080; h,w=frame.shape[:2]; s=max(W/w,H/h); bg=cv2.resize(frame,(int(w*s)+2,int(h*s)+2),interpolation=cv2.INTER_CUBIC)
    y=max(0,(bg.shape[0]-H)//2); x=max(0,(bg.shape[1]-W)//2); bg=bg[y:y+H,x:x+W]; bg=cv2.GaussianBlur(bg,(0,0),32); bg=(bg.astype(np.float32)*.42).astype(np.uint8)
    base=W/w; fw=max(2,int(w*base*zoom)); fh=max(2,int(h*base*zoom)); fg=cv2.resize(frame,(fw,fh),interpolation=cv2.INTER_LANCZOS4)
    hsv=cv2.cvtColor(fg,cv2.COLOR_BGR2HSV).astype(np.float32); hsv[:,:,1]=np.clip(hsv[:,:,1]*color_boost,0,255); hsv[:,:,2]=np.clip((hsv[:,:,2]-128)*1.05+128,0,255); fg=cv2.cvtColor(hsv.astype(np.uint8),cv2.COLOR_HSV2BGR)
    if aberr:
        b,g,r=cv2.split(fg); M1=np.float32([[1,0,aberr],[0,1,0]]); M2=np.float32([[1,0,-aberr],[0,1,0]]); b=cv2.warpAffine(b,M1,(fw,fh),borderMode=cv2.BORDER_REFLECT); r=cv2.warpAffine(r,M2,(fw,fh),borderMode=cv2.BORDER_REFLECT); fg=cv2.merge((b,g,r))
    ox=(W-fw)//2+int(dx); oy=(H-fh)//2+int(dy); x0=max(0,ox); y0=max(0,oy); x1=min(W,ox+fw); y1=min(H,oy+fh)
    if x1>x0 and y1>y0: bg[y0:y1,x0:x1]=fg[y0-oy:y1-oy,x0-ox:x1-ox]
    if flash>0: bg=cv2.addWeighted(bg,1-flash,np.full_like(bg,255),flash,0)
    return bg

def read_frame(cap,t):
    cap.set(cv2.CAP_PROP_POS_MSEC,max(0,t)*1000); ok,f=cap.read()
    if not ok: raise RuntimeError(f'cannot decode frame at {t:.3f}s')
    return f

def choose_anchors(source_analysis,duration,n=6):
    imp=[float(x) for x in source_analysis.get('impact_times_sec',[]) if 1<x<duration-1]; chosen=[]
    for t in imp:
        if all(abs(t-c)>1.0 for c in chosen): chosen.append(t)
    if len(chosen)<n:
        for t in np.linspace(1,max(1,duration-1),n+2)[1:-1]:
            if all(abs(t-c)>.7 for c in chosen): chosen.append(float(t))
            if len(chosen)>=n:break
    chosen=sorted(chosen)[:n]
    while len(chosen)<n: chosen.append(duration*(len(chosen)+1)/(n+1))
    return chosen

def synth_sfx(path,duration,impacts,sr=48000):
    n=int(duration*sr); y=np.zeros(n,dtype=np.float32); rng=np.random.default_rng(7)
    for t,strength in impacts:
        i=int(t*sr); L=min(n-i,int(.28*sr))
        if L<=0:continue
        tt=np.arange(L)/sr; env=np.exp(-tt*18); bass=np.sin(2*np.pi*(72-25*tt)*tt)*env; noise=rng.normal(0,1,L)*np.exp(-tt*34); y[i:i+L]+=strength*(.34*bass+.10*noise)
    y=np.clip(y,-.85,.85); stereo=np.column_stack([y,y]); import wave
    with wave.open(str(path),'wb') as w: w.setnchannels(2); w.setsampwidth(2); w.setframerate(sr); w.writeframes((stereo*32767).astype(np.int16).tobytes())

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('source'); ap.add_argument('music'); ap.add_argument('grammar'); ap.add_argument('source_analysis'); ap.add_argument('output'); ap.add_argument('plan'); a=ap.parse_args()
    source=Path(a.source); music=Path(a.music); out=Path(a.output); out.parent.mkdir(parents=True,exist_ok=True); planp=Path(a.plan); planp.parent.mkdir(parents=True,exist_ok=True)
    grammar=json.loads(Path(a.grammar).read_text()); sa=json.loads(Path(a.source_analysis).read_text()); cap=cv2.VideoCapture(str(source)); sfps=cap.get(cv2.CAP_PROP_FPS) or 30; frames=int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0); sdur=frames/sfps
    onset,step=decode_onset(music); music_bpm=estimate_bpm(onset,step); ref_bpm=float(grammar.get('bpm_median',music_bpm)); bpm=max(100,min(170,music_bpm if 95<=music_bpm<=180 else ref_bpm)); beat=60/bpm; anchors=choose_anchors(sa,sdur,6)
    specs=[('clip',0,2.0,'hook'),('clip',1,3.0,'build'),('clip',2,1.0,'micro_setup'),('freeze',2,1.0,'anticipation'),('clip',3,.5,'impact_micro_1'),('clip',4,.5,'impact_micro_2'),('clip',3,2.0,'impact_release'),('clip',4,3.0,'escalation_1'),('clip',5,3.0,'escalation_2'),('freeze',5,1.0,'pre_finisher_hold'),('clip',4,.5,'finisher_micro_1'),('clip',5,.5,'finisher_micro_2'),('clip',5,3.0,'finisher'),('freeze',5,2.0,'loop_hold')]
    duration=sum(x[2] for x in specs)*beat; fps=30; total=int(round(duration*fps)); duration=total/fps; starts=[]; acc=0
    for _,_,beats,_ in specs: starts.append(acc); acc+=beats*beat
    main_impact=starts[4]; finisher=starts[10]; candidates=[i for i,v in enumerate(onset) if 5<=i*step<=70]; drop_t=(max(candidates,key=lambda i:onset[i])*step) if candidates else main_impact; audio_start=max(0,drop_t-main_impact)
    temp=out.with_suffix('.silent.avi'); writer=cv2.VideoWriter(str(temp),cv2.VideoWriter_fourcc(*'MJPG'),fps,(1080,1920)); rng=random.Random(17); impacts=[]; event_meta=[]; prev=None; out_i=0
    for kind,ai,beats,role in specs:
        odur=beats*beat; nf=max(1,int(round(odur*fps))); anchor=anchors[ai]
        if kind=='freeze': src0=anchor; srcspan=0
        else:
            speed=1.35 if 'micro' in role else (1.18 if 'impact' in role or 'finisher' in role else .92); srcspan=odur*speed; src0=max(0,min(sdur-srcspan-0.05,anchor-srcspan*.45))
        event_meta.append({'role':role,'kind':kind,'start_sec':round(out_i/fps,3),'duration_sec':round(nf/fps,3),'source_anchor_sec':round(anchor,3),'source_start_sec':round(src0,3)}); impact_role=('impact' in role or 'finisher' in role)
        if role in ('impact_micro_1','finisher_micro_1'): impacts.append((out_i/fps,1.0 if 'finisher' in role else .86))
        for j in range(nf):
            p=j/max(1,nf-1); st=anchor if kind=='freeze' else src0+p*srcspan; f=read_frame(cap,st); zoom=1.; dx=dy=0; flash=0; cb=1.03; aberr=0
            if kind=='freeze': zoom=1.02+.07*p
            if impact_role:
                zoom=1.04+.08*min(1,p*2)
                if j<max(2,int(.13*fps)):
                    amp=18*(1-j/max(2,int(.13*fps))); dx=rng.randint(-int(amp),int(amp)); dy=rng.randint(-int(amp),int(amp)); aberr=3
                if j<2: flash=.30 if 'micro_1' in role else .18
                cb=1.28
            elif role.startswith('escalation'): zoom=1.015+.035*p; cb=1.12
            canvas=fit_canvas(f,zoom,dx,dy,flash,cb,aberr)
            if prev is not None and impact_role and j<3: canvas=cv2.addWeighted(canvas,.82,prev,.18,0)
            writer.write(canvas); prev=canvas; out_i+=1
    writer.release(); cap.release(); sfx=out.with_suffix('.sfx.wav'); synth_sfx(sfx,duration,impacts)
    cmd=['ffmpeg','-nostdin','-hide_banner','-y','-i',str(temp),'-ss',f'{audio_start:.3f}','-i',str(music),'-i',str(sfx),'-filter_complex',f'[1:a]atrim=duration={duration:.3f},asetpts=PTS-STARTPTS,volume=0.96,loudnorm=I=-12.5:TP=-1.0:LRA=6[m];[2:a]volume=0.75[s];[m][s]amix=inputs=2:duration=first:dropout_transition=0,alimiter=limit=.96[a]','-map','0:v','-map','[a]','-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p','-r',str(fps),'-c:a','aac','-b:a','192k','-movflags','+faststart','-t',f'{duration:.3f}',str(out)]
    rr=subprocess.run(cmd); temp.unlink(missing_ok=True); sfx.unlink(missing_ok=True)
    if rr.returncode!=0 or not out.exists() or out.stat().st_size<500000: raise SystemExit('render failed')
    meta={'status':'success','output':str(out),'bytes':out.stat().st_size,'duration_sec':round(duration,3),'fps':fps,'size':'1080x1920','music_bpm_estimate':round(bpm,2),'beat_sec':round(beat,4),'reference_bpm_median':grammar.get('bpm_median'),'reference_median_cut_interval_sec':grammar.get('median_cut_interval_sec'),'audio_start_sec':round(audio_start,3),'aligned_audio_drop_sec':round(drop_t,3),'main_impact_sec':round(main_impact,3),'finisher_sec':round(finisher,3),'source_anchors_sec':[round(x,3) for x in anchors],'events':event_meta,'effects':'hold/zoom + short impact shake/flash/chromatic + localized saturation; no copied text/logo/assets','grammar_source':'3 viral anime+phonk references'}
    planp.write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(meta,ensure_ascii=False))
if __name__=='__main__': main()
