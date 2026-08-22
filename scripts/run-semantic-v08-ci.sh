#!/usr/bin/env bash
set -euo pipefail

ROOT="dsh-handoff/anime-semantic-v08-nc"
FINAL="$ROOT/final/anime_combat_semantic_v08.mp4"
SEED_RUN="32584331575"
SEED_ARTIFACT="anime-combat-beat-sync-final-32584331575"
mkdir -p "$ROOT/final" seed

# Reuse only learned decisions/metadata from prior successful research; never reuse its final video as source.
gh run download "$SEED_RUN" --name "$SEED_ARTIFACT" -D seed
cp seed/learned-combat-grammar.json "$ROOT/learned-combat-grammar.json"
cp seed/source-selection.json "$ROOT/source-selection.json"
cp seed/music-selection.json "$ROOT/music-selection.json"
cp seed/reference-ranking.json "$ROOT/reference-ranking.json"

# Redownload original ranked production source through DSH.
URL="$(python -c "import json;print(json.load(open('$ROOT/source-selection.json'))['selected']['url'])")"
rm -rf dsh-handoff/downloads dsh-handoff/handoff.json
mkdir -p dsh-handoff/downloads
bash scripts/dsh-download-media.sh "$URL" 720
P="$(python -c "import json;print(json.load(open('dsh-handoff/handoff.json'))['relative_path'])")"
ffmpeg -nostdin -hide_banner -y -v error -i "$P" -t 420 -map 0:v:0 -map 0:a? -c:v libx264 -preset veryfast -crf 18 -c:a aac -ar 48000 -b:a 160k -movflags +faststart "$ROOT/final/source.mp4"
test -s "$ROOT/final/source.mp4"
python scripts/analyze-viral-edit.py "$ROOT/final/source.mp4" "$ROOT/final/source-analysis"

# Redownload the clean selected phonk master through DSH.
MURL="$(python -c "import json;print(json.load(open('$ROOT/music-selection.json'))['clean_audio_url'])")"
MTITLE="$(python -c "import json;d=json.load(open('$ROOT/music-selection.json'));print(d['title']+' — '+d['artist'])")"
rm -rf dsh-handoff/downloads dsh-handoff/handoff.json
mkdir -p dsh-handoff/downloads
bash scripts/dsh-download-media.sh "${MURL}#dsh-audio" 720
P="$(python -c "import json;print(json.load(open('dsh-handoff/handoff.json'))['relative_path'])")"
ffmpeg -nostdin -hide_banner -y -v error -i "$P" -vn -ar 48000 -ac 2 -c:a pcm_s16le "$ROOT/final/music-master.wav"
test "$(stat -c '%s' "$ROOT/final/music-master.wav")" -gt 1000000

# Build a NEW semantic timeline from original source + actual music phrases.
python scripts/render-learned-anime-combat.py \
  "$ROOT/final/source.mp4" \
  "$ROOT/final/music-master.wav" \
  "$ROOT/learned-combat-grammar.json" \
  "$ROOT/final/source-analysis/analysis.json" \
  "$FINAL" \
  "$ROOT/final/edit-plan.json" \
  --music-title "$MTITLE"
python scripts/analyze-viral-edit.py "$FINAL" "$ROOT/final/output-analysis"
ffprobe -v error -show_streams -show_format -of json "$FINAL" > "$ROOT/final/ffprobe.json"

python - <<'PY'
import json
from pathlib import Path
root=Path('dsh-handoff/anime-semantic-v08-nc')
p=json.load(open(root/'final/ffprobe.json'))
plan=json.load(open(root/'final/edit-plan.json'))
v=next(s for s in p['streams'] if s['codec_type']=='video')
a=next(s for s in p['streams'] if s['codec_type']=='audio')
d=float(p['format']['duration'])
assert int(v['width'])==1080 and int(v['height'])==1920,(v['width'],v['height'])
assert 19.90<=d<=20.10,d
assert int(a['sample_rate'])==48000,a['sample_rate']
assert int(p['format']['size'])>1000000,p['format']['size']
assert plan['editor_mode']=='semantic_phrase_synced_combat',plan.get('editor_mode')
assert plan['technical_pass'] is True
assert plan['creative_pass'] is True
assert plan['semantic_stage_count']>=5,plan['semantic_stage_count']
assert plan['impact_sync_count']>=5,plan['impact_sync_count']
assert plan['post_edit_cuts_added']>=4,plan['post_edit_cuts_added']
assert plan['max_speed_deviation_from_1x']<=0.30,plan['max_speed_deviation_from_1x']
assert plan['semantic_segments'][-1]['target_impact_sec']>=15.0,plan['semantic_segments'][-1]
manifest={
  'flow':'v0.8-semantic-combat-editor',
  'seed_run':32584331575,
  'reference_ranking':json.load(open(root/'reference-ranking.json')),
  'music_selection':json.load(open(root/'music-selection.json')),
  'source_selection':json.load(open(root/'source-selection.json')),
  'learned_grammar':json.load(open(root/'learned-combat-grammar.json')),
  'edit_plan':plan,
  'qa':{
    'technical_pass':True,'creative_pass':True,'duration_sec':d,
    'width':int(v['width']),'height':int(v['height']),
    'semantic_stage_count':plan['semantic_stage_count'],
    'impact_sync_count':plan['impact_sync_count'],
    'post_edit_cuts_added':plan['post_edit_cuts_added'],
    'max_speed_deviation_from_1x':plan['max_speed_deviation_from_1x'],
    'full_bleed_frame_ratio':plan['vertical_reframe']['full_bleed_frame_ratio'],
    'hybrid_frame_ratio':plan['vertical_reframe']['hybrid_frame_ratio']
  }
}
(root/'final/SOURCE_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print('SEMANTIC V0.8 QA PASS',json.dumps(manifest['qa'],ensure_ascii=False))
PY

test -s "$FINAL"
