#!/usr/bin/env python3
import array, json, math, subprocess, sys
from pathlib import Path

if len(sys.argv) != 5:
    raise SystemExit('usage: render-dsh-anime-aura-v4.py <video> <music> <output.mp4> <analysis.json>')
video, music, output, analysis_path = map(Path, sys.argv[1:])
for p in (video, music):
    if not p.exists() or p.stat().st_size == 0:
        raise SystemExit(f'missing input: {p}')
output.parent.mkdir(parents=True, exist_ok=True)
Path(analysis_path).parent.mkdir(parents=True, exist_ok=True)

# V4 editorial language: fast fight -> hard stutter -> aura farming -> fast payoff.
# Fight shots use a large 1:1 active crop over a darkened full-frame background.
# Aura shot intentionally switches to a tall character crop so Sukuna owns the screen.
FAST_A = [
    (68.5,69.15,1.30,'hit_01',0.48),
    (70.6,71.25,1.45,'hit_02',0.45),
    (73.1,73.85,1.45,'hit_03',0.52),
    (92.5,93.25,1.40,'hit_04',0.54),
    (95.0,95.85,1.55,'hit_05',0.55),
    (112.3,113.15,1.50,'hit_06',0.57),
    (115.1,116.0,1.55,'hit_07',0.58),
    (172.8,173.55,1.45,'hit_08',0.52),
]
# The stutter source is a Sukuna close shot; repeated with alternating punch-in/brightness.
STUTTER = [(35.05,35.32,1.0,f'stutter_{i}',0.24) for i in range(4)]
AURA = [(34.75,38.10,0.67,'aura_farm',5.00)]
FAST_B = [
    (93.7,94.55,1.35,'payoff_01',0.63),
    (96.0,96.9,1.45,'payoff_02',0.62),
    (113.5,114.45,1.45,'payoff_03',0.66),
    (116.0,116.95,1.50,'payoff_04',0.63),
    (168.8,170.25,1.00,'fuga_build',1.45),
    (170.6,171.75,1.18,'fuga_charge',0.97),
    (172.0,173.15,1.28,'fuga_release',0.90),
    (173.5,174.55,1.40,'blast_01',0.75),
    (174.6,176.1,1.55,'blast_02',0.97),
]
segments = FAST_A + STUTTER + AURA + FAST_B


def has_audio(path):
    r = subprocess.run(['ffprobe','-v','error','-select_streams','a:0','-show_entries','stream=index','-of','csv=p=0',str(path)],capture_output=True,text=True)
    return r.returncode == 0 and bool(r.stdout.strip())

source_has_audio = has_audio(video)

# Detect an early strong energy rise in the supplied viral sound and place it on aura reveal.
r = subprocess.run(['ffmpeg','-nostdin','-v','error','-i',str(music),'-t','60','-ac','1','-ar','8000','-f','f32le','-'],capture_output=True)
if r.returncode != 0 or not r.stdout:
    raise SystemExit('could not decode soundtrack')
vals = array.array('f'); vals.frombytes(r.stdout)
sr=8000; hop=int(sr*.05); rms=[]
for i in range(0,len(vals)-hop+1,hop):
    c=vals[i:i+hop]
    e=math.sqrt(sum(float(x)*float(x) for x in c)/max(1,len(c)))
    rms.append(math.log10(e+1e-8))
sm=[]
for i in range(len(rms)):
    lo=max(0,i-3); hi=min(len(rms),i+4); sm.append(sum(rms[lo:hi])/(hi-lo))
best_i=int(6/.05); best_score=-999
for i in range(int(2/.05), min(len(sm)-20,int(42/.05))):
    pre=sum(sm[max(0,i-12):i])/max(1,len(sm[max(0,i-12):i]))
    post=sum(sm[i:i+12])/max(1,len(sm[i:i+12]))
    score=post-pre
    if score>best_score:
        best_score=score; best_i=i
drop_sec=best_i*.05

fast_a_d=sum(x[4] for x in FAST_A)
stutter_d=sum(x[4] for x in STUTTER)
aura_reveal=fast_a_d+stutter_d
out_duration=sum(x[4] for x in segments)
audio_start=max(0.0,drop_sec-aura_reveal)

