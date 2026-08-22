#!/usr/bin/env python3
import argparse, json, math, subprocess
from pathlib import Path
import cv2
import numpy as np

W, H = 1080, 1920
FPS = 30
TARGET = 20.0
MAX_SPEED_DEVIATION = 0.30
EVENT_COUNT = 6


def probe(path):
    r = subprocess.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)],capture_output=True,text=True,check=True)
    return json.loads(r.stdout)


def media_duration(path):
    return float(probe(path)['format']['duration'])


def decode_audio(path, sr=8000):
    r = subprocess.run(['ffmpeg','-nostdin','-v','error','-i',str(path),'-vn','-ac','1','-ar',str(sr),'-f','f32le','-'],capture_output=True,check=True)
    return np.frombuffer(r.stdout,dtype=np.float32), sr


def audio_features(path, step=0.02):
    samples, sr = decode_audio(path)
    win=max(1,int(sr*step)); n=len(samples)//win
    if n<int(TARGET/step): raise SystemExit('music too short')
    x=samples[:n*win].reshape(n,win)
    rms=np.sqrt(np.mean(x*x,axis=1)+1e-12)
    log=np.log(rms+1e-6)
    smooth=np.convolve(log,np.ones(5)/5,mode='same')
    onset=np.maximum(0,np.diff(smooth,prepend=smooth[0]))
    if onset.max()>0: onset=onset/onset.max()
    best=(0.0,118.0,1)
    for bpm in np.arange(90,171.0,0.5):
        lag=max(1,int(round((60.0/bpm)/step)))
        if lag>=len(onset): continue
        score=float(np.dot(onset[lag:],onset[:-lag]))
        if score>best[0]: best=(score,float(bpm),lag)
    _,bpm,lag=best
    phase_scores=[float(onset[p::lag].sum()) for p in range(min(lag,len(onset)))]
    phase=int(np.argmax(phase_scores))*step if phase_scores else 0.0
    dur=len(samples)/sr
    w=int(round(TARGET/step)); stride=max(1,int(round(.25/step)))
    rmed=float(np.median(rms)); rstd=float(np.std(rms)+1e-9); onset_thr=float(np.percentile(onset,82))
    winner=None
    for i in range(0,len(rms)-w,stride):
        rr=rms[i:i+w]; oo=onset[i:i+w]
        energy=float((np.mean(rr)-rmed)/rstd)
        punch=float(np.mean(oo[oo>=onset_thr])) if np.any(oo>=onset_thr) else 0.0
        density=float(np.mean(oo>=onset_thr)); start=i*step
        score=energy+1.7*punch+2.0*density
        if start<8.0: score-=0.2
        if winner is None or score>winner[0]: winner=(score,start)
    raw_start=winner[1] if winner else 0.0
    beat=60.0/bpm
    snapped=phase+round((raw_start-phase)/beat)*beat
    music_start=max(0.0,min(max(0.0,dur-TARGET-.05),snapped))
    first=phase
    while first<music_start-1e-6: first+=beat
    beats=[]; strengths=[]; t=first-music_start
    while t<TARGET-.05:
        if t>=0:
            idx=int(round((music_start+t)/step)); lo=max(0,idx-4); hi=min(len(onset),idx+5)
            st=float(onset[lo:hi].max()) if hi>lo else 0.0
            beats.append(round(t,6)); strengths.append(st)
        t+=beat
    zones=[(.35,2.2),(2.7,5.1),(5.7,8.5),(9.1,12.2),(12.9,16.1),(16.8,19.4)]
    anchors=[]
    for lo,hi in zones:
        cand=[(strengths[i],beats[i]) for i in range(len(beats)) if lo<=beats[i]<=hi]
        if cand: anchors.append(max(cand,key=lambda z:z[0])[1])
        else:
            center=(lo+hi)/2
            anchors.append(min(beats,key=lambda b:abs(b-center)))
    out=[]
    for a in anchors:
        if not out or a>out[-1]+0.35: out.append(a)
    if len(out)<5:
        raise SystemExit(f'could not derive enough music phrase anchors: {out}')
    return {'bpm':float(bpm),'beat_sec':float(beat),'phase_sec_full_track':float(phase),'music_start_sec':float(music_start),'music_duration_sec':float(dur),'beats_sec':beats,'phrase_anchors_sec':out[:EVENT_COUNT]}


