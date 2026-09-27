// ── check の保存と GitHub 同期（viewer / stats 共通。scraper.py が各ページに埋め込む） ──
// check はまずブラウザ内（localStorage）に保存し、同期が設定されていれば
// 非公開リポジトリの JSON ファイル（GitHub Contents API）にも書き込む。
const Checks = (() => {
  const KEY = 'cinema.checked', CFG_KEY = 'cinema.sync', PENDING_KEY = 'cinema.sync.pending';
  const read = (k, d) => { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch (_) { return d; } };
  const write = (k, v) => { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, JSON.stringify(v)); } catch (_) {} };

  let set = new Set(read(KEY, []));
  // まだ GitHub に書き込めていない変更（id → true:追加 / false:削除）。ページを閉じても失わないよう保存する
  const pending = new Map(read(PENDING_KEY, []));
  let sha = null, timer = null, flushing = false;
  let status = 'off', lastError = '', lastSync = null;
  const listeners = [];
  const cfg = () => read(CFG_KEY, null);
  const emit = () => listeners.forEach(f => f());
  const savePending = () => write(PENDING_KEY, pending.size ? [...pending] : null);
  const setStatus = (s, err = '') => { status = s; lastError = err; if (s === 'ok') lastSync = new Date(); renderStatus(); };

  // ── GitHub Contents API ──
  const HEADERS = token => ({ Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28' });
  async function api(method, body) {
    const c = cfg();
    const path = c.path.split('/').map(encodeURIComponent).join('/');
    return fetch(`https://api.github.com/repos/${c.repo}/contents/${path}`, {
      method, cache: 'no-store',
      headers: { ...HEADERS(c.token), ...(body ? { 'Content-Type': 'application/json' } : {}) },
      body: body ? JSON.stringify(body) : undefined,
    });
  }
  async function errorOf(r) {
    if (r.status === 401) return 'トークンが無効か、期限が切れています。';
    if (r.status === 403) return 'トークンに書き込み権限がありません（Contents: Read and write が必要です）。';
    if (r.status === 404) return 'リポジトリが見つからないか、トークンにアクセス権がありません。';
    let msg = ''; try { msg = (await r.json()).message || ''; } catch (_) {}
    return `GitHub との通信に失敗しました（${r.status} ${msg}）。`;
  }
  async function pull() {
    const r = await api('GET');
    if (r.status === 404) {
      // ファイルが未作成なのか、リポジトリ自体に届かないのかを見分ける
      const c = cfg();
      const repo = await fetch(`https://api.github.com/repos/${c.repo}`, { cache: 'no-store', headers: HEADERS(c.token) });
      if (!repo.ok) throw new Error(await errorOf(repo));
      sha = null;
      return new Set();
    }
    if (!r.ok) throw new Error(await errorOf(r));
    const j = await r.json();
    sha = j.sha;
    const text = new TextDecoder().decode(Uint8Array.from(atob(j.content.replace(/\s/g, '')), ch => ch.charCodeAt(0)));
    return new Set(JSON.parse(text).checked || []);
  }
  async function push(ids) {
    const json = JSON.stringify({ checked: [...ids].sort(), updated: new Date().toISOString() }, null, 2) + '\n';
    const content = btoa(String.fromCharCode(...new TextEncoder().encode(json)));
    const r = await api('PUT', { message: 'Update checked movies', content, ...(sha ? { sha } : {}) });
    if (r.status === 409 || r.status === 422) return false; // 他の端末が先に更新した（sha の不一致）
    if (!r.ok) throw new Error(await errorOf(r));
    sha = (await r.json()).content.sha;
    return true;
  }
  function apply(remote) {
    const next = new Set(remote);
    for (const [id, on] of pending) on ? next.add(id) : next.delete(id);
    const changed = next.size !== set.size || [...next].some(id => !set.has(id));
    set = next;
    write(KEY, [...set]);
    if (changed) emit();
  }
  // GitHub の最新を読み、未送信の変更があれば上乗せして書き込む（競合時は読み直して最大3回）
  async function flush() {
    if (!cfg() || flushing) return;
    flushing = true;
    clearTimeout(timer);
    setStatus('busy');
    try {
      for (let attempt = 0; attempt < 3; attempt++) {
        const remote = await pull();
        const ops = new Map(pending);
        if (!ops.size) { apply(remote); setStatus('ok'); return; }
        for (const [id, on] of ops) on ? remote.add(id) : remote.delete(id);
        if (await push(remote)) {
          for (const [id, on] of ops) if (pending.get(id) === on) pending.delete(id);
          savePending();
          apply(remote);
          setStatus('ok');
          return;
        }
      }
      throw new Error('他の端末との更新が重なり、保存できませんでした。しばらくして再度お試しください。');
    } catch (e) {
      setStatus('error', e.message || String(e));
    } finally {
      flushing = false;
      if (pending.size && status === 'ok') schedule();
    }
  }
  const schedule = () => { clearTimeout(timer); timer = setTimeout(flush, 800); };

  // 別タブでの変更を反映
  addEventListener('storage', e => {
    if (e.key === KEY) { set = new Set(read(KEY, [])); emit(); }
    if (e.key === CFG_KEY) renderStatus();
  });
  // タブに戻ってきたら、他の端末での変更を取り込む
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') flush(); });

  // ── 同期ボタンと設定ダイアログ ──
  const style = document.createElement('style');
  style.textContent = `
.sync-btn{position:relative;width:36px;height:36px;border-radius:50%;display:grid;place-items:center;color:var(--sub);flex-shrink:0}
.sync-btn:hover{background:var(--bg-sub)}
.sync-btn i{position:absolute;right:5px;bottom:6px;width:9px;height:9px;border-radius:50%;border:2px solid var(--bg);background:var(--line)}
.sync-btn[data-s="ok"] i{background:#0ca30c}.sync-btn[data-s="busy"] i{background:#fab219}.sync-btn[data-s="error"] i{background:#d03b3b}
.sync-dlg{border:none;border-radius:12px;padding:0;width:min(440px,calc(100vw - 32px));background:var(--card);color:var(--text);box-shadow:0 12px 40px rgba(0,0,0,.3)}
.sync-dlg::backdrop{background:rgba(0,0,0,.45)}
.sync-dlg form{padding:20px;display:grid;gap:12px}
.sync-dlg h2{font-size:1.05rem;font-weight:800}
.sync-dlg p,.sync-dlg li{font-size:.8rem;color:var(--sub);line-height:1.6}
.sync-dlg label{display:grid;gap:4px;font-size:.78rem;font-weight:700}
.sync-dlg input{height:36px;border:1px solid var(--line);border-radius:6px;padding:0 10px;background:var(--bg);color:var(--text);font-size:.85rem;font-family:inherit}
.sync-dlg details summary{cursor:pointer;font-size:.8rem;font-weight:700;color:var(--sub)}
.sync-dlg ol{padding-left:1.2em;margin-top:6px}
.sync-dlg code{font-size:.75rem;background:var(--bg-sub);padding:1px 4px;border-radius:3px}
.sync-state{font-size:.8rem;font-weight:700;padding:8px 10px;border-radius:6px;background:var(--bg-sub);display:flex;gap:6px;align-items:flex-start}
.sync-state[data-s="error"]{color:#d03b3b}
.sync-actions{display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap}
.sync-actions button{padding:8px 14px;border-radius:999px;font-size:.82rem;font-weight:700;border:1px solid var(--line)}
.sync-actions .primary{background:var(--ink);color:var(--ink-text);border-color:var(--ink)}
.sync-actions .danger{margin-right:auto;color:#d03b3b}`;
  document.head.append(style);

  const btn = document.createElement('button');
  btn.className = 'sync-btn';
  btn.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17.5 19a4.5 4.5 0 0 0 .5-8.97A6 6 0 0 0 6.2 9.5 4.75 4.75 0 0 0 6.5 19z"/></svg><i></i>';
  const dlg = document.createElement('dialog');
  dlg.className = 'sync-dlg';
  dlg.innerHTML = `<form method="dialog">
    <h2>check の同期</h2>
    <p>check した作品を GitHub の非公開リポジトリに保存し、PC やスマホなど複数の端末で共有します。</p>
    <div class="sync-state" id="syncState"></div>
    <label>リポジトリ（所有者/リポジトリ名）<input id="syncRepo" placeholder="stickrope0/cinema-checks" autocomplete="off" spellcheck="false"></label>
    <label>保存するファイル<input id="syncPath" placeholder="checked.json" autocomplete="off" spellcheck="false"></label>
    <label>アクセストークン<input id="syncToken" type="password" placeholder="github_pat_…" autocomplete="off" spellcheck="false"></label>
    <details><summary>準備のしかた</summary><ol>
      <li>GitHub で check 保存用の<b>非公開</b>リポジトリを作ります（例：<code>cinema-checks</code>）。</li>
      <li>Settings → Developer settings → Fine-grained tokens で新しいトークンを作ります。Repository access は <b>Only select repositories</b> で手順1のリポジトリだけを選び、Permissions の <b>Contents</b> を <b>Read and write</b> にします。</li>
      <li>リポジトリ名とトークンをここに入力して「保存して同期」を押します。端末ごとに1回必要です。</li>
    </ol>
    <p>トークンはこのブラウザの中にだけ保存されます。同じ github.io のサイトからは読み取れてしまうので、上記のとおり権限を check 用リポジトリだけに絞ってください。</p></details>
    <div class="sync-actions">
      <button type="button" class="danger" id="syncOff">連携を解除</button>
      <button value="close">閉じる</button>
      <button type="button" class="primary" id="syncSave">保存して同期</button>
    </div>
  </form>`;
  const $d = id => dlg.querySelector('#' + id);

  function renderStatus() {
    const c = cfg();
    const s = c ? status : 'off';
    const label = {
      off: '同期していません（このブラウザにだけ保存）',
      busy: '同期中…',
      ok: `同期済み（${c?.repo ?? ''}${lastSync ? ` ・ ${lastSync.toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit' })}` : ''}）`,
      error: `同期エラー：${lastError}`,
    }[s];
    btn.dataset.s = s;
    btn.title = `check の同期：${label}`;
    btn.setAttribute('aria-label', btn.title);
    const st = $d('syncState');
    st.dataset.s = s;
    st.textContent = s === 'error' ? `同期エラー：${lastError}${pending.size ? `（未送信の変更 ${pending.size}件はこのブラウザに保存されています）` : ''}` : label;
    $d('syncOff').hidden = !c;
  }
  btn.addEventListener('click', () => {
    const c = cfg();
    $d('syncRepo').value = c?.repo || '';
    $d('syncPath').value = c?.path || 'checked.json';
    $d('syncToken').value = c?.token || '';
    renderStatus();
    dlg.showModal();
  });
  $d('syncSave').addEventListener('click', async () => {
    const repo = $d('syncRepo').value.trim().replace(/^https:\/\/github\.com\//, '').replace(/\/+$/, '');
    const path = $d('syncPath').value.trim() || 'checked.json';
    const token = $d('syncToken').value.trim();
    if (!/^[\w.-]+\/[\w.-]+$/.test(repo) || !token) {
      status = 'error'; lastError = 'リポジトリ名（所有者/名前）とトークンを入力してください。'; renderStatus(); return;
    }
    const first = !cfg();
    write(CFG_KEY, { repo, path, token });
    // 初めて接続するときは、このブラウザの check も GitHub 側に合流させる
    if (first) { for (const id of set) if (!pending.has(id)) pending.set(id, true); savePending(); }
    await flush();
  });
  $d('syncOff').addEventListener('click', () => {
    if (!confirm('この端末の同期設定（トークン）を削除します。check はこのブラウザに残ります。')) return;
    write(CFG_KEY, null); pending.clear(); savePending(); sha = null; status = 'off'; renderStatus();
  });

  function mount() {
    const theme = document.querySelector('.theme-btn');
    theme.before(btn);
    document.body.append(dlg);
    renderStatus();
    flush();
  }
  document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', mount) : mount();

  return {
    has: id => set.has(id),
    all: () => new Set(set),
    toggle(id) {
      const on = !set.has(id);
      on ? set.add(id) : set.delete(id);
      write(KEY, [...set]);
      if (cfg()) { pending.set(id, on); savePending(); setStatus('busy'); schedule(); }
      emit();
    },
    remove(id) { if (set.has(id)) this.toggle(id); },
    onChange: fn => listeners.push(fn),
  };
})();
