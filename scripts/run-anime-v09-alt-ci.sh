#!/usr/bin/env bash
set -euo pipefail

ROOT="dsh-handoff/anime-v09-alt"
FINAL="$ROOT/final/anime_combat_v09_alt.mp4"
SOURCE_URL="https://www.youtube.com/watch?v=IHSKA6bwNQ4"
SOURCE_TITLE="Saitama vs Cosmic Garou — RedHairedGuy"
MUSIC_URL="ytsearch1:INTERWORLD METAMORPHOSIS official audio"
MUSIC_TITLE="METAMORPHOSIS — INTERWORLD"
mkdir -p "$ROOT/final"

cat > "$ROOT/source-selection.json" <<'JSON'
{
  "strategy": "continuous_combat",
  "selected": {
    "title": "Saitama vs Cosmic Garou — RedHairedGuy",
    "url": "https://www.youtube.com/watch?v=IHSKA6bwNQ4",
    "reason": "Different combat identity from the prior JJK test; long continuous fight with enough choreography to support readability-first extraction."
  }
}
JSON

cat > "$ROOT/music-selection.json" <<'JSON'
{
  "title": "METAMORPHOSIS",
  "artist": "INTERWORLD",
  "clean_audio_url": "ytsearch1:INTERWORLD METAMORPHOSIS official audio",
  "reason": "Widely used phonk/edit track; different musical identity from Murder In My Mind and suitable for phrase/onset alignment without forcing extra cuts."
}
JSON

# DSH: production source only.
rm -rf dsh-handoff/downloads dsh-handoff/handoff.json
mkdir -p dsh-handoff/downloads
bash scripts/dsh-download-media.sh "$SOURCE_URL" 720
P="$(python -c "import json;print(json.load(open('dsh-handoff/handoff.json'))['relative_path'])")"
ffmpeg -nostdin -hide_banner -y -v error -i "$P" -t 420 -map 0:v:0 -map 0:a? -c:v libx264 -preset veryfast -crf 18 -c:a aac -ar 48000 -b:a 160k -movflags +faststart "$ROOT/final/source.mp4"
test -s "$ROOT/final/source.mp4"
python scripts/analyze-viral-edit.py "$ROOT/final/source.mp4" "$ROOT/final/source-analysis"

# DSH: clean music master only.
rm -rf dsh-handoff/downloads dsh-handoff/handoff.json
mkdir -p dsh-handoff/downloads
bash scripts/dsh-download-media.sh "${MUSIC_URL}#dsh-audio" 720
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
  --music-title "$MUSIC_TITLE"

python scripts/analyze-viral-edit.py "$FINAL" "$ROOT/final/output-analysis"
ffprobe -v error -show_streams -show_format -of json "$FINAL" > "$ROOT/final/ffprobe.json"

python - <<'PY'
import json
from pathlib import Path
root=Path('dsh-handoff/anime-v09-alt')
p=json.load(open(root/'final/ffprobe.json'))
plan=json.load(open(root/'final/edit-plan.json'))
v=next(s for s in p['streams'] if s['codec_type']=='video')
a=next(s for s in p['streams'] if s['codec_type']=='audio')
d=float(p['format']['duration'])
assert int(v['width'])==1080 and int(v['height'])==1920
assert 19.90<=d<=20.10
assert int(a['sample_rate'])==48000
assert int(p['format']['size'])>1000000
assert plan['flow']=='v0.9-readability-first'
assert plan['strategy']=='continuous_combat'
assert plan['hard_source_jumps_added']==0
assert plan['speed_warp_applied'] is False
assert plan['technical_pass'] is True
assert plan['readability_pass'] is True
assert plan['creative_pass'] is True
manifest={
  'flow':'v0.9-readability-first',
  'source_selection':json.load(open(root/'source-selection.json')),
  'music_selection':json.load(open(root/'music-selection.json')),
  'edit_plan':plan,
  'qa':{'technical_pass':True,'readability_pass':True,'creative_pass':True,'duration_sec':d,'width':1080,'height':1920}
}
(root/'final/SOURCE_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print('V0.9 ALT QA PASS',json.dumps(manifest['qa']))
PY

test -s "$FINAL"