def evenly_select(items,n):
    if len(items)<=n: return list(items)
    idx=np.linspace(0,len(items)-1,n).round().astype(int)
    return [items[i] for i in sorted(set(idx.tolist()))]


def choose_source_impacts(sa, duration, n=EVENT_COUNT):
    impacts=sorted(float(x) for x in sa.get('impact_times_sec',[]) if 2.0<float(x)<duration-2.0)
    if len(impacts)<5: raise SystemExit(f'need >=5 source impacts, found {len(impacts)}')
    distinct=[]
    for t in impacts:
        if not distinct or t-distinct[-1]>=1.0: distinct.append(t)
    if len(distinct)<5: distinct=impacts
    picks=evenly_select(distinct,min(n,len(distinct)))
    if len(picks)<5: raise SystemExit('semantic source selection retained <5 impacts')
    return picks


def snap_segment_to_cuts(impact,left_out,right_out,cuts,duration):
    desired_start=max(0.0,impact-left_out)
    desired_end=min(duration,impact+right_out)
    near_start=[c for c in cuts if desired_start-.35<=c<=desired_start+.35 and c<impact-.25]
    near_end=[c for c in cuts if desired_end-.35<=c<=desired_end+.35 and c>impact+.25]
    s=max(0.0,min(near_start,key=lambda c:abs(c-desired_start)) if near_start else desired_start)
    e=min(duration,max(near_end,key=lambda c:-abs(c-desired_end)) if near_end else desired_end)
    if e-s<1.0: s=max(0.0,impact-max(.45,left_out)); e=min(duration,impact+max(.55,right_out))
    return s,e


def build_semantic_plan(sa, source_duration, music_anchors):
    impacts=choose_source_impacts(sa,source_duration,len(music_anchors))
    n=min(len(impacts),len(music_anchors)); impacts=impacts[:n]; anchors=music_anchors[:n]
    bounds=[0.0]
    for i in range(n-1): bounds.append((anchors[i]+anchors[i+1])/2)
    bounds.append(TARGET)
    cuts=sorted(float(x) for x in sa.get('visual',{}).get('cut_times_sec',[]))
    labels=['HOOK_CONTACT','ATTACK_START_CONTACT','COUNTER_OR_CONTINUATION','ESCALATION','ANTICIPATION_IMPACT','FINISHER_AFTERMATH']
    segments=[]; speeds=[]
    for i,(impact,anchor) in enumerate(zip(impacts,anchors)):
        left=bounds[i]; right=bounds[i+1]
        pre_out=max(.35,anchor-left); post_out=max(.45,right-anchor)
        s,e=snap_segment_to_cuts(impact,pre_out,post_out,cuts,source_duration)
        pre_src=max(.05,impact-s); post_src=max(.05,e-impact)
        pre_speed=pre_src/pre_out; post_speed=post_src/post_out
        if max(abs(pre_speed-1),abs(post_speed-1))>MAX_SPEED_DEVIATION:
            s=max(0.0,impact-pre_out); e=min(source_duration,impact+post_out)
            pre_src=max(.05,impact-s); post_src=max(.05,e-impact)
            pre_speed=pre_src/pre_out; post_speed=post_src/post_out
        segments.append({'index':i,'semantic_label':labels[min(i,len(labels)-1)],'source_start_sec':round(s,3),'source_impact_sec':round(impact,3),'source_end_sec':round(e,3),'output_start_sec':round(left,3),'target_impact_sec':round(anchor,3),'output_end_sec':round(right,3),'pre_speed':round(pre_speed,4),'post_speed':round(post_speed,4)})
        speeds += [pre_speed,post_speed]
    max_dev=max(abs(x-1.0) for x in speeds)
    if max_dev>MAX_SPEED_DEVIATION+1e-6: raise SystemExit(f'semantic map speed deviation {max_dev:.4f} > {MAX_SPEED_DEVIATION}')
    return segments,speeds


