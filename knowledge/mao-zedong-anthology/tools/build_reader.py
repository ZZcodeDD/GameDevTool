#!/usr/bin/env python3
"""Build a searchable offline HTML reader + print HTML for MaoZeDongAnthology.

Features inspired by HowToLiveBetter offline reader:
- volume / article sidebar
- full-text search
- in-article footnote markers jump to 注释
- notes jump back to the marker
- hash deep-links: #v1-a011 or ?q=
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VOL_DIR = ROOT / "volumes"
OUT_HTML = ROOT / "index.html"
OUT_PRINT = ROOT / "print.html"
OUT_META = ROOT / "catalog.json"

CIRCLED = "⑴⑵⑶⑷⑸⑹⑺⑻⑼⑽⑾⑿⒀⒁⒂⒃⒄⒅⒆⒇"
CIRCLED_MAP = {ch: i + 1 for i, ch in enumerate(CIRCLED)}

VOLUME_META = [
    ("001", "第一卷", "国内革命战争时期", "官方"),
    ("002", "第二卷", "抗日战争时期（上）", "官方"),
    ("003", "第三卷", "抗日战争时期（下）", "官方"),
    ("004", "第四卷", "第三次国内革命战争时期", "官方"),
    ("005", "第五卷", "社会主义革命和社会主义建设时期（一）", "官方"),
    ("006", "第六卷", "社会主义革命和社会主义建设时期（二）", "非官方·静火"),
    ("007", "第七卷", "文化大革命时期", "非官方·静火"),
]


@dataclass
class Article:
    id: str
    volume: str
    volume_no: str
    volume_title: str
    official: bool
    path: str
    file: str
    seq: str
    title: str
    date: str
    intro: str
    body_html: str
    notes_html: str
    note_count: int
    search_text: str
    subsections: list[str] = field(default_factory=list)


def slugify(s: str) -> str:
    s = re.sub(r"\s+", "-", s.strip())
    s = re.sub(r"[^\w\u4e00-\u9fff\-]+", "", s)
    return s[:80] or "x"


def parse_article(path: Path, vol_no: str, vol_title: str, official: bool) -> Article:
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    title = path.stem
    date = ""
    intro_lines: list[str] = []
    body_lines: list[str] = []
    note_lines: list[str] = []
    mode = "head"  # head | intro | body | notes
    i = 0
    while i < len(lines):
        line = lines[i]
        if mode == "head":
            if line.startswith("# "):
                title = line[2:].strip()
                i += 1
                continue
            m = re.match(r"^（([^）]+)）\s*$", line.strip())
            if m:
                date = m.group(1)
                i += 1
                continue
            if line.strip().startswith(">"):
                mode = "intro"
                continue
            if line.strip() and not line.strip().startswith("#"):
                mode = "body"
                continue
            i += 1
            continue
        if mode == "intro":
            if line.strip().startswith(">"):
                intro_lines.append(re.sub(r"^>\s?", "", line))
                i += 1
                continue
            if not line.strip():
                i += 1
                # peek: more blockquote?
                if i < len(lines) and lines[i].strip().startswith(">"):
                    continue
                mode = "body"
                continue
            mode = "body"
            continue
        if mode == "body":
            if re.match(r"^-{5,}\s*$", line.strip()):
                # next non-empty should be 注释
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j < len(lines) and re.match(r"^注释\s*$", lines[j].strip()):
                    mode = "notes"
                    i = j + 1
                    continue
            body_lines.append(line)
            i += 1
            continue
        if mode == "notes":
            note_lines.append(line)
            i += 1
            continue
        i += 1

    seq_m = re.match(r"^(\d+)-", path.name)
    seq = seq_m.group(1) if seq_m else "000"
    art_id = f"v{int(vol_no)}-a{seq}"

    subsections = []
    for ln in body_lines:
        if ln.startswith("## "):
            subsections.append(ln[3:].strip())

    body_html, note_count_from_body = render_body("\n".join(body_lines), art_id)
    notes_html, note_count = render_notes("\n".join(note_lines), art_id)
    note_count = max(note_count, note_count_from_body)

    intro = "\n".join(intro_lines).strip()
    search_text = "\n".join(
        [title, date, intro, "\n".join(body_lines), "\n".join(note_lines)]
    )

    rel = str(path.relative_to(VOL_DIR))
    return Article(
        id=art_id,
        volume=f"{vol_no}-{vol_title}",
        volume_no=vol_no,
        volume_title=vol_title,
        official=official,
        path=rel,
        file=path.name,
        seq=seq,
        title=title,
        date=date,
        intro=intro,
        body_html=body_html,
        notes_html=notes_html,
        note_count=note_count,
        search_text=search_text,
        subsections=subsections,
    )


def md_inline(text: str) -> str:
    text = html.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    return text


def link_footnotes(text: str, art_id: str) -> str:
    """Turn footnote markers into jump links. text is already HTML-escaped."""

    def repl_circled(m: re.Match) -> str:
        ch = m.group(0)
        n = CIRCLED_MAP[ch]
        return (
            f'<a class="fn" id="{art_id}-fnref-{n}" href="#{art_id}-fn-{n}" '
            f'title="查看注释〔{n}〕">{ch}</a>'
        )

    text = re.sub("[" + CIRCLED + "]", repl_circled, text)

    # halfwidth (12) style markers common in some articles
    def repl_paren(m: re.Match) -> str:
        n = int(m.group(1))
        if n < 1 or n > 200:
            return m.group(0)
        return (
            f'<a class="fn" id="{art_id}-fnref-{n}" href="#{art_id}-fn-{n}" '
            f'title="查看注释〔{n}〕">({n})</a>'
        )

    text = re.sub(r"\((\d{1,3})\)", repl_paren, text)

    # 《title》 cross refs — leave as marked spans for potential nav
    text = re.sub(
        r"《([^》]+)》",
        r'<span class="xref">《\1》</span>',
        text,
    )
    return text


def render_body(md: str, art_id: str) -> tuple[str, int]:
    parts: list[str] = []
    para: list[str] = []
    max_holder = [0]

    def flush_para():
        nonlocal para
        if not para:
            return
        text = re.sub(r"\s+", " ", "".join(para).strip())
        if text:
            linked = link_footnotes(md_inline(text), art_id)
            parts.append(f"<p>{linked}</p>")
            for ch, n in CIRCLED_MAP.items():
                if ch in text:
                    max_holder[0] = max(max_holder[0], n)
            for m in re.finditer(r"\((\d{1,3})\)", text):
                max_holder[0] = max(max_holder[0], int(m.group(1)))
        para = []

    for line in md.splitlines():
        if line.startswith("## "):
            flush_para()
            h = md_inline(line[3:].strip())
            hid = f"{art_id}-h-{slugify(line[3:])}"
            parts.append(f'<h2 id="{hid}">{h}</h2>')
            continue
        if line.startswith("### "):
            flush_para()
            h = md_inline(line[4:].strip())
            hid = f"{art_id}-h-{slugify(line[4:])}"
            parts.append(f'<h3 id="{hid}">{h}</h3>')
            continue
        if not line.strip():
            flush_para()
            continue
        para.append(line)
    flush_para()
    return "\n".join(parts), max_holder[0]


def render_notes(md: str, art_id: str) -> tuple[str, int]:
    if not md.strip():
        return "", 0
    items: list[tuple[int, str]] = []
    cur_n: int | None = None
    cur_buf: list[str] = []

    def flush():
        nonlocal cur_n, cur_buf
        if cur_n is None:
            return
        items.append((cur_n, "".join(cur_buf).strip()))
        cur_n = None
        cur_buf = []

    for line in md.splitlines():
        m = re.match(r"^〔(\d+)〕\s*(.*)$", line.strip())
        if m:
            flush()
            cur_n = int(m.group(1))
            cur_buf = [m.group(2)]
            continue
        if cur_n is not None:
            cur_buf.append("\n" + line)
    flush()

    if not items:
        # fallback: whole block as plain
        return f"<div class='notes-plain'><pre>{html.escape(md)}</pre></div>", 0

    out = ['<ol class="notes">']
    for n, text in items:
        # internal "见本卷《xxx》注〔n〕"
        linked = link_footnotes(md_inline(re.sub(r"\s+", " ", text)), art_id)
        linked = re.sub(
            r"见本卷《([^》]+)》注〔(\d+)〕",
            r'见本卷《\1》注〔\2〕',
            linked,
        )
        out.append(
            f'<li id="{art_id}-fn-{n}" value="{n}">'
            f'<a class="fn-back" href="#{art_id}-fnref-{n}" title="回到正文">〔{n}〕</a> '
            f"{linked}</li>"
        )
    out.append("</ol>")
    return "\n".join(out), len(items)


def collect_articles() -> list[Article]:
    articles: list[Article] = []
    for vol_no, short, period, kind in VOLUME_META:
        matches = sorted(VOL_DIR.glob(f"{vol_no}-*"))
        if not matches:
            continue
        vol_path = matches[0]
        vol_title = f"{short}　{period}"
        official = kind.startswith("官方")
        for md in sorted(vol_path.rglob("*.md")):
            articles.append(parse_article(md, vol_no, vol_title, official))
    articles.sort(key=lambda a: (a.volume_no, a.seq, a.title))
    return articles


def build_catalog(articles: list[Article]) -> dict:
    vols = []
    for vol_no, short, period, kind in VOLUME_META:
        items = [a for a in articles if a.volume_no == vol_no]
        vols.append(
            {
                "no": vol_no,
                "short": short,
                "period": period,
                "kind": kind,
                "count": len(items),
                "articles": [
                    {
                        "id": a.id,
                        "seq": a.seq,
                        "title": a.title,
                        "date": a.date,
                        "note_count": a.note_count,
                        "subsections": a.subsections,
                    }
                    for a in items
                ],
            }
        )
    return {
        "title": "毛泽东选集",
        "source": "https://github.com/NpTIme/MaoZeDongAnthology",
        "article_count": len(articles),
        "volumes": vols,
    }


READER_CSS = r"""
:root{
  --bg:#0a0a0a; --bg-alt:#141414; --panel:#111; --ink:#f2f2f2; --muted:#a3a3a3;
  --accent:#e8e8e8; --accent-2:#ffffff; --line:#2a2a2a; --fn:#f5c542;
  --shadow:0 10px 30px rgba(0,0,0,.45);
  --font:"Source Han Serif SC","Noto Serif SC","Songti SC","SimSun",serif;
  --sans:"IBM Plex Sans","Noto Sans SC","PingFang SC",sans-serif;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0;background:var(--bg);color:var(--ink);font:16px/1.75 var(--font)}
