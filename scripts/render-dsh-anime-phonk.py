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

# V2 editorial plan: preserve spatial readability and let the fight breathe.
# The source stays fully visible in a 16:9 foreground card on a blurred 9:16 fill.
segments = [
    # start, end, speed, role
    (34.5, 39.0, 0.98, 'hook_readable_open'),
    (68.0, 75.0, 1.08, 'pursuit_buildup'),
    (92.0, 98.0, 1.08, 'midfight_escalation'),
    (112.0, 118.0, 1.10, 'clash_acceleration'),
    (168.0, 173.5, 0.92, 'fuga_ignition'),
    (173.5, 179.0, 1.08, 'explosion_payoff'),
]


def has_audio(path: Path) -> bool:
    r = subprocess.run([
        'ffprobe','-v','error','-select_streams','a:0','-show_entries','stream=index',
        '-of','csv=p=0',str(path)
    ], capture_output=True, text=True)
    return r.returncode == 0 and bool(r.stdout.strip())


source_has_audio = has_audio(video)

# Find the strongest energy rise in the first 90 seconds of the soundtrack.
probe_seconds = 90
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
    e = math.sqrt(sum(float(x)*float(x) for x in chunk) / max(1, len(chunk)))
    rms.append(math.log10(e + 1e-7))
sm = []
for i in range(len(rms)):
    lo = max(0, i-2)
    hi = min(len(rms), i+3)
    sm.append(sum(rms[lo:hi]) / (hi-lo))
best_i = int(18.0/0.10)
best_score = -999
for i in range(int(6/0.10), min(len(sm)-10, int(70/0.10))):
    pre_slice = sm[max(0, i-10):i]
    post_slice = sm[i:min(len(sm), i+10)]
    pre = sum(pre_slice) / max(1, len(pre_slice))
    post = sum(post_slice) / max(1, len(post_slice))
    score = post - pre
    if score > best_score:
        best_score = score
        best_i = i
drop_sec = best_i * 0.10

block_durations = [(b-a)/speed for a,b,speed,_ in segments]
out_duration = sum(block_durations)
fuga_edit_sec = sum(block_durations[:4])
audio_start = max(0.0, drop_sec - fuga_edit_sec)

filters = []
vlabels = []
alabels = []
for idx, (start, end, speed, role) in enumerate(segments):
    base = f'b{idx}'
    bg = f'bg{idx}'
    fg = f'fg{idx}'
    vl = f'v{idx}'
    filters.append(
        f"[0:v]trim=start={start}:end={end},setpts=(PTS-STARTPTS)/{speed},split=2[{base}a][{base}b]"
    )
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
        al = f's{idx}'
        filters.append(
            f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS,atempo={speed}[{al}]"
        )
        alabels.append(f'[{al}]')

filters.append(''.join(vlabels) + f'concat=n={len(segments)}:v=1:a=0[vcat]')
if source_has_audio:
    filters.append(''.join(alabels) + f'concat=n={len(segments)}:v=0:a=1[sfxcat]')

cut_times = []
acc = 0.0
for d in block_durations[:-1]:
    acc += d
    cut_times.append(acc)
enable = '+'.join([f'between(t,{x:.3f},{x+0.040:.3f})' for x in cut_times]) or '0'
filters.append(
    f"[vcat]drawbox=x=0:y=0:w=iw:h=ih:color=white@0.22:t=fill:enable='{enable}',"
    f"fade=t=in:st=0:d=0.12,fade=t=out:st={max(0, out_duration-0.40):.3f}:d=0.40[vout]"
)
filters.append(
    f"[1:a]atrim=start={audio_start:.3f}:duration={out_duration:.3f},asetpts=PTS-STARTPTS,"
    "volume=0.92,loudnorm=I=-13:TP=-1.2:LRA=7[music]"
)
if source_has_audio:
    filters.append('[sfxcat]volume=0.38,highpass=f=80[sfx]')
    filters.append('[music][sfx]amix=inputs=2:duration=first:dropout_transition=0,alimiter=limit=0.95[aout]')
else:
    filters.append('[music]alimiter=limit=0.95[aout]')

cmd = [
    'ffmpeg','-nostdin','-hide_banner','-y','-i',str(video),'-i',str(music),
    '-filter_complex',';'.join(filters),'-map','[vout]','-map','[aout]',
    '-c:v','libx264','-preset','medium','-crf','19','-pix_fmt','yuv420p',
    '-c:a','aac','-b:a','192k','-movflags','+faststart','-t',f'{out_duration:.3f}',str(output)
]
print('Rendering', output)
rr = subprocess.run(cmd)
if rr.returncode != 0 or not output.exists() or output.stat().st_size == 0:
    raise SystemExit(f'ffmpeg render failed: {rr.returncode}')

meta = {
    'status':'success',
    'layout':'full_16_9_foreground_on_blurred_9_16_canvas',
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
Path(analysis_path).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(meta, ensure_ascii=False))
