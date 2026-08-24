#!/usr/bin/env bash
set -euo pipefail
ROOT='dsh-handoff/ibkr-recreate'
FINAL="$ROOT/final"
PUB='ibkr-remotion/public'
mkdir -p "$FINAL" "$PUB" ibkr-remotion/out

# This reference is self-contained motion graphics/UI. v0.11 routes it to
# native DOM/SVG reconstruction; no external footage/audio acquisition is required.
# Build the small brand lockup natively from the reference visual grammar.
cat > "$PUB/dsh-logo.svg" <<'SVG'
<svg xmlns="http://www.w3.org/2000/svg" width="760" height="150" viewBox="0 0 760 150">
  <rect width="760" height="150" fill="none"/>
  <g transform="translate(18 27)">
    <path d="M22 92 L44 4 L64 9 L42 96 Z" fill="#f5265d"/>
    <path d="M30 25 C2 30 0 72 30 77" fill="none" stroke="#f5265d" stroke-width="16" stroke-linecap="round"/>
  </g>
  <text x="110" y="92" font-family="Arial,Helvetica,sans-serif" font-size="56" font-weight="700" fill="white">InteractiveBrokers</text>
</svg>
SVG
rsvg-convert "$PUB/dsh-logo.svg" -o "$PUB/dsh-logo.png"
test -s "$PUB/dsh-logo.png"

pushd ibkr-remotion >/dev/null
npm install --no-audit --no-fund
npx remotion render src/index.jsx IBKRRecreate out/ibkr_recreate_silent.mp4 --codec=h264 --crf=17 --pixel-format=yuv420p --concurrency=2
popd >/dev/null

cp ibkr-remotion/out/ibkr_recreate_silent.mp4 "$FINAL/ibkr_recreate_silent.mp4"
ffmpeg -nostdin -v error -i "$FINAL/ibkr_recreate_silent.mp4" -f null -
ffmpeg -nostdin -hide_banner -y -v error -i "$FINAL/ibkr_recreate_silent.mp4" -vf "fps=1/2,scale=270:-2,tile=4x2:padding=8:margin=8" -frames:v 1 "$FINAL/qa-contact.jpg"

python3 - <<'PY'
import json, subprocess
from pathlib import Path
p=Path('dsh-handoff/ibkr-recreate/final/ibkr_recreate_silent.mp4')
raw=subprocess.check_output([
  'ffprobe','-v','error',
  '-show_entries','format=duration',
  '-show_entries','stream=codec_type,codec_name,width,height,sample_rate,channels',
  '-of','json',str(p)
],text=True)
x=json.loads(raw)
video=next(s for s in x['streams'] if s['codec_type']=='video')
audio=next((s for s in x['streams'] if s['codec_type']=='audio'),None)
dur=float(x['format']['duration'])
qa={
  'resolution':[int(video['width']),int(video['height'])],
  'video_codec':video['codec_name'],
  'duration':dur,
  'expected_creative_duration':14.9,
  'has_audio':audio is not None,
  'audio_codec': audio['codec_name'] if audio else None,
  'sample_rate': int(audio['sample_rate']) if audio and audio.get('sample_rate') else None,
  'channels': int(audio['channels']) if audio and audio.get('channels') else None,
  'production_route':'reference teardown -> spec -> native Remotion/DOM/SVG -> local reference audio -> final QC',
  'external_acquisition_required':False
}
qa['pass']=(
  qa['resolution']==[1080,1920]
  and qa['video_codec']=='h264'
  and 14.7<=dur<=15.1
  and qa['has_audio'] is True
  and qa['audio_codec']=='aac'
  and qa['sample_rate']==48000
  and qa['channels']==2
)
Path('dsh-handoff/ibkr-recreate/final/qa.json').write_text(json.dumps(qa,indent=2))
assert qa['pass'], qa
print(json.dumps(qa,indent=2))
PY

cp ibkr-reconstruction-spec.json "$FINAL/reconstruction-spec.json"
echo 'IBKR RECREATE+ NATIVE AUDIO RENDER PASS'
