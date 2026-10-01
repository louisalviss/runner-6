from __future__ import annotations
import json, math, pathlib, subprocess, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont

W,H,FPS=1080,1920,30
VIDEO_Y=270
VIDEO_H=800
PANEL_Y=1090
SAFE_BOTTOM=1760
WHITE=(247,247,245); MUT=(172,174,180); DIM=(74,76,82)
FONT='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
BOLD='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
INTRO=1.5
REG=6.5
TOP3=7.5
TOP1=8.5
OUTRO=3.0

TRACKS=[
(10,'Tsunami','DVBBS & Borgeous'),
(9,'Heroes (We Could Be)','Alesso ft. Tove Lo'),
(8,'The Nights','Avicii'),
(7,'Summer','Calvin Harris'),
(6,'Titanium','David Guetta ft. Sia'),
(5,'Animals','Martin Garrix'),
(4,"Don't You Worry Child",'Swedish House Mafia'),
(3,'Clarity','Zedd ft. Foxes'),
(2,'Wake Me Up','Avicii'),
(1,'Levels','Avicii'),
]


def run(cmd):
    print('+',' '.join(map(str,cmd)),flush=True)
    subprocess.run(cmd,check=True)


def probe_duration(path):
    return float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(path)],text=True).strip())


def font(size,bold=False):
    return ImageFont.truetype(BOLD if bold else FONT,size)


def fit(draw,text,maxw,start=40,minsize=20,bold=True):
    for s in range(start,minsize-1,-2):
        f=font(s,bold)
        if draw.textbbox((0,0),text,font=f)[2] <= maxw:
            return f
    return font(minsize,bold)