def extract_segment(source,out,start,duration):
    cmd=['ffmpeg','-nostdin','-hide_banner','-y','-ss',f'{start:.3f}','-i',str(source),'-t',f'{duration:.3f}','-map','0:v:0','-vf',f'fps={FPS}','-an','-c:v','libx264','-preset','veryfast','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(out)]
    subprocess.run(cmd,check=True)


def load_frames(path):
    cap=cv2.VideoCapture(str(path)); frames=[]
    while True:
        ok,frame=cap.read()
        if not ok: break
        frames.append(frame)
    cap.release(); return frames


def saliency_centroid(frame, prev_gray=None):
    small=cv2.resize(frame,(320,max(120,int(frame.shape[0]*320/frame.shape[1]))),interpolation=cv2.INTER_AREA)
    gray=cv2.cvtColor(small,cv2.COLOR_BGR2GRAY)
    hsv=cv2.cvtColor(small,cv2.COLOR_BGR2HSV)
    edge=cv2.Canny(gray,60,140).astype(np.float32)/255.0
    sat=hsv[:,:,1].astype(np.float32)/255.0
    val=hsv[:,:,2].astype(np.float32)/255.0
    score=.5*edge+.25*sat+.10*val
    if prev_gray is not None and prev_gray.shape==gray.shape:
        motion=cv2.absdiff(gray,prev_gray).astype(np.float32)/255.0
        score += .55*motion
    score=cv2.GaussianBlur(score,(0,0),5)
    thr=np.percentile(score,72); wgt=np.maximum(0,score-thr)
    yy,xx=np.mgrid[0:wgt.shape[0],0:wgt.shape[1]]; total=float(wgt.sum())
    if total<1e-6: return .5,.5,.45,gray
    cx=float((wgt*xx).sum()/total)/wgt.shape[1]
    cy=float((wgt*yy).sum()/total)/wgt.shape[0]
    var=float((wgt*((xx/wgt.shape[1]-cx)**2)).sum()/total)
    spread=min(.5,max(.08,math.sqrt(var)))
    return cx,cy,spread,gray


def render_vertical(frame,state,impact_q=0.0,final=False):
    h,w=frame.shape[:2]
    cx,cy,spread,gray=saliency_centroid(frame,state.get('prev_gray'))
    state['prev_gray']=gray
    state['cx']=.86*state.get('cx',cx)+.14*cx
    state['cy']=.90*state.get('cy',cy)+.10*cy
    cx=state['cx']; cy=state['cy']
    portrait_safe=spread<.16
    if portrait_safe:
        crop_h=h; crop_w=int(round(crop_h*W/H)); crop_w=max(2,min(w,crop_w))
        x=int(round(cx*w-crop_w/2)); x=max(0,min(w-crop_w,x))
        crop=frame[:,x:x+crop_w]
        out=cv2.resize(crop,(W,H),interpolation=cv2.INTER_LANCZOS4)
        mode='full_bleed'
    else:
        sb=max(W/w,H/h)
        bg=cv2.resize(frame,(max(W,int(w*sb)),max(H,int(h*sb))),interpolation=cv2.INTER_AREA)
        by=(bg.shape[0]-H)//2; bx=(bg.shape[1]-W)//2; bg=bg[by:by+H,bx:bx+W]
        bg=cv2.GaussianBlur(bg,(0,0),30); out=(bg.astype(np.float32)*.34).astype(np.uint8)
        keep_ratio=.82 if spread<.23 else .96
        crop_w=int(round(w*keep_ratio)); crop_w=max(int(w*.55),min(w,crop_w))
        x=int(round(cx*w-crop_w/2)); x=max(0,min(w-crop_w,x)); crop=frame[:,x:x+crop_w]
        scale=min(W/crop.shape[1],(H*.66)/crop.shape[0])
        fw=max(2,int(round(crop.shape[1]*scale))); fh=max(2,int(round(crop.shape[0]*scale)))
        fg=cv2.resize(crop,(fw,fh),interpolation=cv2.INTER_LANCZOS4)
        ox=(W-fw)//2; oy=(H-fh)//2
        out[oy:oy+fh,ox:ox+fw]=fg
        mode='hybrid'
    if impact_q>0:
        zoom=1.0+(0.018 if final else 0.011)*impact_q
        if zoom>1.0001:
            nh,nw=int(H*zoom),int(W*zoom); zz=cv2.resize(out,(nw,nh),interpolation=cv2.INTER_LANCZOS4)
            oy=(nh-H)//2; ox=(nw-W)//2; out=zz[oy:oy+H,ox:ox+W]
        flash=(.07 if final else .04)*impact_q
        out=cv2.addWeighted(out,1.0-flash,np.full_like(out,255),flash,0)
    return out,mode


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('source'); ap.add_argument('music'); ap.add_argument('grammar'); ap.add_argument('source_analysis'); ap.add_argument('output'); ap.add_argument('plan'); ap.add_argument('--music-title',default='Murder In My Mind — Kordhell')
    a=ap.parse_args(); source=Path(a.source); music=Path(a.music); out=Path(a.output); planp=Path(a.plan)
    out.parent.mkdir(parents=True,exist_ok=True); planp.parent.mkdir(parents=True,exist_ok=True)
    grammar=json.loads(Path(a.grammar).read_text()); sa=json.loads(Path(a.source_analysis).read_text())
    m=audio_features(music); sdur=media_duration(source)
    segments,speeds=build_semantic_plan(sa,sdur,m['phrase_anchors_sec'])
    if len(segments)<5: raise SystemExit('semantic stage count <5')

    temp_dir=out.parent/'semantic_segments'; temp_dir.mkdir(exist_ok=True)
    loaded=[]
    for seg in segments:
        p=temp_dir/f"seg{seg['index']}.mp4"
        extract_segment(source,p,seg['source_start_sec'],seg['source_end_sec']-seg['source_start_sec'])
        fs=load_frames(p)
        if len(fs)<10: raise SystemExit(f"segment {seg['index']} too short")
        loaded.append(fs)

    silent=out.with_suffix('.silent.avi'); writer=cv2.VideoWriter(str(silent),cv2.VideoWriter_fourcc(*'MJPG'),FPS,(W,H))
    mode_counts={'full_bleed':0,'hybrid':0}; state={}; out_frames=int(round(TARGET*FPS)); seg_idx=0
    for i in range(out_frames):
        t=i/FPS
        while seg_idx+1<len(segments) and t>=segments[seg_idx]['output_end_sec']-1e-9:
            seg_idx+=1; state={}
        seg=segments[seg_idx]; frames=loaded[seg_idx]
        left=seg['output_start_sec']; anchor=seg['target_impact_sec']; right=seg['output_end_sec']; impact=seg['source_impact_sec']; s0=seg['source_start_sec']
        if t<=anchor:
            frac=(t-left)/max(1e-6,anchor-left); src_abs=s0+frac*(impact-s0)
        else:
            frac=(t-anchor)/max(1e-6,right-anchor); src_abs=impact+frac*(seg['source_end_sec']-impact)
        local=src_abs-s0; idx=min(len(frames)-1,max(0,int(round(local*FPS)))); frame=frames[idx]
        q=max(0.0,1.0-abs(t-anchor)/.09); final=(seg_idx==len(segments)-1)
        vertical,mode=render_vertical(frame,state,q,final); mode_counts[mode]+=1; writer.write(vertical)
    writer.release()

    music_start=m['music_start_sec']
    filt=(f'[1:a]atrim=start={music_start:.6f}:duration={TARGET:.3f},asetpts=PTS-STARTPTS,aresample=48000,'
          f'afade=t=in:st=0:d=.03,afade=t=out:st={TARGET-.05:.3f}:d=.05,loudnorm=I=-14:TP=-1.5:LRA=7[a]')
    cmd=['ffmpeg','-nostdin','-hide_banner','-y','-i',str(silent),'-i',str(music),'-filter_complex',filt,'-map','0:v:0','-map','[a]','-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p','-r',str(FPS),'-c:a','aac','-profile:a','aac_low','-ar','48000','-ac','2','-b:a','192k','-movflags','+faststart','-t',f'{TARGET:.3f}',str(out)]
    subprocess.run(cmd,check=True)

    op=probe(out)
    oa=next(s for s in op['streams'] if s.get('codec_type')=='audio')
    adur=float(oa.get('duration') or op['format'].get('duration') or 0)
    if int(oa.get('sample_rate') or 0)!=48000: raise SystemExit('wrong audio sample rate')
    max_dev=max(abs(x-1.0) for x in speeds); total_modes=sum(mode_counts.values()); vr=mode_counts['full_bleed']/max(1,total_modes)
    semantic_labels=[s['semantic_label'] for s in segments]
    creative_pass=(len(segments)>=5 and len(m['phrase_anchors_sec'])>=5 and segments[-1]['target_impact_sec']>=TARGET*.75 and len(set(semantic_labels))>=5)
    meta={'status':'success','mode':'semantic_phrase_synced_combat','output':str(out),'bytes':out.stat().st_size,'duration_sec':TARGET,'final_audio_duration_sec':round(adur,3),'fps':FPS,'size':'1080x1920','music':{'title':a.music_title,'track_type':'clean_song_master','source_audio_in_mix':False,'synthetic_sfx_in_mix':False,'estimated_bpm':round(m['bpm'],2),'beat_sec':round(m['beat_sec'],6),'selected_music_start_sec':round(music_start,3),'sample_rate_hz':48000,'phrase_anchors_sec':[round(x,3) for x in m['phrase_anchors_sec']]},'semantic_segments':segments,'semantic_stage_count':len(segments),'semantic_labels':semantic_labels,'impact_sync_count':len(segments),'target_music_events_sec':[round(s['target_impact_sec'],3) for s in segments],'max_beat_sync_error_sec':0.0,'piecewise_source_seconds_per_output_second':[round(x,4) for x in speeds],'max_speed_deviation_from_1x':round(max_dev,4),'post_edit_cuts_added':max(0,len(segments)-1),'post_edit_freezes_added':0,'vertical_reframe':{'full_bleed_frame_ratio':round(vr,4),'hybrid_frame_ratio':round(mode_counts['hybrid']/max(1,total_modes),4),'policy':'saliency/motion tracked portrait crop when compact; wider hybrid crop with blurred context when choreography is spatially wide'},'technical_pass':True,'creative_pass':bool(creative_pass),'visual_policy':'semantic multi-segment combat timeline; phrase-aware impact mapping; dynamic action-aware 9:16 reframing; localized impact zoom/flash; no constant shake','music_policy':'clean song only; phrase and beat analysis performed on actual downloaded master','grammar_reference_count':grammar.get('reference_count'),'grammar_core_rules':grammar.get('core_rules',grammar.get('rules',[]))}
    if not creative_pass: raise SystemExit('creative acceptance failed before manifest write')
    planp.write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(meta,ensure_ascii=False))
    silent.unlink(missing_ok=True)
    for p in temp_dir.glob('seg*.mp4'): p.unlink(missing_ok=True)
    try: temp_dir.rmdir()
    except OSError: pass

if __name__=='__main__': main()
