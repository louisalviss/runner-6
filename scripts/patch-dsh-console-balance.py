from pathlib import Path

p = Path('dsh-console/index.html')
s = p.read_text(encoding='utf-8')

css_anchor = "@media(min-width:760px){"
css_insert = ".balancegrid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:8px}.balancebox{background:#111;border:1px solid #343434;border-radius:12px;padding:10px;min-width:0}.balancebox b{display:block;font-size:15px;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.balancebox span{display:block;font-size:9px;color:#777;margin-top:3px;text-transform:uppercase;letter-spacing:.03em}.balanceinfo{font-size:10px;color:#777;margin-top:7px;min-height:15px}"
if css_insert not in s:
    if css_anchor not in s:
        raise SystemExit('CSS anchor not found')
    s = s.replace(css_anchor, css_insert + css_anchor, 1)

html_anchor = '''    <div class="row"><button id="clearChat" class="btn">Clear chat</button><button id="clearKey" class="btn danger">Clear GitHub key</button></div>
    <button id="resetEnc" class="btn full danger">Reset encryption keys</button>'''
html_insert = '''    <div class="label">OpenRouter</div>
    <div class="balancegrid">
      <div class="balancebox"><b id="orCredits">—</b><span>Credits</span></div>
      <div class="balancebox"><b id="orToday">—</b><span>Today</span></div>
      <div class="balancebox"><b id="orLimit">—</b><span>Key limit left</span></div>
    </div>
    <div id="orBalanceInfo" class="balanceinfo">Balance is decrypted only in this browser.</div>
    <button id="refreshBalance" class="btn full">Refresh OpenRouter balance</button>

    <div class="row"><button id="clearChat" class="btn">Clear chat</button><button id="clearKey" class="btn danger">Clear GitHub key</button></div>
    <button id="resetEnc" class="btn full danger">Reset encryption keys</button>'''
if 'id="refreshBalance"' not in s:
    if html_anchor not in s:
        raise SystemExit('HTML anchor not found')
    s = s.replace(html_anchor, html_insert, 1)

js_anchor = "const TOKEN_KEY='dsh_token',HIST='dsh_chat_history_secure_v1',PUB='dsh_rsa_public_jwk_v1',READY='dsh_secure_ready_v1',PEND='dsh_pending_aes_';"
js_new = "const TOKEN_KEY='dsh_token',HIST='dsh_chat_history_secure_v1',PUB='dsh_rsa_public_jwk_v1',READY='dsh_secure_ready_v1',PEND='dsh_pending_aes_',OR_CACHE='openrouter_balance_cache_v1';"
if 'OR_CACHE=' not in s:
    if js_anchor not in s:
        raise SystemExit('JS const anchor not found')
    s = s.replace(js_anchor, js_new, 1)

func_anchor = "function paintStatus(s){"
func_insert = r'''function money(v){return typeof v==='number'&&Number.isFinite(v)?'$'+v.toFixed(v<1?3:2):'—'}
function renderBalance(r){
  if(!r){$('orCredits').textContent='—';$('orToday').textContent='—';$('orLimit').textContent='—';return}
  const credits=r.credits||{},key=r.key||{};
  $('orCredits').textContent=money(credits.remaining);
  $('orToday').textContent=money(key.usage_daily);
  $('orLimit').textContent=money(key.limit_remaining);
  const when=r.checked_at?new Date(r.checked_at).toLocaleString():'';
  let msg=key.valid?'Key active':'Key check failed';
  if(!credits.available&&r.credits_error)msg+=' · credits endpoint unavailable';
  if(when)msg+=' · '+when;
  $('orBalanceInfo').textContent=msg;
}
function loadBalanceCache(){try{const r=JSON.parse(localStorage.getItem(OR_CACHE)||'null');if(r)renderBalance(r)}catch{}}
async function refreshOpenRouterBalance(){
  const btn=$('refreshBalance');
  if(!token.value.trim()){openSheet();$('orBalanceInfo').textContent='Add GitHub key first.';return}
  btn.disabled=true;btn.textContent='Checking…';$('orBalanceInfo').textContent='Encrypted balance check running…';
  let cid='';
  try{
    await syncPublishedEncryption();
    const sec=await encryptTask('openrouter-balance-check-v1');cid=sec.clientId;
    await api('/actions/workflows/openrouter-balance-check.yml/dispatches',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ref:REF,inputs:{payload:sec.payload}})},true);
    const started=Date.now();
    while(Date.now()-started<60000){
      await new Promise(r=>setTimeout(r,1600));
      const st=await repoJson('openrouter-balance-status.json');
      if(String(st.client_id||'')!==String(cid))continue;
      if(st.status==='started')continue;
      if(st.status!=='success')throw Error('Balance check failed: '+(st.status||'unknown'));
      const packed=await repoJson('openrouter-balance-result.enc.json');
      if(String(packed.client_id||'')!==String(cid))continue;
      const result=await decryptResult(packed,cid);
      localStorage.setItem(OR_CACHE,JSON.stringify(result));
      localStorage.removeItem(PEND+cid);
      renderBalance(result);
      btn.textContent='Refresh OpenRouter balance';btn.disabled=false;return;
    }
    throw Error('Balance check timed out');
  }catch(e){
    if(cid)localStorage.removeItem(PEND+cid);
    $('orBalanceInfo').textContent=e.message||'Balance check failed';
    btn.textContent='Refresh OpenRouter balance';btn.disabled=false;
  }
}
$('refreshBalance').onclick=refreshOpenRouterBalance;
loadBalanceCache();

'''
if 'function refreshOpenRouterBalance()' not in s:
    if func_anchor not in s:
        raise SystemExit('Function anchor not found')
    s = s.replace(func_anchor, func_insert + func_anchor, 1)

p.write_text(s, encoding='utf-8')
print('patched DSH console OpenRouter balance UI')