body{min-height:100vh}
a{color:#f5c542;text-decoration:none}
a:hover{text-decoration:underline;color:#ffe08a}
.app{display:grid;grid-template-columns:320px 1fr;min-height:100vh}
.side{position:sticky;top:0;height:100vh;overflow:auto;background:linear-gradient(180deg,#0f0f0f,#0a0a0a 55%,#0d0d0d);border-right:1px solid var(--line);padding:18px 14px 40px}
.brand{padding:8px 10px 16px}
.brand h1{margin:0;font:700 22px/1.25 var(--sans);letter-spacing:.04em;color:#fff}
.brand h1 a{color:#fff}
.brand p{margin:8px 0 0;color:var(--muted);font:13px/1.5 var(--sans)}
.search{position:relative;margin:0 8px 14px}
.search input{width:100%;height:40px;border:1px solid var(--line);border-radius:10px;padding:0 12px 0 36px;background:var(--bg-alt);font:14px var(--sans);color:var(--ink)}
.search input::placeholder{color:#777}
.search input:focus{outline:0;border-color:#555;background:#181818}
.search svg{position:absolute;left:12px;top:50%;transform:translateY(-50%);width:16px;height:16px;stroke:#888;fill:none;stroke-width:2}
.vol{margin:0 4px 10px;border:1px solid transparent;border-radius:12px}
.vol>button{width:100%;text-align:left;border:0;background:transparent;padding:10px 12px;border-radius:12px;cursor:pointer;font:600 14px/1.35 var(--sans);color:var(--ink)}
.vol>button:hover,.vol.active>button{background:rgba(255,255,255,.06)}
.vol .meta{display:block;margin-top:2px;font:12px/1.3 var(--sans);color:var(--muted);font-weight:500}
.alist{display:none;padding:0 4px 8px}
.vol.open .alist{display:block}
.alist a{display:block;padding:7px 10px;border-radius:8px;color:#e5e5e5;font:13px/1.4 var(--sans)}
.alist a:hover,.alist a.active{background:#1a1a1a;box-shadow:inset 0 0 0 1px #333;text-decoration:none;color:#fff}
.alist a .d{display:block;color:#888;font-size:11px;margin-top:2px}
.main{padding:28px 7vw 80px;max-width:980px}
.hero{margin-bottom:22px;padding:22px 24px;border-radius:18px;background:
  radial-gradient(1000px 220px at 12% -30%, rgba(245,197,66,.12), transparent 55%),
  linear-gradient(160deg,#151515,#0f0f0f 60%,#121212);border:1px solid var(--line);box-shadow:var(--shadow)}
.hero h2{margin:0 0 8px;font:700 30px/1.25 var(--sans);color:#fff}
.hero p{margin:0;color:var(--muted);font:14px/1.6 var(--sans);max-width:62ch}
.toolbar{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0 0}
.chip{border:1px solid #333;background:#161616;border-radius:999px;padding:6px 12px;font:12px var(--sans);color:#ccc}
.results{display:none;margin:18px 0;padding:14px;border:1px solid var(--line);border-radius:14px;background:var(--bg-alt)}
.results h3{margin:0 0 8px;font:600 15px var(--sans);color:#fff}
.results a{display:block;padding:8px 6px;border-bottom:1px solid var(--line);font:14px/1.45 var(--sans);color:#eee}
.results a:last-child{border-bottom:0}
.results a small{display:block;color:var(--muted);margin-top:2px}
.article{display:none}
.article.on{display:block;animation:fade .25s ease}
@keyframes fade{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
.article header{margin-bottom:18px;padding-bottom:14px;border-bottom:1px solid var(--line)}
.article header .crumb{font:12px var(--sans);color:var(--muted);margin-bottom:8px}
.article h1{margin:0 0 8px;font:700 28px/1.3 var(--sans);color:#fff}
.article .date{color:#f5c542;font:600 14px var(--sans)}
.intro{margin:16px 0 22px;padding:14px 16px;border-left:3px solid #f5c542;background:rgba(255,255,255,.04);color:#d4d4d4;font-size:15px}
.body p{margin:0 0 1.05em;text-indent:2em;color:#f0f0f0}
.body h2{margin:1.6em 0 .7em;font:700 22px/1.35 var(--sans);color:#fff}
.body h3{margin:1.3em 0 .55em;font:700 18px/1.35 var(--sans);color:#f5f5f5}
a.fn{color:var(--fn);font-weight:700;padding:0 .1em;border-radius:3px}
a.fn:target, li:target{background:#3a3110;outline:2px solid #f5c542}
.notes-wrap{margin-top:36px;padding-top:18px;border-top:2px solid var(--line)}
.notes-wrap h2{margin:0 0 12px;font:700 20px var(--sans);color:#fff}
.notes{margin:0;padding:0;list-style:none}
.notes li{margin:0 0 12px;padding:10px 12px;border-radius:10px;background:rgba(255,255,255,.03);border:1px solid transparent;font-size:14.5px;line-height:1.7;color:#ddd}
.notes li:hover{border-color:#333}
.fn-back{font-weight:700;margin-right:.25em;color:#f5c542}
.empty{padding:40px 10px;color:var(--muted);font:15px var(--sans)}
.foot{margin-top:40px;padding-top:16px;border-top:1px solid var(--line);color:#888;font:12px/1.6 var(--sans)}
.foot a{color:#f5c542}
@media (max-width:900px){
  .app{grid-template-columns:1fr}
  .side{position:relative;height:auto;max-height:none;border-right:0;border-bottom:1px solid var(--line)}
  .main{padding:20px 18px 60px}
  .article h1{font-size:24px}
}
@media print{
  :root{--bg:#fff;--ink:#000;--muted:#444;--line:#ccc}
  body{background:#fff;color:#000}
  .side,.search,.toolbar,.results{display:none!important}
  .app{display:block}
  .main{max-width:none;padding:0}
  .article{display:block!important;break-before:page;color:#000}
  .article:first-of-type{break-before:auto}
  .article h1,.body h2,.body h3,.body p,.intro,.notes li{color:#000}
  a.fn{color:#000;font-weight:700}
}
"""

READER_JS = r"""
const catalog = window.__CATALOG__;
const corpus = window.__CORPUS__;
const qEl = document.getElementById('q');
const resultsEl = document.getElementById('results');
const articleEls = new Map([...document.querySelectorAll('.article')].map(el => [el.id, el]));

function openVol(no, forceOpen){
  document.querySelectorAll('.vol').forEach(v => {
    const on = v.dataset.no === no;
    v.classList.toggle('active', on);
    if (on) v.classList.add('open');
    else if (!forceOpen) {/* keep others as-is */}
  });
}

function showArticle(id, hash){
  articleEls.forEach(el => el.classList.remove('on'));
  const el = articleEls.get(id);
  if (!el) return;
  el.classList.add('on');
  document.getElementById('home').style.display = 'none';
  resultsEl.style.display = 'none';
  document.querySelectorAll('.alist a').forEach(a => a.classList.toggle('active', a.dataset.id === id));
  const art = corpus[id];
  if (art) openVol(art.volume_no, true);
  history.replaceState(null, '', '#' + id + (hash ? '-' + hash : ''));
  const target = hash ? document.getElementById(id + '-' + hash) : el;
  (target || el).scrollIntoView({behavior:'smooth', block:'start'});
}

function showHome(){
  articleEls.forEach(el => el.classList.remove('on'));
  document.getElementById('home').style.display = 'block';
  document.querySelectorAll('.alist a').forEach(a => a.classList.remove('active'));
  history.replaceState(null, '', location.pathname + location.search);
}

function search(q){
  q = (q || '').trim().toLowerCase();
  if (!q){ resultsEl.style.display='none'; return; }
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
  // id or id-fn-3 or id-fnref-3
  const m = h.match(/^(v\d+-a\d+)(?:-(.+))?$/);
  if (m){ showArticle(m[1], m[2] || ''); return; }
  showHome();
}

document.querySelectorAll('.vol > button').forEach(btn => {
  btn.addEventListener('click', () => {
    const vol = btn.parentElement;
    vol.classList.toggle('open');
    document.querySelectorAll('.vol').forEach(v => v.classList.toggle('active', v === vol));
  });
});
document.querySelectorAll('.alist a').forEach(a => {
  a.addEventListener('click', e => { e.preventDefault(); showArticle(a.dataset.id); });
});
document.getElementById('homeLink').addEventListener('click', e => { e.preventDefault(); showHome(); qEl.value=''; search(''); });
qEl.addEventListener('input', () => search(qEl.value));
window.addEventListener('hashchange', route);
const params = new URLSearchParams(location.search);
if (params.get('q')) { qEl.value = params.get('q'); search(qEl.value); }
route();
"""


def shell_html(catalog: dict, articles: list[Article], *, print_mode: bool = False) -> str:
    # Lightweight corpus for search + routing (exclude heavy HTML)
    corpus = {
        a.id: {
            "title": a.title,
            "date": a.date,
            "volume_no": a.volume_no,
            "volume_title": a.volume_title,
            "search": a.search_text[:20000],
        }
        for a in articles
    }

    side_parts = []
    for v in catalog["volumes"]:
        links = []
        for a in v["articles"]:
            sub = a["date"] or (f"注释 {a['note_count']} 条" if a["note_count"] else "")
            links.append(
                f'<a href="#{html.escape(a["id"])}" data-id="{html.escape(a["id"])}">'
                f'{html.escape(a["seq"]+". "+a["title"])}'
                f'<span class="d">{html.escape(sub)}</span></a>'
            )
        side_parts.append(
            f'<div class="vol" data-no="{v["no"]}">'
            f'<button type="button">{html.escape(v["short"])}'
            f'<span class="meta">{html.escape(v["period"])} · {v["count"]} 篇 · {html.escape(v["kind"])}</span></button>'
            f'<div class="alist">{"".join(links)}</div></div>'
        )

    article_parts = []
    for a in articles:
        intro_html = f'<div class="intro">{md_inline(a.intro)}</div>' if a.intro else ""
        notes = ""
        if a.notes_html:
            notes = f'<section class="notes-wrap"><h2>注释</h2>{a.notes_html}</section>'
        article_parts.append(
            f'<article class="article" id="{html.escape(a.id)}" data-volume="{html.escape(a.volume_no)}">'
            f'<header><div class="crumb">{html.escape(a.volume_title)}'
            f'{" · 非官方静火整理" if not a.official else ""}</div>'
            f'<h1>{html.escape(a.title)}</h1>'
            f'{f"<div class=date>（{html.escape(a.date)}）</div>" if a.date else ""}'
            f"</header>{intro_html}<div class='body'>{a.body_html}</div>{notes}</article>"
        )

    mode_class = "print-root" if print_mode else "app"
    home_display = "none" if print_mode else "block"
    articles_force = ""
    if print_mode:
        # show all articles for print/PDF
        articles_force = "<style>.article{display:block!important}.side,.search,#results,#home{display:none!important}.app{display:block}.main{padding:24px}</style>"

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>毛泽东选集 · 可检索阅读版</title>
<meta name="description" content="毛泽东选集七卷本地知识库阅读器：按卷浏览、全文检索、注释跳转。第一至五卷为官方版本，第六、七卷为静火非官方整理。">
<style>{READER_CSS}</style>
{articles_force}
</head>
<body>
<div class="{mode_class}">
  <aside class="side">
    <div class="brand">
      <h1><a href="#" id="homeLink">毛泽东选集</a></h1>
      <p>七卷 · {catalog['article_count']} 篇<br>章节目录 · 注释跳转 · 全文检索</p>
    </div>
    <label class="search">
      <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>
      <input id="q" type="search" placeholder="搜索篇名或正文" autocomplete="off" aria-label="搜索">
    </label>
    {''.join(side_parts)}
  </aside>
  <main class="main">
    <section id="home" class="hero" style="display:{home_display}">
      <h2>毛泽东选集</h2>
      <p>官方五卷与静火整理两卷的 Markdown 知识库阅读版。左侧按卷展开篇目；正文中的 ⑴ / (1) 可跳到文末注释，注释号可跳回原文。支持全文检索与 URL 深链。</p>
      <div class="toolbar">
        <span class="chip">{catalog['article_count']} 篇</span>
        <span class="chip">7 卷</span>
        <span class="chip">注释双向跳转</span>
        <span class="chip">来源 NpTIme/MaoZeDongAnthology</span>
      </div>
      <p style="margin-top:14px">第六、七卷为非官方版本，可能有错误或误导，请注意鉴别。标题前序号仅为排序方便，不存在于原文。</p>
    </section>
    <div id="results" class="results"></div>
    {''.join(article_parts)}
    <footer class="foot">
      正文整理来自 <a href="https://github.com/NpTIme/MaoZeDongAnthology" target="_blank" rel="noopener">NpTIme/MaoZeDongAnthology</a>。
      本页为本地知识库阅读器（章节 / 检索 / 注释跳转），生成自仓库构建脚本，不改变原文表述。
    </footer>
  </main>
</div>
<script>
window.__CATALOG__ = {json.dumps(catalog, ensure_ascii=False)};
window.__CORPUS__ = {json.dumps(corpus, ensure_ascii=False)};
{READER_JS if not print_mode else "document.querySelectorAll('.article').forEach(el=>el.classList.add('on'));"}
</script>
</body>
</html>
"""


def main() -> int:
    print("Collecting articles…", flush=True)
    articles = collect_articles()
    if not articles:
        print("No articles found under", VOL_DIR, file=sys.stderr)
        return 1
    catalog = build_catalog(articles)
    OUT_META.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    html_doc = shell_html(catalog, articles, print_mode=False)
    OUT_HTML.write_text(html_doc, encoding="utf-8")
    print_html = shell_html(catalog, articles, print_mode=True)
    OUT_PRINT.write_text(print_html, encoding="utf-8")
    print(
        f"Built {OUT_HTML} ({OUT_HTML.stat().st_size/1024/1024:.1f} MB), "
        f"{OUT_PRINT.name} ({OUT_PRINT.stat().st_size/1024/1024:.1f} MB), "
        f"{len(articles)} articles",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
