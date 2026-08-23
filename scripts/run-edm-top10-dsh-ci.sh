#!/usr/bin/env bash
set -euo pipefail
ROOT='dsh-handoff/edm-top10-dsh'
SEL="$ROOT/dsh-selection.json"
MEDIA="$ROOT/media"
FINAL="$ROOT/final"
mkdir -p "$MEDIA" "$FINAL"
test -s "$SEL"

python - <<'PY'
import json
p=json.load(open('dsh-handoff/edm-top10-dsh/dsh-selection.json'))
assert isinstance(p.get('tracks'),list) and len(p['tracks'])==10
ranks=sorted(int(x['rank']) for x in p['tracks'])
assert ranks==list(range(1,11)),ranks
for x in p['tracks']:
    s=x['selected_source']
    assert s['url'].startswith('http'),s
    assert s.get('title')
    assert isinstance(s.get('start_sec'),(int,float)) and s['start_sec']>=0,s
print('selection schema pass')
PY

for RANK in $(seq 10 -1 1); do
  URL="$(python - "$RANK" <<'PY'
import json,sys
rank=int(sys.argv[1]); p=json.load(open('dsh-handoff/edm-top10-dsh/dsh-selection.json'))
row=next(x for x in p['tracks'] if int(x['rank'])==rank)
print(row['selected_source']['url'])
PY
)"
  echo "=== DSH handoff acquisition rank $RANK ==="
  rm -rf dsh-handoff/downloads dsh-handoff/handoff.json
  mkdir -p dsh-handoff/downloads
  bash scripts/dsh-download-media.sh "$URL" 720
  SRC="$(python -c "import json;print(json.load(open('dsh-handoff/handoff.json'))['relative_path'])")"
  test -s "$SRC"
  ffprobe -v error -select_streams v:0 -show_entries stream=codec_name -of csv=p=0 "$SRC" >/dev/null
  ffprobe -v error -select_streams a:0 -show_entries stream=codec_name -of csv=p=0 "$SRC" >/dev/null
  printf -v OUT '%s/rank-%02d.mp4' "$MEDIA" "$RANK"
  ffmpeg -nostdin -hide_banner -y -v error -i "$SRC" -map 0:v:0 -map 0:a:0 -c:v libx264 -preset veryfast -crf 19 -vf 'scale=-2:min(720,ih)' -c:a aac -b:a 192k -ar 48000 -ac 2 -movflags +faststart "$OUT"
  test -s "$OUT"
  D="$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$OUT")"
  python - "$RANK" "$D" <<'PY'
import sys
rank=int(sys.argv[1]); d=float(sys.argv[2])
assert d>12, (rank,d)
print('rank',rank,'duration',round(d,2),'sec')
PY
done

python scripts/render-edm-top10-dsh.py "$ROOT"
FINAL_MP4="$FINAL/edm_top10_nostalgia.mp4"
test -s "$FINAL_MP4"
ffmpeg -nostdin -v error -i "$FINAL_MP4" -f null -

python - <<'PY'
import json
from pathlib import Path
root=Path('dsh-handoff/edm-top10-dsh')
sel=json.load(open(root/'dsh-selection.json'))
qa=json.load(open(root/'final/qa.json'))
tl=json.load(open(root/'final/timeline.json'))
manifest={
  'flow':'AI Video Motion-First v0.10 DHS/DSH media handoff',
  'delegation':{
    'dsh':'research/select/acquire media source identities; downloader materializes handoff assets',
    'orchestrator':'all editing, crop/reframe, typography, timing, audio sync/mix, render, QC, final MP4'
  },
  'source_policy':'no official-source priority; selected by content fit, visual/audio strength, quality and usability',
  'selection':sel,
  'timeline':tl,
  'technical_qa':qa,
}
(root/'final/SOURCE_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print('EDM TOP10 DSH HANDOFF + FINAL QA PASS')
PY
