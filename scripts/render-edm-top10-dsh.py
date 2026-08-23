from __future__ import annotations
import json, pathlib, subprocess, sys
from PIL import Image, ImageDraw, ImageFont

W,H,FPS=1080,1920,30
VIDEO_Y=270; VIDEO_H=960
WHITE=(247,247,245); MUT=(166,168,174); DIM=(72,74,80)
FONT='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
BOLD='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
INTRO=2.2; REG=5.1; TOP=6.4; OUTRO=5.0

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

def font(size,bold=False): return ImageFont.truetype(BOLD if bold else FONT,size)

def fit(draw,text,maxw,start=31,minsize=17,bold=True):
    for s in range(start,minsize-1,-2):
        f=font(s,bold)
        if draw.textbbox((0,0),text,font=f)[2] <= maxw: return f
    return font(minsize,bold)

def list_overlay(idx,out,cta=False):
    im=Image.new('RGBA',(W,H),(0,0,0,0)); d=ImageDraw.Draw(im)
    d.rectangle((0,0,W,VIDEO_Y),fill=(0,0,0,255))
    d.rectangle((0,VIDEO_Y+VIDEO_H,W,H),fill=(0,0,0,255))
    d.text((54,58),'TOP 10 NOSTALGIC',font=font(52,True),fill=WHITE)
    d.text((54,119),'EDM SONGS — 2010s',font=font(57,True),fill=WHITE)
    d.text((56,190),'the era that still sounds enormous',font=font(25),fill=(184,186,192))
    d.line((40,VIDEO_Y+VIDEO_H+18,1040,VIDEO_Y+VIDEO_H+18),fill=(255,255,255,88),width=2)
    y0=1268; row=49
    for i,(rank,song,artist) in enumerate(TRACKS):
        y=y0+i*row; active=i==idx; revealed=idx is not None and i<=idx
        if active:
            d.rounded_rectangle((42,y-4,1038,y+42),radius=10,fill=(248,248,246,244)); nf=sf=(8,8,10); af=(76,78,84)
        elif revealed: nf=sf=WHITE; af=MUT
        else: nf=sf=DIM; af=(62,64,70)
        d.text((61,y),str(rank),font=font(31,True),fill=nf)
        d.text((126,y),song,font=fit(d,song,570,31,20,True),fill=sf)
        fa=fit(d,artist,300,22,16,False); tw=d.textbbox((0,0),artist,font=fa)[2]
        d.text((1010-tw,y+4),artist,font=fa,fill=af)
    if cta:
        d.rounded_rectangle((54,1790,1026,1874),radius=24,fill=(248,248,246,244))
        t='Which one is your #1?'; f=font(34,True); tw=d.textbbox((0,0),t,font=f)[2]
        d.text(((W-tw)//2,1813),t,font=f,fill=(8,8,10))
    im.save(out)

def intro_overlay(out):
    im=Image.new('RGBA',(W,H),(0,0,0,0)); d=ImageDraw.Draw(im)
    d.rectangle((0,0,W,H),fill=(0,0,0,120))
    d.text((54,115),'2010s EDM',font=font(39,True),fill=(214,216,220))
    for j,t in enumerate(['TOP 10','NOSTALGIC','EDM SONGS']):
        d.text((54,600+j*118),t,font=font(104 if j!=1 else 92,True),fill=WHITE)
    d.text((58,1030),'songs that instantly bring the era back',font=font(28),fill=(224,226,230))
    im.save(out)

def clamp_start(src,start,need):
    D=probe_duration(src)
    if D <= need+0.2: return 0.0
    return max(0.0,min(float(start),D-need-0.15))

def segment(src,overlay,secs,out,start):
    start=clamp_start(src,start,secs)
    fade=max(0.0,secs-0.08)
    fc=(
      f"color=c=black:s={W}x{H}:r={FPS}[bg];"
      f"[0:v]scale={W}:{VIDEO_H}:force_original_aspect_ratio=increase,crop={W}:{VIDEO_H},eq=contrast=1.03:saturation=1.06[v];"
      f"[bg][v]overlay=0:{VIDEO_Y}[mid];"
      f"[1:v]format=rgba[ov];[mid][ov]overlay=0:0:format=auto,fps={FPS},format=yuv420p[vout]"
    )
    run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-ss',f'{start:.3f}','-i',str(src),'-loop','1','-i',str(overlay),'-t',f'{secs:.3f}',
         '-filter_complex',fc,'-map','[vout]','-map','0:a:0','-af',f'aresample=48000,afade=t=in:st=0:d=0.06,afade=t=out:st={fade:.3f}:d=0.08',
         '-r',str(FPS),'-c:v','libx264','-preset','veryfast','-crf','18','-c:a','aac','-b:a','192k','-ar','48000','-ac','2','-movflags','+faststart','-shortest',str(out)])

