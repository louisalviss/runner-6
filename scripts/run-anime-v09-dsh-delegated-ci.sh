#!/usr/bin/env bash
set -euo pipefail

ROOT="dsh-handoff/anime-v09-dsh-delegated"
FINAL="$ROOT/final/anime_combat_v09_dsh.mp4"
SEL="$ROOT/dsh-selection.json"
mkdir -p "$ROOT/final"

test -s "$SEL"
SOURCE_URL="$(python - <<'PY'
import json
p=json.load(open('dsh-handoff/anime-v09-dsh-delegated/dsh-selection.json'))
print(p['selected_source']['url'])
PY
)"
SOURCE_TITLE="$(python - <<'PY'
import json
p=json.load(open('dsh-handoff/anime-v09-dsh-delegated/dsh-selection.json'))
print(p['selected_source']['title'])
PY
)"
MUSIC_TITLE="$(python - <<'PY'
import json
p=json.load(open('dsh-handoff/anime-v09-dsh-delegated/dsh-selection.json'))
print(p['selected_music']['title'])
PY
)"
MUSIC_ARTIST="$(python - <<'PY'
import json
p=json.load(open('dsh-handoff/anime-v09-dsh-delegated/dsh-selection.json'))
print(p['selected_music']['artist'])
PY
)"
MUSIC_QUERY="ytsearch1:${MUSIC_ARTIST} ${MUSIC_TITLE} official audio"

# Acquisition uses only DSH-selected identities; no source/song URL is preselected by the orchestrator.
rm -rf dsh-handoff/downloads dsh-handoff/handoff.json
mkdir -p dsh-handoff/downloads
bash scripts/dsh-download-media.sh "$SOURCE_URL" 720
P="$(python -c "import json;print(json.load(open('dsh-handoff/handoff.json'))['relative_path'])")"
ffmpeg -nostdin -hide_banner -y -v error -i "$P" -t 420 -map 0:v:0 -map 0:a? -c:v libx264 -preset veryfast -crf 18 -c:a aac -ar 48000 -b:a 160k -movflags +faststart "$ROOT/final/source.mp4"
test -s "$ROOT/final/source.mp4"
python scripts/analyze-viral-edit.py "$ROOT/final/source.mp4" "$ROOT/final/source-analysis"

rm -rf dsh-handoff/downloads dsh-handoff/handoff.json
mkdir -p dsh-handoff/downloads
bash scripts/dsh-download-media.sh "${MUSIC_QUERY}#dsh-audio" 720
P="$(python -c "import json;print(json.load(open('dsh-handoff/handoff.json'))['relative_path'])")"
ffmpeg -nostdin -hide_banner -y -v error -i "$P" -vn -ar 48000 -ac 2 -c:a pcm_s16le "$ROOT/final/music-master.wav"
test "$(stat -c '%s' "$ROOT/final/music-master.wav")" -gt 1000000

python scripts/render-anime-combat-v09.py \
  "$ROOT/final/source.mp4" \
  "$ROOT/final/music-master.wav" \
  "$ROOT/final/source-analysis/analysis.json" \
  "$FINAL" \
  "$ROOT/final/edit-plan.json" \
  --source-title "$SOURCE_TITLE" \
  --music-title "$MUSIC_TITLE — $MUSIC_ARTIST"

python scripts/analyze-viral-edit.py "$FINAL" "$ROOT/final/output-analysis"
ffprobe -v error -show_streams -show_format -of json "$FINAL" > "$ROOT/final/ffprobe.json"

python - <<'PY'
import json
from pathlib import Path
root=Path('dsh-handoff/anime-v09-dsh-delegated')
p=json.load(open(root/'final/ffprobe.json'))
plan=json.load(open(root/'final/edit-plan.json'))
sel=json.load(open(root/'dsh-selection.json'))
v=next(s for s in p['streams'] if s['codec_type']=='video')
a=next(s for s in p['streams'] if s['codec_type']=='audio')
d=float(p['format']['duration'])
assert int(v['width'])==1080 and int(v['height'])==1920
assert 19.90<=d<=20.10
assert int(a['sample_rate'])==48000
assert int(p['format']['size'])>1000000
manifest={
  'flow':'v0.9-readability-first',
  'delegation':'brief_to_dsh_no_preselected_source_or_song',
  'dsh_selection':sel,
  'edit_plan':plan,
  'technical_qa':{'pass':True,'duration_sec':d,'width':1080,'height':1920,'audio_hz':48000},
  'creative_qa':'pending_orchestrator_visual_review'
}
(root/'final/SOURCE_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print('DSH-DELEGATED TECHNICAL QA PASS')
PY

test -s "$FINAL"
