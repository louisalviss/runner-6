#!/usr/bin/env python3
import argparse, json, math, subprocess
from pathlib import Path
import numpy as np

TARGET = 20.0
FPS = 30


def run(cmd):
    return subprocess.run(cmd, check=True, capture_output=True, text=True)


def probe(path):
    r = run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)])
    return json.loads(r.stdout)


def duration(path):
    return float(probe(path)['format']['duration'])


def decode_audio(path, sr=8000):
    r = subprocess.run(['ffmpeg','-nostdin','-v','error','-i',str(path),'-vn','-ac','1','-ar',str(sr),'-f','f32le','-'],capture_output=True,check=True)
    return np.frombuffer(r.stdout,dtype=np.float32), sr


def audio_arrays(path, step=0.02):
    samples, sr = decode_audio(path)
    win=max(1,int(sr*step)); n=len(samples)//win
    x=samples[:n*win].reshape(n,win)
    rms=np.sqrt(np.mean(x*x,axis=1)+1e-12)
    log=np.log(rms+1e-6)
    smooth=np.convolve(log,np.ones(5)/5,mode='same')
    onset=np.maximum(0,np.diff(smooth,prepend=smooth[0]))
    if onset.max()>0: onset=onset/onset.max()
    return rms,onset,step,len(samples)/sr


def get_impacts(sa, dur):
    impacts=sorted(float(x) for x in sa.get('impact_times_sec',[]) if 0.5<float(x)<dur-0.5)
    if len(impacts)>=3:
        return impacts
    cuts=sorted(float(x) for x in sa.get('visual',{}).get('cut_times_sec',[]) if 0.5<float(x)<dur-0.5)
    return cuts


def get_cuts(sa, dur):
    return sorted(float(x) for x in sa.get('visual',{}).get('cut_times_sec',[]) if 0.0<float(x)<dur)


