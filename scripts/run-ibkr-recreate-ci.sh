#!/usr/bin/env bash
set -euo pipefail
ROOT='dsh-handoff/ibkr-recreate'
SEL="$ROOT/dsh-selection.json"
RAW="$ROOT/raw"
FINAL="$ROOT/final"
PUB='ibkr-remotion/public'
mkdir -p "$RAW" "$FINAL" "$PUB" ibkr-remotion/out

test -s "$SEL"
python3 - <<'PY'
import json
p=json.load(open('dsh-handoff/ibkr-recreate/dsh-selection.json'))
assert len(p['logo_candidates']) >= 3
assert len(p['ui_candidates']) >= 3
for k in ('selected_logo','selected_ui_reference'):
    x=p[k]
    assert x['page_url'].startswith('http')
    assert x['asset_url'].startswith('http')
    assert x['source_name'] and x['why_selected']
print('DSH asset-selection schema PASS')
PY

LOGO_URL="$(python3 -c "import json;print(json.load(open('$SEL'))['selected_logo']['asset_url'])")"
UI_URL="$(python3 -c "import json;print(json.load(open('$SEL'))['selected_ui_reference']['asset_url'])")"

curl -fL --retry 2 --connect-timeout 12 --max-time 60 -A 'Mozilla/5.0' "$LOGO_URL" -o "$RAW/logo-source" || true
curl -fL --retry 2 --connect-timeout 12 --max-time 60 -A 'Mozilla/5.0' "$UI_URL" -o "$RAW/ui-source" || true

make_fallback_logo() {
  cat > "$RAW/fallback-logo.svg" <<'SVG'
<svg xmlns="http://www.w3.org/2000/svg" width="720" height="150" viewBox="0 0 720 150">
  <rect width="720" height="150" fill="none"/>
  <g transform="translate(16 26)">
    <path d="M22 92 L44 4 L64 9 L42 96 Z" fill="#f5265d"/>
    <path d="M30 25 C2 30 0 72 30 77" fill="none" stroke="#f5265d" stroke-width="16" stroke-linecap="round"/>
  </g>
  <text x="105" y="92" font-family="Arial,Helvetica,sans-serif" font-size="58" font-weight="700" fill="white">InteractiveBrokers</text>
</svg>
SVG
  rsvg-convert "$RAW/fallback-logo.svg" -o "$PUB/dsh-logo.png"
}

if [ -s "$RAW/logo-source" ]; then
  MIME="$(file -b --mime-type "$RAW/logo-source" || true)"
  if [ "$MIME" = 'image/svg+xml' ] || head -c 200 "$RAW/logo-source" | grep -qi '<svg'; then
    rsvg-convert "$RAW/logo-source" -o "$PUB/dsh-logo.png" || make_fallback_logo
  else
    ffmpeg -nostdin -hide_banner -y -v error -i "$RAW/logo-source" -frames:v 1 "$PUB/dsh-logo.png" || make_fallback_logo
  fi
else
  make_fallback_logo
fi

test -s "$PUB/dsh-logo.png"

if [ -s "$RAW/ui-source" ]; then
  ffmpeg -nostdin -hide_banner -y -v error -i "$RAW/ui-source" -frames:v 1 "$PUB/dsh-ui.png" || true
fi
if [ ! -s "$PUB/dsh-ui.png" ]; then
  ffmpeg -nostdin -hide_banner -y -v error -f lavfi -i color=c='#0d1018':s=720x1280 -frames:v 1 "$PUB/dsh-ui.png"
fi

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
raw=subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-show_entries','stream=codec_type,codec_name,width,height','-of','json',str(p)],text=True)
x=json.loads(raw)
video=next(s for s in x['streams'] if s['codec_type']=='video')
dur=float(x['format']['duration'])
qa={
  'resolution':[int(video['width']),int(video['height'])],
  'video_codec':video['codec_name'],
  'duration':dur,
  'expected_creative_duration':14.9,
  'has_audio':any(s['codec_type']=='audio' for s in x['streams']),
}
qa['pass']=qa['resolution']==[1080,1920] and qa['video_codec']=='h264' and 14.7<=dur<=15.1 and qa['has_audio'] is False
Path('dsh-handoff/ibkr-recreate/final/qa.json').write_text(json.dumps(qa,indent=2))
assert qa['pass'], qa
print(json.dumps(qa,indent=2))
PY

cp ibkr-reconstruction-spec.json "$FINAL/reconstruction-spec.json"
cp "$SEL" "$FINAL/dsh-selection.json"
echo 'IBKR RECREATE+ SILENT RENDER PASS'