def main():
    if len(sys.argv)<2: raise SystemExit('usage: render-edm-top10-dsh.py ROOT')
    root=pathlib.Path(sys.argv[1]); sel=json.load(open(root/'dsh-selection.json'))
    media=root/'media'; out=root/'final'; work=out/'work'; ovs=work/'ovs'; clips=work/'clips'
    for d in (out,work,ovs,clips): d.mkdir(parents=True,exist_ok=True)
    rows={int(x['rank']):x for x in sel['tracks']}
    assert set(rows)==set(range(1,11)),sorted(rows)
    intro_overlay(ovs/'intro.png')
    for i in range(10): list_overlay(i,ovs/f'list-{i}.png')
    list_overlay(9,ovs/'outro.png',True)

    outputs=[]; timeline=[]; cursor=0.0
    src10=media/'rank-10.mp4'; s10=float(rows[10]['selected_source']['start_sec'])
    p=clips/'00-intro.mp4'; segment(src10,ovs/'intro.png',INTRO,p,max(0,s10-INTRO)); outputs.append(p); timeline.append({'type':'intro','start':0,'end':INTRO}); cursor+=INTRO

    for i,(rank,song,artist) in enumerate(TRACKS):
        row=rows[rank]; src=media/f'rank-{rank:02d}.mp4'; secs=TOP if rank==1 else REG
        start=float(row['selected_source']['start_sec']); p=clips/f'{i+1:02d}-rank-{rank:02d}.mp4'
        segment(src,ovs/f'list-{i}.png',secs,p,start); outputs.append(p)
        timeline.append({'rank':rank,'song':song,'artist':artist,'start':round(cursor,3),'end':round(cursor+secs,3),'source':row['selected_source']}); cursor+=secs

    src1=media/'rank-01.mp4'; s1=float(rows[1]['selected_source']['start_sec'])
    p=clips/'11-outro.mp4'; segment(src1,ovs/'outro.png',OUTRO,p,s1+TOP); outputs.append(p); timeline.append({'type':'outro','start':round(cursor,3),'end':round(cursor+OUTRO,3)}); cursor+=OUTRO

    concat=work/'concat.txt'; concat.write_text('\n'.join("file '"+str(p.resolve())+"'" for p in outputs)+'\n')
    joined=work/'joined.mp4'; run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(concat),'-c','copy',str(joined)])
    final=out/'edm_top10_nostalgia.mp4'
    run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-i',str(joined),'-map','0:v:0','-map','0:a:0','-c:v','copy','-af','loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000','-c:a','aac','-b:a','192k','-ar','48000','-ac','2','-movflags','+faststart',str(final)])
    D=probe_duration(final); assert 59.0<=D<=60.0,D

    times=[.8,3.5,8.6,13.7,18.8,23.9,29,34.1,39.2,44.3,49.4,55.4,58.7]; thumbs=[]
    for j,t in enumerate(times):
        q=work/f'q{j:02d}.jpg'; run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-ss',str(t),'-i',str(final),'-frames:v','1','-vf','scale=270:480',str(q)]); thumbs.append(Image.open(q).convert('RGB'))
    sheet=Image.new('RGB',(1080,1920),(16,16,18))
    for j,im in enumerate(thumbs): sheet.paste(im,((j%4)*270,(j//4)*480))
    sheet.save(out/'qa-contact.jpg',quality=94)

    raw=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(final)],text=True)); v=next(s for s in raw['streams'] if s['codec_type']=='video'); a=next(s for s in raw['streams'] if s['codec_type']=='audio')
    qa={'duration':D,'resolution':[int(v['width']),int(v['height'])],'video_codec':v['codec_name'],'audio_codec':a['codec_name'],'sample_rate':int(a['sample_rate']),'tracks':10}
    qa['pass']=(qa['resolution']==[1080,1920] and qa['video_codec']=='h264' and qa['audio_codec']=='aac' and qa['sample_rate']==48000 and 59.0<=D<=60.0)
    (out/'qa.json').write_text(json.dumps(qa,indent=2),encoding='utf-8')
    (out/'timeline.json').write_text(json.dumps({'duration':D,'timeline':timeline},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(qa,indent=2),flush=True)
    assert qa['pass'],qa

if __name__=='__main__': main()