def select_window(sa, dur):
    impacts=get_impacts(sa,dur); cuts=get_cuts(sa,dur)
    if dur <= TARGET + .1:
        return 0.0, impacts
    starts=set([0.0, max(0.0,dur-TARGET)])
    for t in impacts:
        for off in (0.6,1.0,1.5,2.0,3.0):
            s=max(0.0,min(dur-TARGET,t-off)); starts.add(round(s,3))
    for s in np.arange(0,max(.01,dur-TARGET),1.0): starts.add(round(float(s),3))
    winner=None
    for s in sorted(starts):
        e=s+TARGET
        rel=[t-s for t in impacts if s<=t<=e]
        cs=[t-s for t in cuts if s<=t<=e]
        if not rel: continue
        early=sum(1 for x in rel if x<=3.0)
        middle=sum(1 for x in rel if 5.0<=x<=14.5)
        late=sum(1 for x in rel if x>=14.0)
        # Reward a distributed action sequence; avoid using cut density as the main objective.
        bins=len(set(min(4,int(x//4)) for x in rel))
        cut_pen=max(0,len(cs)-24)*0.08 + max(0,5-len(cs))*0.05
        score=3.2*min(len(rel),8)+2.4*early+1.3*middle+2.7*late+1.1*bins-cut_pen
        # Slightly prefer windows with a little setup before first impact and aftermath after last.
        if rel:
            if .5<=min(rel)<=2.5: score+=1.2
            if 15.0<=max(rel)<=19.3: score+=1.5
        cand=(score,-abs(len(cs)-12),s,rel)
        if winner is None or cand>winner: winner=cand
    if winner is None:
        s=max(0.0,min(dur-TARGET,dur*.35)); return s,[]
    return float(winner[2]), [round(x,3) for x in winner[3]]


def select_music_window(music, source_impacts):
    rms,onset,step,dur=audio_arrays(music)
    w=int(round(TARGET/step))
    if len(rms)<w+1: raise SystemExit('music too short')
    rmed=float(np.median(rms)); rstd=float(np.std(rms)+1e-9)
    best=None
    max_start=max(0.0,dur-TARGET-.05)
    # 100 ms search: enough phase freedom to align a few meaningful impacts without warping video.
    for start in np.arange(0,max_start+.001,0.10):
        i=int(round(start/step)); rr=rms[i:i+w]; oo=onset[i:i+w]
        if len(rr)<w: continue
        energy=float((np.mean(rr)-rmed)/rstd)
        sync=[]
        for t in source_impacts:
            if t<0 or t>=TARGET: continue
            idx=i+int(round(t/step)); lo=max(0,idx-4); hi=min(len(onset),idx+5)
            sync.append(float(onset[lo:hi].max()) if hi>lo else 0.0)
        sync_score=float(np.mean(sorted(sync,reverse=True)[:5])) if sync else 0.0
        late_bonus=0.0
        late=[x for x in source_impacts if x>=14]
        if late:
            idx=i+int(round(late[-1]/step)); lo=max(0,idx-5); hi=min(len(onset),idx+6)
            late_bonus=float(onset[lo:hi].max()) if hi>lo else 0.0
        score=energy+2.8*sync_score+0.8*late_bonus
        if start<5: score-=0.15
        cand=(score,start,sync_score,late_bonus)
        if best is None or cand[0]>best[0]: best=cand
    return {'start_sec':round(float(best[1]),3),'sync_score':round(float(best[2]),4),'late_sync_score':round(float(best[3]),4)}


def render(source,music,out,source_start,music_start):
    # Stable hybrid mobile framing. Foreground is slightly enlarged but action context is preserved.
    vf=(f"[0:v]trim=start={source_start:.3f}:duration={TARGET:.3f},setpts=PTS-STARTPTS,fps={FPS},split=2[bg][fg];"
        f"[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=32,eq=brightness=-0.08:saturation=0.86[bg2];"
        f"[fg]scale=1140:-2:force_original_aspect_ratio=decrease,eq=contrast=1.035:saturation=1.04,unsharp=5:5:0.45:5:5:0[fg2];"
        f"[bg2][fg2]overlay=(W-w)/2:(H-h)/2,fade=t=in:st=0:d=0.12,fade=t=out:st=19.75:d=0.25[v];"
        f"[1:a]atrim=start={music_start:.3f}:duration={TARGET:.3f},asetpts=PTS-STARTPTS,aresample=48000,"
        f"afade=t=in:st=0:d=0.04,afade=t=out:st=19.75:d=0.25,loudnorm=I=-14:TP=-1.5:LRA=8[a]")
    cmd=['ffmpeg','-nostdin','-hide_banner','-y','-i',str(source),'-i',str(music),'-filter_complex',vf,
         '-map','[v]','-map','[a]','-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p','-r',str(FPS),
         '-c:a','aac','-ar','48000','-ac','2','-b:a','192k','-movflags','+faststart','-t',f'{TARGET:.3f}',str(out)]
    subprocess.run(cmd,check=True)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('source'); ap.add_argument('music'); ap.add_argument('source_analysis'); ap.add_argument('output'); ap.add_argument('plan')
    ap.add_argument('--source-title',default='Saitama vs Cosmic Garou — RedHairedGuy')
    ap.add_argument('--music-title',default='METAMORPHOSIS — INTERWORLD')
    a=ap.parse_args()
    source=Path(a.source); music=Path(a.music); out=Path(a.output); plan=Path(a.plan)
    out.parent.mkdir(parents=True,exist_ok=True); plan.parent.mkdir(parents=True,exist_ok=True)
    sa=json.loads(Path(a.source_analysis).read_text())
    sdur=duration(source)
    sstart, impacts=select_window(sa,sdur)
    msel=select_music_window(music,impacts)
    render(source,music,out,sstart,msel['start_sec'])
    p=probe(out); v=next(s for s in p['streams'] if s.get('codec_type')=='video'); aud=next(s for s in p['streams'] if s.get('codec_type')=='audio')
    odur=float(p['format']['duration']); size=int(p['format']['size'])
    late=any(x>=14 for x in impacts)
    early=any(x<=3 for x in impacts)
    readability_pass=bool(early and late and len(impacts)>=3)
    technical_pass=bool(int(v['width'])==1080 and int(v['height'])==1920 and 19.90<=odur<=20.10 and int(aud['sample_rate'])==48000 and size>1000000)
    creative_pass=bool(readability_pass and msel['sync_score']>=0.08)
    meta={
      'flow':'v0.9-readability-first',
      'editor_mode':'continuous_combat_phrase_aligned',
      'strategy':'continuous_combat',
      'source':{'title':a.source_title,'selected_start_sec':round(sstart,3),'window_sec':TARGET,'impacts_in_window_sec':impacts},
      'music':{'title':a.music_title,'selected_start_sec':msel['start_sec'],'impact_onset_sync_score':msel['sync_score'],'late_sync_score':msel['late_sync_score'],'source_audio_in_mix':False,'sample_rate_hz':48000},
      'hard_source_jumps_added':0,
      'speed_warp_applied':False,
      'post_edit_cuts_added':0,
      'framing_policy':'stable hybrid 9:16; preserve choreography context; no per-section crop reset',
      'technical_pass':technical_pass,
      'readability_pass':readability_pass,
      'creative_pass':creative_pass,
      'duration_sec':round(odur,3),'size':'1080x1920','fps':FPS,'bytes':size
    }
    plan.write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(meta,ensure_ascii=False))
    if not technical_pass: raise SystemExit('technical QA failed')
    if not readability_pass: raise SystemExit('readability heuristic failed')
    if not creative_pass: raise SystemExit('creative/audio alignment heuristic failed')

if __name__=='__main__': main()
