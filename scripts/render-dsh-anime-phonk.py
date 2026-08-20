#!/usr/bin/env python3
import array
import json
import math
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

# Metaphonk is 150 BPM => one beat = 0.4s. Each edit block is intentionally
# quantized to the beat grid so the cuts do not feel arbitrary.
BPM = 150.0
BEAT = 60.0 / BPM
# start, end, target edit duration, role
plan = [
    (34.5, 39.0, 4.8, 'hook_readable_open'),       # 12 beats
    (68.0, 75.0, 6.4, 'pursuit_buildup'),          # 16 beats
    (92.0, 98.0, 5.6, 'midfight_escalation'),      # 14 beats
    (112.0, 118.0, 5.2, 'clash_acceleration'),     # 13 beats
    (168.0, 173.5, 6.0, 'fuga_ignition'),          # 15 beats
    (173.5, 179.0, 5.2, 'explosion_payoff'),       # 13 beats
]
segments = [(a, b, (b-a)/dur, role) for a,b,dur,role in plan]
block_durations = [dur for _,_,dur,_ in plan]
out_duration = sum(block_durations)  # 33.2s
fuga_edit_sec = sum(block_durations[:4])  # exactly 22.0s


def has_audio(path: Path) -> bool:
    r = subprocess.run([
        'ffprobe','-v','error','-select_streams','a:0','-show_entries','stream=index',
        '-of','csv=p=0',str(path)
    ], capture_output=True, text=True)
    return r.returncode == 0 and bool(r.stdout.strip())


source_has_audio = has_audio(video)

# Decode enough of the licensed track to locate energy rises. We deliberately
# choose a strong rise AFTER the edit's Fuga point so we can trim the music and
# put that rise exactly on Fuga instead of accepting an early 12.7s drop.
probe_seconds = 100
r = subprocess.run([
    'ffmpeg','-nostdin','-v','error','-i',str(music),'-t',str(probe_seconds),
    '-ac','1','-ar','8000','-f','f32le','-'
], capture_output=True)
if r.returncode != 0 or not r.stdout:
    raise SystemExit('could not decode music for drop analysis')
vals = array.array('f')
vals.frombytes(r.stdout)
sr = 8000
step_sec = 0.10
win = int(sr * step_sec)
rms = []
for i in range(0, len(vals)-win+1, win):
    chunk = vals[i:i+win]
    e = math.sqrt(sum(float(x)*float(x) for x in chunk) / max(1, len(chunk)))
    rms.append(math.log10(e + 1e-7))
sm = []
for i in range(len(rms)):
    lo=max(0,i-2); hi=min(len(rms),i+3)
    sm.append(sum(rms[lo:hi])/(hi-lo))

candidates = []
for i in range(int(5/step_sec), min(len(sm)-10, int(85/step_sec))):
    pre_slice = sm[max(0,i-10):i]
    post_slice = sm[i:min(len(sm),i+10)]
    pre = sum(pre_slice)/max(1,len(pre_slice))
    post = sum(post_slice)/max(1,len(post_slice))
    score = post-pre
    candidates.append((score, i*step_sec))

# Need a source-track drop later than Fuga so audio_start remains positive.
late_candidates = [(score,t) for score,t in candidates if t >= fuga_edit_sec + 2.0]
if not late_candidates:
    late_candidates = candidates
best_score, drop_sec = max(late_candidates, key=lambda x: x[0])
audio_start = max(0.0, drop_sec - fuga_edit_sec)

