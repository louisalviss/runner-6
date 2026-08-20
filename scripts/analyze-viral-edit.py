#!/usr/bin/env python3
import argparse, array, json, math, statistics, subprocess, wave
from pathlib import Path
import cv2
import numpy as np


def ffprobe(path):
    p=subprocess.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)],capture_output=True,text=True,check=True)
    return json.loads(p.stdout)

def audio_envelope(path, sr=8000, step=0.02):
    r=subprocess.run(['ffmpeg','-nostdin','-v','error','-i',str(path),'-vn','-ac','1','-ar',str(sr),'-f','f32le','-'],capture_output=True,check=True)
    vals=np.frombuffer(r.stdout,dtype=np.float32)
    win=max(1,int(sr*step)); n=len(vals)//win
    if n<10: return np.zeros(1), step
    x=vals[:n*win].reshape(n,win)
    rms=np.sqrt(np.mean(x*x,axis=1)+1e-12)
    log=np.log(rms+1e-6)
    smooth=np.convolve(log,np.ones(5)/5,mode='same')
    onset=np.maximum(0,np.diff(smooth,prepend=smooth[0]))
    if onset.max()>0: onset/=onset.max()
    return onset,step

def estimate_bpm(onset,step):
    best=(0,120.0,0)
    for bpm in np.arange(80,190.01,0.5):
        lag=max(1,int(round((60.0/bpm)/step)))
        if lag>=len(onset): continue
        score=float(np.dot(onset[lag:],onset[:-lag]))
        if score>best[0]: best=(score,float(bpm),lag)
    _,bpm,lag=best
    phase_scores=[float(onset[p::lag].sum()) for p in range(min(lag,len(onset)))] if lag>0 else []
    phase=int(np.argmax(phase_scores)) if phase_scores else 0
    return bpm,phase*step

def frame_metrics(path,sample_fps=15.0):
    cap=cv2.VideoCapture(str(path)); fps=cap.get(cv2.CAP_PROP_FPS) or 30.0
    total=int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0); duration=(total/fps) if total else 0
    stride=max(1,int(round(fps/sample_fps))); rows=[]; prev_gray=None; freezes=[]; i=0
    while True:
        ok,frame=cap.read()
        if not ok: break
        if i%stride: i+=1; continue
        t=i/fps; small=cv2.resize(frame,(320,180),interpolation=cv2.INTER_AREA)
        gray=cv2.cvtColor(small,cv2.COLOR_BGR2GRAY); hsv=cv2.cvtColor(small,cv2.COLOR_BGR2HSV)
        bright=float(gray.mean()); sat=float(hsv[:,:,1].mean()); sharp=float(cv2.Laplacian(gray,cv2.CV_64F).var())
        diff=motion=tx=ty=0.0; scale=1.0
        if prev_gray is not None:
            diff=float(np.mean(cv2.absdiff(gray,prev_gray)))
            pts=cv2.goodFeaturesToTrack(prev_gray,maxCorners=120,qualityLevel=0.02,minDistance=6,blockSize=5)
            if pts is not None and len(pts)>=8:
                nxt,st,_=cv2.calcOpticalFlowPyrLK(prev_gray,gray,pts,None,winSize=(21,21),maxLevel=3)
                good=st.reshape(-1)==1; p0=pts.reshape(-1,2)[good]; p1=nxt.reshape(-1,2)[good]
                if len(p0)>=6:
                    motion=float(np.median(np.linalg.norm(p1-p0,axis=1)))
                    M,_=cv2.estimateAffinePartial2D(p0,p1,method=cv2.RANSAC,ransacReprojThreshold=3)
                    if M is not None:
                        scale=float(math.sqrt(M[0,0]**2+M[0,1]**2)); tx=float(M[0,2]); ty=float(M[1,2])
        rows.append({'t':round(t,4),'bright':bright,'sat':sat,'sharp':sharp,'diff':diff,'motion':motion,'scale':scale,'tx':tx,'ty':ty})
        prev_gray=gray; i+=1
    cap.release()
    if not rows: return {},[]
    diffs=np.array([r['diff'] for r in rows]); motions=np.array([r['motion'] for r in rows]); br=np.array([r['bright'] for r in rows]); satv=np.array([r['sat'] for r in rows]); scales=np.array([abs(r['scale']-1) for r in rows]); trans=np.array([math.hypot(r['tx'],r['ty']) for r in rows])
    cut_thr=max(18.0,float(np.percentile(diffs,92))); cuts=[r['t'] for r in rows[1:] if r['diff']>=cut_thr]; ded=[]
    for t in cuts:
        if not ded or t-ded[-1]>=0.10: ded.append(t)
    dt=(rows[1]['t']-rows[0]['t']) if len(rows)>1 else 1/sample_fps; run=[]
    for r in rows[1:]:
        if r['diff']<1.6 and r['motion']<0.22: run.append(r['t'])
        else:
            if len(run)*dt>=0.12: freezes.append([round(run[0]-dt,3),round(run[-1],3)])
            run=[]
    if len(run)*dt>=0.12: freezes.append([round(run[0]-dt,3),round(run[-1],3)])
    flash_thr=float(np.percentile(br,96)); color_thr=float(np.percentile(satv,90)); trans_thr=max(2.2,float(np.percentile(trans,90)))
    return {
      'duration_sec':round(duration,3),'source_fps':round(fps,3),'sample_fps':round(1/dt,3),'cut_times_sec':[round(x,3) for x in ded],
      'median_cut_interval_sec':round(float(np.median(np.diff([0]+ded+[duration]))) if ded else duration,3),'freeze_segments_sec':freezes,
      'flash_times_sec':[round(r['t'],3) for r in rows if r['bright']>=flash_thr and r['bright']>np.median(br)+18],
      'zoom_times_sec':[round(r['t'],3) for r in rows if abs(r['scale']-1)>=0.012 and r['motion']>0.4],
      'shake_times_sec':[round(r['t'],3) for r in rows if math.hypot(r['tx'],r['ty'])>=trans_thr],
      'color_burst_times_sec':[round(r['t'],3) for r in rows if r['sat']>=color_thr],
      'motion_p90':round(float(np.percentile(motions,90)),3),'translation_p90_px_sample':round(float(np.percentile(trans,90)),3),
      'scale_delta_p90':round(float(np.percentile(scales,90)),5),'brightness_p96':round(flash_thr,3),'saturation_p90':round(color_thr,3)
    },rows

