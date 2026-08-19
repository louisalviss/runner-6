from pathlib import Path

p = Path('dsh-console/index.html')
s = p.read_text(encoding='utf-8')

repls = [
    (
        ".orb.error,.orb.failure,.orb.missing_chat_key,.orb.decrypt_error,.orb.missing_openrouter_key{background:var(--red)}",
        ".orb.error,.orb.failure,.orb.timeout,.orb.missing_chat_key,.orb.decrypt_error,.orb.missing_openrouter_key{background:var(--red)}",
    ),
    (
        "else if(st==='decrypt_error')$('state').textContent='Runner 6 · decrypt error';else if(st==='error'||st==='failure'||st==='missing_openrouter_key')$('state').textContent='Runner 6 · error';",
        "else if(st==='decrypt_error')$('state').textContent='Runner 6 · decrypt error';else if(st==='timeout')$('state').textContent='Runner 6 · timeout';else if(st==='error'||st==='failure'||st==='missing_openrouter_key')$('state').textContent='Runner 6 · error';",
    ),
    (
        "if(['success','error','missing_openrouter_key'].includes(s.status)){",
        "if(['success','error','timeout','failure','missing_openrouter_key'].includes(s.status)){",
    ),
]

for old, new in repls:
    if old not in s:
        raise SystemExit(f'Expected console fragment not found: {old[:100]}')
    s = s.replace(old, new, 1)

p.write_text(s, encoding='utf-8')
print('patched DSH console terminal statuses')
