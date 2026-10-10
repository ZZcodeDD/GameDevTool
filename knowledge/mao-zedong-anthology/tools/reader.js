const catalog = window.__CATALOG__;
const corpus = window.__CORPUS__;
const qEl = document.getElementById('q');
const resultsEl = document.getElementById('results');
const articleEls = new Map([...document.querySelectorAll('.article')].map(el => [el.id, el]));
const learnEls = new Map([...document.querySelectorAll('.learn-page')].map(el => [el.id, el]));
const backTop = document.getElementById('backTop');

function hideAllMain(){
  articleEls.forEach(el => el.classList.remove('on'));
  learnEls.forEach(el => el.classList.remove('on'));
  document.getElementById('home').style.display = 'none';
  resultsEl.style.display = 'none';
  document.querySelectorAll('.alist a').forEach(a => a.classList.remove('active'));
  document.querySelectorAll('.learn-nav-a').forEach(a => a.classList.remove('active'));
}

function openVol(no, forceOpen){
  document.querySelectorAll('.vol').forEach(v => {
    const on = v.dataset.no === no;
    v.classList.toggle('active', on);
    if (on) v.classList.add('open');
    else if (forceOpen) v.classList.remove('open');
  });
}

function showArticle(id, hash){
  hideAllMain();
  const el = articleEls.get(id);
  if (!el) return;
  el.classList.add('on');
  document.querySelectorAll('.alist a').forEach(a => a.classList.toggle('active', a.dataset.id === id));
  const art = corpus[id];
  if (art) openVol(art.volume_no, true);
  history.replaceState(null, '', '#' + id + (hash ? '-' + hash : ''));
  const target = hash ? document.getElementById(id + '-' + hash) : el;
  requestAnimationFrame(() => (target || el).scrollIntoView({behavior:'smooth', block: hash ? 'center' : 'start'}));
}

function showLearn(id){
  hideAllMain();
  const el = learnEls.get(id);
  if (!el){ showHome(); return; }
  el.classList.add('on');
  document.querySelectorAll('.learn-nav-a').forEach(a => a.classList.toggle('active', a.dataset.learn === id));
  if (id.startsWith('learn-theme-')) {
    document.querySelector('.nav-fold[data-fold="themes"]')?.classList.add('open');
  }
  history.replaceState(null, '', '#' + id);
  el.scrollIntoView({behavior:'smooth', block:'start'});
}

function showHome(){
  hideAllMain();
  document.getElementById('home').style.display = 'block';
  history.replaceState(null, '', location.pathname + location.search);
}

function search(q){
  q = (q || '').trim().toLowerCase();
  if (!q){ resultsEl.style.display='none'; return; }
  hideAllMain();
  const hits = [];
  for (const id of Object.keys(corpus)){
    const a = corpus[id];
    const idx = a.search.toLowerCase().indexOf(q);
    if (idx < 0) continue;
    const snip = a.search.slice(Math.max(0, idx-24), idx+48).replace(/\s+/g,' ');
    hits.push({id, title:a.title, volume:a.volume_title, snip, date:a.date});
    if (hits.length >= 40) break;
  }
  resultsEl.style.display = 'block';
  resultsEl.innerHTML = `<h3>检索结果 · ${hits.length}${hits.length>=40?'+':''}</h3>` +
    (hits.length ? hits.map(h => `<a href="#${h.id}" data-id="${h.id}"><strong>${escapeHtml(h.title)}</strong><small>${escapeHtml(h.volume)}${h.date?' · '+escapeHtml(h.date):''}<br>…${escapeHtml(h.snip)}…</small></a>`).join('')
      : '<p class="empty">没有匹配条目。试试更短的关键词。</p>');
  resultsEl.querySelectorAll('a[data-id]').forEach(a => a.addEventListener('click', e => {
    e.preventDefault(); showArticle(a.dataset.id);
  }));
}

function escapeHtml(s){
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function route(){
  const h = decodeURIComponent(location.hash.replace(/^#/, ''));
  if (!h){ showHome(); return; }
  if (h.startsWith('learn-')){ showLearn(h); return; }
  const m = h.match(/^(v\d+-a\d+)(?:-(.+))?$/);
  if (m){ showArticle(m[1], m[2] || ''); return; }
  showHome();
}

document.querySelectorAll('.vol > button').forEach(btn => {
  btn.addEventListener('click', () => {
    const vol = btn.parentElement;
    const willOpen = !vol.classList.contains('open');
    if (willOpen) {
      document.querySelectorAll('.vol').forEach(v => v.classList.remove('open', 'active'));
      vol.classList.add('open', 'active');
    } else {
      vol.classList.remove('open', 'active');
    }
  });
});

document.querySelectorAll('.nav-fold-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const fold = btn.parentElement;
    const open = fold.classList.toggle('open');
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
  });
});

document.getElementById('collapseAllVols')?.addEventListener('click', () => {
  document.querySelectorAll('.vol').forEach(v => v.classList.remove('open', 'active'));
});

document.querySelectorAll('.alist a, a.learn-art').forEach(a => {
  a.addEventListener('click', e => {
    const id = a.dataset.id;
    if (!id) return;
    e.preventDefault();
    showArticle(id);
  });
});

document.querySelectorAll('[data-learn]').forEach(a => {
  a.addEventListener('click', e => {
    e.preventDefault();
    showLearn(a.dataset.learn);
  });
});

document.querySelectorAll('.open-vol').forEach(btn => {
  btn.addEventListener('click', () => {
    openVol(btn.dataset.vol, true);
    const vol = document.querySelector(`.vol[data-no="${btn.dataset.vol}"]`);
    if (vol) {
      vol.classList.add('open', 'active');
      vol.scrollIntoView({behavior:'smooth', block:'nearest'});
    }
  });
});

document.querySelectorAll('[data-back-learn]').forEach(btn => {
  btn.addEventListener('click', () => showLearn(btn.dataset.backLearn || 'learn-overview'));
});

document.querySelectorAll('[data-scroll-notes]').forEach(btn => {
  btn.addEventListener('click', () => {
    const art = btn.closest('.article');
    const notes = art?.querySelector('.notes-fold, .notes-wrap');
    if (notes) {
      if (notes.tagName === 'DETAILS') notes.open = true;
      notes.scrollIntoView({behavior:'smooth', block:'start'});
    }
  });
});

document.getElementById('homeLink').addEventListener('click', e => {
  e.preventDefault(); showHome(); qEl.value=''; resultsEl.style.display='none';
});
qEl.addEventListener('input', () => search(qEl.value));
window.addEventListener('hashchange', route);
window.addEventListener('scroll', () => {
  if (!backTop) return;
  backTop.classList.toggle('show', window.scrollY > 600);
});
backTop?.addEventListener('click', () => window.scrollTo({top:0, behavior:'smooth'}));

const params = new URLSearchParams(location.search);
if (params.get('q')) { qEl.value = params.get('q'); search(qEl.value); }
route();
