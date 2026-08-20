#!/usr/bin/env python3
import array
import json
import math
import os
from pathlib import Path
import subprocess
import sys

if len(sys.argv) != 5:
    raise SystemExit('usage: render-dsh-anime-phonk.py <video> <music> <output.mp4> <analysis.json>')

video, music, output, analysis_path = map(Path, sys.argv[1:])
for p in (video, music):
    if not p.exists() or p.stat().st_size == 0:
        raise SystemExit(f'missing input: {p}')
output.parent.mkdir(parents=True, exist_ok=True)
Path(analysis_path).parent.mkdir(parents=True, exist_ok=True)

# V4/DSH scene analysis: Sukuna vs Mahoraga reference clip. Keep one payoff,
# but compress the fight into beat blocks instead of a random montage.
segments = [
    # start, end, speed, role
    (34.5, 37.5, 0.88, 'hook_hand_seal'),
    (68.0, 74.0, 1.15, 'buildup_pressure'),
    (112.0, 117.0, 1.25, 'clash_acceleration'),
    (168.0, 173.0, 0.88, 'fuga_ignition'),
    (173.0, 179.0, 1.15, 'explosion_payoff'),
]

# Probe whether source has an audio stream for low-level SFX retention.
def has_audio(path: Path) -> bool:
    r = subprocess.run([
        'ffprobe','-v','error','-select_streams','a:0','-show_entries','stream=index',
        '-of','csv=p=0',str(path)
    ], capture_output=True, text=True)
    return r.returncode == 0 and bool(r.stdout.strip())

source_has_audio = has_audio(video)

# Detect a likely musical drop from short-time RMS rise. No external Python deps.
# Decode first 75s to mono float32 at 8kHz.
probe_seconds = 75
r = subprocess.run([
    'ffmpeg','-nostdin','-v','error','-i',str(music),'-t',str(probe_seconds),
    '-ac','1','-ar','8000','-f','f32le','-'
], capture_output=True)
if r.returncode != 0 or not r.stdout:
    raise SystemExit('could not decode music for drop analysis')
vals = array.array('f')
vals.frombytes(r.stdout)
sr = 8000
win = int(sr * 0.10)
rms = []
for i in range(0, len(vals)-win+1, win):
    chunk = vals[i:i+win]
    e = math.sqrt(sum(float(x)*float(x) for x in chunk)/max(1,len(chunk)))
    rms.append(math.log10(e + 1e-7))
# Smooth ~0.5s then maximize future-vs-past level rise between 5s and 55s.
sm = []
for i in range(len(rms)):
    lo=max(0,i-2); hi=min(len(rms),i+3)
    sm.append(sum(rms[lo:hi])/(hi-lo))
best_i = int(12.6/0.10)
best_score = -999
for i in range(int(5/0.10), min(len(sm)-8, int(55/0.10))):
    pre = sum(sm[max(0,i-8):i])/max(1,len(sm[max(0,i-8):i]))
    post = sum(sm[i:min(len(sm),i+8)])/max(1,len(sm[i:min(len(sm),i+8)]))
    score = post-pre
    if score > best_score:
        best_score=score; best_i=i
drop_sec = best_i * 0.10

block_durations = [(b-a)/speed for a,b,speed,_ in segments]
out_duration = sum(block_durations)
# Fuga starts at block 4. Align detected musical drop there.
fuga_edit_sec = sum(block_durations[:3])
audio_start = max(0.0, drop_sec - fuga_edit_sec)

# Source 16:9 -> center action crop 9:16. This is intentionally aggressive for TikTok.
# Hard cuts are used; 50ms flash frames emphasize each transition.
filters=[]
vlabels=[]
alabels=[]
for idx,(start,end,speed,role) in enumerate(segments):
    vl=f'v{idx}'
    filters.append(
        f"[0:v]trim=start={start}:end={end},setpts=(PTS-STARTPTS)/{speed},"
        "crop='min(iw,ih*9/16)':ih:(iw-min(iw,ih*9/16))/2:0,"
        "scale=1080:1920:flags=lanczos,fps=30,"
        "eq=contrast=1.07:saturation=1.10:brightness=-0.01,unsharp=5:5:0.45:5:5:0["+vl+"]"
    )
    vlabels.append(f'[{vl}]')
    if source_has_audio:
        al=f's{idx}'
        filters.append(
            f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS,atempo={speed}[{al}]"
        )
        alabels.append(f'[{al}]')
filters.append(''.join(vlabels)+f'concat=n={len(segments)}:v=1:a=0[vcat]')
if source_has_audio:
    filters.append(''.join(alabels)+f'concat=n={len(segments)}:v=0:a=1[sfxcat]')

# Flash at every cut plus quick fade at head/tail.
cut_times=[]
acc=0.0
for d in block_durations[:-1]:
    acc += d
    cut_times.append(acc)
enable='+'.join([f'between(t,{x:.3f},{x+0.055:.3f})' for x in cut_times]) or '0'
filters.append(
    f"[vcat]drawbox=x=0:y=0:w=iw:h=ih:color=white@0.58:t=fill:enable='{enable}',"
    f"fade=t=in:st=0:d=0.10,fade=t=out:st={max(0,out_duration-0.35):.3f}:d=0.35[vout]"
)
filters.append(
    f"[1:a]atrim=start={audio_start:.3f}:duration={out_duration:.3f},asetpts=PTS-STARTPTS,"
    "volume=0.96,loudnorm=I=-12:TP=-1.2:LRA=7[music]"
)
if source_has_audio:
    filters.append('[sfxcat]volume=0.27,highpass=f=90[sfx]')
    filters.append('[music][sfx]amix=inputs=2:duration=shortest:dropout_transition=0,alimiter=limit=0.95[aout]')
else:
    filters.append('[music]alimiter=limit=0.95[aout]')

cmd=[
    'ffmpeg','-nostdin','-hide_banner','-y','-i',str(video),'-i',str(music),
    '-filter_complex',';'.join(filters),'-map','[vout]','-map','[aout]',
    '-c:v','libx264','-preset','medium','-crf','19','-pix_fmt','yuv420p',
    '-c:a','aac','-b:a','192k','-movflags','+faststart','-shortest',str(output)
]
print('Rendering', output)
rr=subprocess.run(cmd)
if rr.returncode != 0 or not output.exists() or output.stat().st_size == 0:
    raise SystemExit(f'ffmpeg render failed: {rr.returncode}')

meta={
    'status':'success',
    'video_source_file':str(video),
    'music_source_file':str(music),
    'source_has_audio':source_has_audio,
    'detected_music_drop_sec':round(drop_sec,3),
    'drop_rise_score':round(best_score,5),
    'audio_start_sec':round(audio_start,3),
    'fuga_edit_sec':round(fuga_edit_sec,3),
    'output_duration_sec':round(out_duration,3),
    'segments':[{'start':a,'end':b,'speed':s,'role':role,'edit_duration':round((b-a)/s,3)} for a,b,s,role in segments],
    'cut_times_sec':[round(x,3) for x in cut_times],
    'format':'1080x1920 H.264 + AAC',
    'output':str(output),
    'bytes':output.stat().st_size,
}
Path(analysis_path).write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(meta,ensure_ascii=False))