def make_contact(path,out,duration,cols=5,rows=4):
    times=np.linspace(0,max(0.01,duration-0.01),cols*rows); cap=cv2.VideoCapture(str(path)); thumbs=[]
    for t in times:
        cap.set(cv2.CAP_PROP_POS_MSEC,float(t*1000)); ok,f=cap.read()
        if not ok: continue
        f=cv2.resize(f,(320,180),interpolation=cv2.INTER_AREA); cv2.rectangle(f,(0,150),(320,180),(0,0,0),-1)
        cv2.putText(f,f'{t:.2f}s',(8,171),cv2.FONT_HERSHEY_SIMPLEX,0.55,(255,255,255),1,cv2.LINE_AA); thumbs.append(f)
    cap.release()
    if thumbs:
        canvas=np.zeros((rows*180,cols*320,3),dtype=np.uint8)
        for i,f in enumerate(thumbs[:cols*rows]): canvas[(i//cols)*180:(i//cols+1)*180,(i%cols)*320:(i%cols+1)*320]=f
        cv2.imwrite(str(out),canvas,[cv2.IMWRITE_JPEG_QUALITY,90])

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('video'); ap.add_argument('outdir'); a=ap.parse_args(); video=Path(a.video); out=Path(a.outdir); out.mkdir(parents=True,exist_ok=True)
    probe=ffprobe(video); (out/'ffprobe.json').write_text(json.dumps(probe,indent=2)); onset,step=audio_envelope(video); bpm,phase=estimate_bpm(onset,step); visual,rows=frame_metrics(video)
    impact=[]
    if rows and len(onset)>2:
        d=np.array([r['diff'] for r in rows]); m=np.array([r['motion'] for r in rows]); b=np.array([r['bright'] for r in rows])
        def z(x):
            med=np.median(x); q=np.percentile(x,75)-np.percentile(x,25); return np.maximum(0,(x-med)/(q+1e-6))
        score=[]
        for r,ds,ms,bs in zip(rows,z(d),z(m),z(b)):
            oi=min(len(onset)-1,max(0,int(round(r['t']/step)))); score.append(1.8*onset[oi]+ds+0.9*ms+0.35*bs)
        chosen=[]
        for idx in np.argsort(score)[::-1]:
            t=rows[int(idx)]['t']
            if all(abs(t-x)>0.35 for x in chosen): chosen.append(t)
            if len(chosen)>=12: break
        impact=sorted(round(float(x),3) for x in chosen)
    leads=[]
    for _,end in visual.get('freeze_segments_sec',[]):
        later=[x for x in impact if 0<=x-end<=0.75]
        if later: leads.append(round(later[0]-end,3))
    data={'video':str(video),'audio':{'bpm':round(bpm,2),'beat_sec':round(60/bpm,4),'beat_phase_sec':round(phase,3),'onset_step_sec':step},'visual':visual,'impact_times_sec':impact,'freeze_to_impact_leads_sec':leads}
    (out/'analysis.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8'); make_contact(video,out/'contact.jpg',visual.get('duration_sec',0)); print(json.dumps(data,ensure_ascii=False))
if __name__=='__main__': main()