def two_col_overlay(active_rank,out,cta=False):
    im=Image.new('RGBA',(W,H),(0,0,0,0)); d=ImageDraw.Draw(im)
    d.rectangle((0,0,W,VIDEO_Y),fill=(0,0,0,255))
    d.rectangle((0,VIDEO_Y+VIDEO_H,W,H),fill=(0,0,0,255))
    d.text((52,48),'TOP 10 NOSTALGIC',font=font(52,True),fill=WHITE)
    d.text((52,110),'EDM SONGS — 2010s',font=font(57,True),fill=WHITE)
    d.text((54,186),'turn it up — these still hit',font=font(27),fill=(190,192,198))
    d.line((38,PANEL_Y-18,W-38,PANEL_Y-18),fill=(255,255,255,88),width=2)

    left=[10,9,8,7,6]
    right=[5,4,3,2,1]
    col_x=[42,558]
    row_h=104
    y0=PANEL_Y+8
    rank_map={r:(s,a) for r,s,a in TRACKS}
    revealed=set(r for r,_,_ in TRACKS if active_rank is not None and r>=active_rank)
    # In countdown order, ranks already shown are numerically >= current active rank.
    for col,ranks in enumerate([left,right]):
        x=col_x[col]
        for j,rank in enumerate(ranks):
            y=y0+j*row_h
            song,artist=rank_map[rank]
            active=(rank==active_rank)
            shown=(rank in revealed)
            if active:
                d.rounded_rectangle((x,y-5,x+480,y+87),radius=16,fill=(248,248,246,246))
                rf=sf=(8,8,10); af=(74,76,82)
            elif shown:
                rf=sf=WHITE; af=MUT
            else:
                rf=sf=DIM; af=(64,66,72)
            d.text((x+16,y+7),str(rank),font=font(43,True),fill=rf)
            fs=fit(d,song,365,38,20,True)
            d.text((x+82,y+2),song,font=fs,fill=sf)
            fa=fit(d,artist,360,22,16,False)
            d.text((x+82,y+48),artist,font=fa,fill=af)

    if cta:
        d.rounded_rectangle((170,1645,910,1727),radius=24,fill=(248,248,246,246))
        t='Which one still hits hardest?'; f=font(32,True)
        tw=d.textbbox((0,0),t,font=f)[2]
        d.text(((W-tw)//2,1666),t,font=f,fill=(8,8,10))
    im.save(out)


def intro_overlay(out):
    im=Image.new('RGBA',(W,H),(0,0,0,0)); d=ImageDraw.Draw(im)
    d.rectangle((0,0,W,H),fill=(0,0,0,108))
    d.text((54,150),'2010s EDM',font=font(40,True),fill=(214,216,220))
    for j,t in enumerate(['TOP 10','NOSTALGIC','EDM SONGS']):
        d.text((54,585+j*120),t,font=font(104 if j!=1 else 92,True),fill=WHITE)
    d.text((58,1008),'the drops, hooks and choruses we still remember',font=font(27),fill=(230,232,236))
    im.save(out)


def _norm(v):
    v=np.asarray(v,dtype=np.float64)
    lo=float(np.percentile(v,10)); hi=float(np.percentile(v,90))
    if hi <= lo+1e-12:
        return np.zeros_like(v)
    return np.clip((v-lo)/(hi-lo),0,1)


def decode_audio(src,sr=12000):
    p=subprocess.run(['ffmpeg','-nostdin','-v','error','-i',str(src),'-vn','-ac','1','-ar',str(sr),'-f','f32le','pipe:1'],stdout=subprocess.PIPE,check=True)
    x=np.frombuffer(p.stdout,dtype=np.float32).astype(np.float64)
    if x.size==0:
        raise RuntimeError(f'empty audio: {src}')
    return x,sr


def choose_best_start(src,secs,hint):
    x,sr=decode_audio(src)
    dur=len(x)/sr
    hop_s=.25; hop=max(1,int(sr*hop_s)); win=max(hop,int(sr*.50))
    starts=np.arange(0,max(1,len(x)-win),hop,dtype=np.int64)
    sq=x*x
    cs=np.concatenate(([0.0],np.cumsum(sq)))
    ends=np.minimum(starts+win,len(x))
    rms=np.sqrt(np.maximum(0,(cs[ends]-cs[starts])/np.maximum(1,ends-starts)))

    nfft=1024
    mags=[]
    for s in starts:
        chunk=x[s:min(len(x),s+nfft)]
        if len(chunk)<nfft:
            chunk=np.pad(chunk,(0,nfft-len(chunk)))
        spec=np.abs(np.fft.rfft(chunk*np.hanning(nfft)))
        mags.append(spec)
    mags=np.asarray(mags)
    flux=np.zeros(len(mags))
    if len(mags)>1:
        diff=np.maximum(0,mags[1:]-mags[:-1])
        flux[1:]=np.sqrt((diff*diff).mean(axis=1))
    rn=_norm(rms); fn=_norm(flux)

    seg_frames=max(2,int(round(secs/hop_s)))
    pre_frames=max(2,int(round(2.0/hop_s)))
    head_frames=max(2,int(round(1.5/hop_s)))
    min_t=12.0
    max_t=max(min_t,dur-secs-8.0)
    best=None
    for i in range(len(starts)-seg_frames):
        t=i*hop_s
        if t<min_t or t>max_t:
            continue
        energy=float(rn[i:i+seg_frames].mean())
        onset=float(fn[i:i+head_frames].max())
        pre=float(rn[max(0,i-pre_frames):i].mean()) if i else 0.0
        post=float(rn[i:i+pre_frames].mean())
        jump=max(0.0,post-pre)
        sustain=float(np.percentile(rn[i:i+seg_frames],35))
        hint_bonus=math.exp(-0.5*((t-float(hint))/38.0)**2)
        score=.43*energy + .24*onset + .16*jump + .10*sustain + .07*hint_bonus
        if best is None or score>best[0]:
            best=(score,t,energy,onset,jump,hint_bonus)
    if best is None:
        t=max(0.0,min(float(hint),dur-secs-.2))
        return t,{'fallback':True,'hint':hint}
    t=max(0.0,best[1]-.25)
    return t,{
        'score':round(best[0],4),'energy':round(best[2],4),'onset':round(best[3],4),
        'jump':round(best[4],4),'hint_bonus':round(best[5],4),'hint':float(hint),
        'picked_start':round(t,3),'source_duration':round(dur,3)
    }


def segment(src,overlay,secs,out,start):
    D=probe_duration(src)
    start=max(0.0,min(float(start),max(0.0,D-secs-.1)))
    fade=max(0.0,secs-.14)
    fc=(
      f"color=c=black:s={W}x{H}:r={FPS}[base];"
      f"[0:v]split=2[bgsrc][fgsrc];"
      f"[bgsrc]scale={W}:{VIDEO_H}:force_original_aspect_ratio=increase,crop={W}:{VIDEO_H},boxblur=22:2,eq=brightness=-0.20:saturation=0.72[bgv];"
      f"[fgsrc]scale={W}:{VIDEO_H}:force_original_aspect_ratio=decrease[fgv];"
      f"[base][bgv]overlay=0:{VIDEO_Y}[b1];"
      f"[b1][fgv]overlay=(main_w-overlay_w)/2:{VIDEO_Y}+(%d-overlay_h)/2[b2];" % VIDEO_H +
      f"[1:v]format=rgba[ov];[b2][ov]overlay=0:0:format=auto,fps={FPS},format=yuv420p[vout]"
    )
    run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-ss',f'{start:.3f}','-i',str(src),'-loop','1','-i',str(overlay),'-t',f'{secs:.3f}',
         '-filter_complex',fc,'-map','[vout]','-map','0:a:0','-af',f'aresample=48000,afade=t=in:st=0:d=0.10,afade=t=out:st={fade:.3f}:d=0.14',
         '-r',str(FPS),'-c:v','libx264','-preset','veryfast','-crf','18','-c:a','aac','-b:a','192k','-ar','48000','-ac','2','-movflags','+faststart','-shortest',str(out)])