filters=[]; vlabels=[]; alabels=[]
for idx,(start,end,speed,role,target_d) in enumerate(segments):
    raw_d=(end-start)/speed
    # force every block to the editorial target duration; this keeps cuts on a deliberate grid
    pts_scale=target_d/max(raw_d,1e-6)
    base=f'b{idx}'; bg=f'bg{idx}'; fg=f'fg{idx}'; out=f'v{idx}'
    filters.append(f'[0:v]trim=start={start}:end={end},setpts=(PTS-STARTPTS)/{speed}*{pts_scale},split=2[{base}a][{base}b]')
    filters.append(f'[{base}a]scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,gblur=sigma=32:steps=2,eq=brightness=-0.30:saturation=0.85[{bg}]')
    if role=='aura_farm' or role.startswith('stutter_'):
        # Tall smart crop for the centered Sukuna close shot.
        punch = 1.10 if role.startswith('stutter_') else 1.02
        bright = 0.035 if role.startswith('stutter_') and idx%2==0 else 0.0
        filters.append(f'[{base}b]scale=-2:1920:flags=lanczos,crop=1080:1920:x=(iw-1080)/2:y=0,scale={int(1080*punch)}:{int(1920*punch)},crop=1080:1920,eq=contrast=1.10:saturation=1.16:brightness={bright},vignette=PI/5[{fg}]')
        filters.append(f'[{bg}][{fg}]overlay=0:0:shortest=1,setsar=1,fps=30[{out}]')
    else:
        # Big 1:1 action crop, safer than full 9:16 crop but much larger than the old letterbox card.
        filters.append(f'[{base}b]scale=-2:1080:flags=lanczos,crop=1080:1080:x=(iw-1080)/2:y=0,eq=contrast=1.08:saturation=1.10[{fg}]')
        filters.append(f'[{bg}][{fg}]overlay=x=0:y=(H-h)/2:shortest=1,setsar=1,fps=30[{out}]')
    vlabels.append(f'[{out}]')
    if source_has_audio:
        al=f'a{idx}'
        filters.append(f'[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS,atempo={speed},atempo={1/pts_scale if 0.5 <= 1/pts_scale <= 2 else 1.0}[{al}]')
        alabels.append(f'[{al}]')

filters.append(''.join(vlabels)+f'concat=n={len(segments)}:v=1:a=0[vcat]')
if source_has_audio:
    filters.append(''.join(alabels)+f'concat=n={len(segments)}:v=0:a=1[sfxcat]')

# 1-2 frame flashes at rapid cuts, stronger around stutter and aura reveal.
cut_times=[]; acc=0.0
for seg in segments[:-1]:
    acc += seg[4]; cut_times.append(acc)
flash_expr='+'.join([f'between(t,{x:.3f},{x+0.050:.3f})' for x in cut_times])
filters.append(f"[vcat]drawbox=x=0:y=0:w=iw:h=ih:color=white@0.28:t=fill:enable='{flash_expr}',fade=t=in:st=0:d=.08,fade=t=out:st={out_duration-.25:.3f}:d=.25[vout]")
filters.append(f'[1:a]atrim=start={audio_start:.3f}:duration={out_duration:.3f},asetpts=PTS-STARTPTS,volume=1.02,loudnorm=I=-12:TP=-1.0:LRA=6[music]')
if source_has_audio:
    filters.append('[sfxcat]volume=0.22,highpass=f=100[sfx]')
    filters.append('[music][sfx]amix=inputs=2:duration=first:dropout_transition=0,alimiter=limit=.96[aout]')
else:
    filters.append('[music]alimiter=limit=.96[aout]')

cmd=['ffmpeg','-nostdin','-hide_banner','-y','-i',str(video),'-i',str(music),'-filter_complex',';'.join(filters),'-map','[vout]','-map','[aout]','-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-movflags','+faststart','-t',f'{out_duration:.3f}',str(output)]
print('Rendering',output,'duration',out_duration,'aura',aura_reveal,'music_drop',drop_sec,'audio_start',audio_start)
rr=subprocess.run(cmd)
if rr.returncode!=0 or not output.exists() or output.stat().st_size<1000000:
    raise SystemExit(f'ffmpeg render failed: {rr.returncode}')
meta={'status':'success','concept':'fast_fight_stutter_aura_farm_payoff','duration_sec':round(out_duration,3),'aura_reveal_sec':round(aura_reveal,3),'detected_music_drop_sec':round(drop_sec,3),'audio_start_sec':round(audio_start,3),'drop_alignment_error_sec':round(abs((drop_sec-audio_start)-aura_reveal),3),'segments':[{'start':a,'end':b,'speed':s,'role':r,'edit_duration':d} for a,b,s,r,d in segments],'cut_times_sec':[round(x,3) for x in cut_times],'format':'1080x1920 H.264 + AAC','bytes':output.stat().st_size}
Path(analysis_path).write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(meta,ensure_ascii=False))