filters=[]
vlabels=[]
alabels=[]
for idx,(start,end,speed,role) in enumerate(segments):
    base=f'b{idx}'; bg=f'bg{idx}'; fg=f'fg{idx}'; vl=f'v{idx}'
    filters.append(
        f"[0:v]trim=start={start}:end={end},setpts=(PTS-STARTPTS)/{speed:.8f},split=2[{base}a][{base}b]"
    )
    # Background fills 9:16 only; the actual source image is never center-cropped.
    filters.append(
        f"[{base}a]scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop=1080:1920,gblur=sigma=30:steps=2,eq=brightness=-0.24:saturation=0.82[{bg}]"
    )
    filters.append(
        f"[{base}b]scale=1080:-2:flags=lanczos,eq=contrast=1.04:saturation=1.06:brightness=-0.01[{fg}]"
    )
    filters.append(
        f"[{bg}][{fg}]overlay=x=(W-w)/2:y=(H-h)/2:shortest=1,setsar=1,fps=30[{vl}]"
    )
    vlabels.append(f'[{vl}]')
    if source_has_audio:
        al=f's{idx}'
        filters.append(
            f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS,atempo={speed:.8f}[{al}]"
        )
        alabels.append(f'[{al}]')

filters.append(''.join(vlabels)+f'concat=n={len(segments)}:v=1:a=0[vcat]')
if source_has_audio:
    filters.append(''.join(alabels)+f'concat=n={len(segments)}:v=0:a=1[sfxcat]')

cut_times=[]
acc=0.0
for d in block_durations[:-1]:
    acc += d
    cut_times.append(acc)
enable='+'.join([f'between(t,{x:.3f},{x+0.040:.3f})' for x in cut_times]) or '0'
filters.append(
    f"[vcat]drawbox=x=0:y=0:w=iw:h=ih:color=white@0.20:t=fill:enable='{enable}',"
    f"fade=t=in:st=0:d=0.12,fade=t=out:st={out_duration-0.40:.3f}:d=0.40[vout]"
)
filters.append(
    f"[1:a]atrim=start={audio_start:.3f}:duration={out_duration:.3f},asetpts=PTS-STARTPTS,"
    "volume=0.92,loudnorm=I=-13:TP=-1.2:LRA=7[music]"
)
if source_has_audio:
    filters.append('[sfxcat]volume=0.36,highpass=f=80[sfx]')
    filters.append('[music][sfx]amix=inputs=2:duration=first:dropout_transition=0,alimiter=limit=0.95[aout]')
else:
    filters.append('[music]alimiter=limit=0.95[aout]')

cmd=[
    'ffmpeg','-nostdin','-hide_banner','-y','-i',str(video),'-i',str(music),
    '-filter_complex',';'.join(filters),'-map','[vout]','-map','[aout]',
    '-c:v','libx264','-preset','medium','-crf','19','-pix_fmt','yuv420p',
    '-c:a','aac','-b:a','192k','-movflags','+faststart','-t',f'{out_duration:.3f}',str(output)
]
print('Rendering', output)
rr=subprocess.run(cmd)
if rr.returncode != 0 or not output.exists() or output.stat().st_size == 0:
    raise SystemExit(f'ffmpeg render failed: {rr.returncode}')

meta={
    'status':'success',
    'layout':'full_16_9_foreground_on_blurred_9_16_canvas',
    'bpm':BPM,
    'beat_seconds':BEAT,
    'beat_quantized':True,
    'video_source_file':str(video),
    'music_source_file':str(music),
    'source_has_audio':source_has_audio,
    'selected_music_drop_sec':round(drop_sec,3),
    'drop_rise_score':round(best_score,5),
    'audio_start_sec':round(audio_start,3),
    'fuga_edit_sec':round(fuga_edit_sec,3),
    'drop_alignment_error_sec':round((drop_sec-audio_start)-fuga_edit_sec,4),
    'output_duration_sec':round(out_duration,3),
    'segments':[{'start':a,'end':b,'speed':round(s,6),'role':role,'edit_duration':dur} for (a,b,s,role),(_,_,dur,_) in zip(segments,plan)],
    'cut_times_sec':[round(x,3) for x in cut_times],
    'format':'1080x1920 H.264 + AAC',
    'output':str(output),
    'bytes':output.stat().st_size,
}
Path(analysis_path).write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(meta,ensure_ascii=False))