def main():
    if len(sys.argv)<2:
        raise SystemExit('usage: render-edm-top10-dsh-v2.py ROOT')
    root=pathlib.Path(sys.argv[1]); sel=json.load(open(root/'dsh-selection.json'))
    media=root/'media'; out=root/'final'; work=out/'work-v2'; ovs=work/'ovs'; clips=work/'clips'
    for d in (out,work,ovs,clips): d.mkdir(parents=True,exist_ok=True)
    rows={int(x['rank']):x for x in sel['tracks']}
    assert set(rows)==set(range(1,11)),sorted(rows)

    intro_overlay(ovs/'intro.png')
    for rank,_,_ in TRACKS:
        two_col_overlay(rank,ovs/f'list-{rank:02d}.png')
    two_col_overlay(1,ovs/'outro.png',True)

    pick={}
    for rank,song,artist in TRACKS:
        src=media/f'rank-{rank:02d}.mp4'
        secs=TOP1 if rank==1 else TOP3 if rank<=3 else REG
        hint=float(rows[rank]['selected_source']['start_sec'])
        start,meta=choose_best_start(src,secs,hint)
        pick[rank]={'rank':rank,'song':song,'artist':artist,'start':round(start,3),'duration':secs,'analysis':meta}
        print('AUDIO_PICK',json.dumps(pick[rank],ensure_ascii=False),flush=True)

    outputs=[]; timeline=[]; cursor=0.0
    src10=media/'rank-10.mp4'; p=clips/'00-intro.mp4'
    intro_start=max(0.0,pick[10]['start']-INTRO)
    segment(src10,ovs/'intro.png',INTRO,p,intro_start)
    outputs.append(p); timeline.append({'type':'intro','start':0,'end':INTRO,'source_start':intro_start}); cursor+=INTRO

    for i,(rank,song,artist) in enumerate(TRACKS):
        row=rows[rank]; src=media/f'rank-{rank:02d}.mp4'; secs=pick[rank]['duration']; start=pick[rank]['start']
        p=clips/f'{i+1:02d}-rank-{rank:02d}.mp4'
        segment(src,ovs/f'list-{rank:02d}.png',secs,p,start); outputs.append(p)
        timeline.append({'rank':rank,'song':song,'artist':artist,'start':round(cursor,3),'end':round(cursor+secs,3),'source_start':start,'audio_pick':pick[rank]['analysis'],'source':row['selected_source']})
        cursor+=secs

    src1=media/'rank-01.mp4'; p=clips/'11-outro.mp4'
    outro_start=min(max(0.0,probe_duration(src1)-OUTRO-.1),pick[1]['start']+TOP1)
    segment(src1,ovs/'outro.png',OUTRO,p,outro_start); outputs.append(p)
    timeline.append({'type':'outro','start':round(cursor,3),'end':round(cursor+OUTRO,3),'source_start':outro_start}); cursor+=OUTRO

    concat=work/'concat.txt'; concat.write_text('\n'.join("file '"+str(p.resolve())+"'" for p in outputs)+'\n')
    joined=work/'joined.mp4'; run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(concat),'-c','copy',str(joined)])
    final=out/'edm_top10_nostalgia.mp4'
    run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-i',str(joined),'-map','0:v:0','-map','0:a:0','-c:v','copy','-af','loudnorm=I=-13:TP=-1.2:LRA=9,aresample=48000','-ar','48000','-ac','2','-c:a','aac','-b:a','224k','-movflags','+faststart',str(final)])
    D=probe_duration(final)
    assert 73.0<=D<=74.5,D

    # More useful phone-size QA: sample intro, every rank, and outro.
    times=[.7,2.8,9.3,15.8,22.3,28.8,35.3,41.8,48.8,56.3,64.0,71.8]
    thumbs=[]
    for j,t in enumerate(times):
        q=work/f'q{j:02d}.jpg'
        run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-ss',str(t),'-i',str(final),'-frames:v','1','-vf','scale=270:480',str(q)])
        thumbs.append(Image.open(q).convert('RGB'))
    sheet=Image.new('RGB',(1080,1440),(16,16,18))
    for j,im in enumerate(thumbs):
        sheet.paste(im,((j%4)*270,(j//4)*480))
    sheet.save(out/'qa-contact.jpg',quality=94)

    raw=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(final)],text=True))
    v=next(s for s in raw['streams'] if s['codec_type']=='video'); a=next(s for s in raw['streams'] if s['codec_type']=='audio')
    qa={'pass':True,'version':'v2-iphone-uncropped-best-audio','duration':D,'resolution':[int(v['width']),int(v['height'])],'video_codec':v['codec_name'],'audio_codec':a['codec_name'],'sample_rate':int(a['sample_rate']),'tracks':10,'layout':'uncropped contain foreground + blurred fill','audio_selection':'waveform energy/onset/jump scan with DSH timestamp as weak prior','audio_picks':pick}
    (out/'qa.json').write_text(json.dumps(qa,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'timeline.json').write_text(json.dumps({'duration':D,'timeline':timeline},ensure_ascii=False,indent=2),encoding='utf-8')
    assert qa['resolution']==[1080,1920] and qa['video_codec']=='h264' and qa['audio_codec']=='aac' and qa['sample_rate']==48000
    print(json.dumps(qa,ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
