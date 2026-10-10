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


# title substring -> used to resolve article ids at build time
LEARN_READING = [
    ("中国社会各阶级的分析", "分清敌我友，革命的首要问题"),
    ("反对本本主义", "没有调查就没有发言权，从实际出发"),
    ("实践论", "认识从实践来，还要回到实践去检验"),
    ("矛盾论", "抓主要矛盾与矛盾的特殊性"),
    ("中国革命战争的战略问题", "中国革命战争的特点与全局"),
    ("论持久战", "弱国何以能胜：阶段论与主动灵活"),
    ("新民主主义论", "中国要建立一个什么样的国家"),
    ("论人民民主专政", "建国逻辑的收束：人民民主专政"),
]

LEARN_TIMELINE = [
    ("国民革命与农民", "1925–1927", "国共合作、北伐；党内忽视农民", "谁是朋友？农民运动怎么看？", ["中国社会各阶级的分析", "湖南农民运动考察报告"]),
    ("井冈山与长征前后", "1927–1936", "城市起义失败，农村割据与「围剿」", "红色政权为何能存在？怎么打中国战争？", ["井冈山的斗争", "星星之火，可以燎原", "反对本本主义", "中国革命战争的战略问题"]),
    ("认识论总括", "1937", "总结两次国内战争，准备抗战", "如何正确认识世界、分析矛盾？", ["实践论", "矛盾论"]),
    ("抗战战略", "1937–1941", "弱国对强国；国共再合作又摩擦", "速胜/亡国论；游击与持久", ["论持久战", "抗日游击战争的战略问题", "战争和战略问题"]),
    ("新民主主义与整风", "1940–1945", "相持阶段；教条与主观主义", "国体方案；党风学风文风", ["新民主主义论", "改造我们的学习", "整顿党的作风", "反对党八股", "论联合政府"]),
    ("解放战争", "1945–1949", "抗战结束转内战；由弱转强", "敢不敢打、如何打、政权性质", ["抗日战争胜利后的时局和我们的方针", "目前形势和我们的任务", "论人民民主专政", "党委会的工作方法"]),
    ("建国初期", "1949–1957", "政权建立、改造与建设", "十大关系；人民内部矛盾", ["论十大关系", "关于正确处理人民内部矛盾的问题"]),
]

LEARN_THEMES = [
    ("rural", "农村包围城市", "中国道路：根据地如何站住", ["中国的红色政权为什么能够存在？", "井冈山的斗争", "星星之火，可以燎原"]),
    ("military", "军事战略", "以弱胜强：战略与战役", ["中国革命战争的战略问题", "论持久战", "抗日游击战争的战略问题", "战争和战略问题"]),
    ("united", "统一战线", "联合与独立如何并存", ["新民主主义论", "论联合政府", "抗日战争胜利后的时局和我们的方针"]),
    ("party", "党建整风", "把党建成能执行路线的组织", ["改造我们的学习", "整顿党的作风", "反对党八股", "为人民服务", "愚公移山"]),
    ("mass", "群众与作风", "怎样做事、怎样联系群众", ["关心群众生活，注意工作方法", "纪念白求恩", "党委会的工作方法"]),
    ("build", "建设与矛盾", "执政后的关系与矛盾处理", ["论十大关系", "关于正确处理人民内部矛盾的问题"]),
]


def resolve_article(articles: list[Article], title_key: str) -> Article | None:
    for a in articles:
        if title_key in a.title or a.title in title_key:
            return a
    return None


def art_link(articles: list[Article], title_key: str, note: str = "") -> str:
    a = resolve_article(articles, title_key)
    if not a:
        return f'<span class="missing">{html.escape(title_key)}</span>'
    note_html = f'<span class="hint">{html.escape(note)}</span>' if note else ""
    date = f'<span class="d">{html.escape(a.date)}</span>' if a.date else ""
    return (
        f'<a class="learn-art" href="#{html.escape(a.id)}" data-id="{html.escape(a.id)}">'
        f'<strong>{html.escape(a.title)}</strong>{date}{note_html}</a>'
    )


def build_learn_pages(articles: list[Article], catalog: dict) -> tuple[str, str]:
    """Return (sidebar_html, pages_html) for structured learning."""
    nav = [
        '<div class="learn-nav">',
        '<div class="side-label">结构化学习</div>',
        '<a class="learn-nav-a" href="#learn-overview" data-learn="learn-overview">总览：怎么学</a>',
        '<a class="learn-nav-a" href="#learn-thread" data-learn="learn-thread">总脉络：四句方法</a>',
        '<a class="learn-nav-a" href="#learn-timeline" data-learn="learn-timeline">时间线：局面与方针</a>',
        '<a class="learn-nav-a" href="#learn-l1" data-learn="learn-l1">第一层：坐标系（必读）</a>',
        '<a class="learn-nav-a" href="#learn-l2" data-learn="learn-l2">第二层：专题线</a>',
    ]
    for tid, title, _, _ in LEARN_THEMES:
        nav.append(
            f'<a class="learn-nav-a sub" href="#learn-theme-{html.escape(tid)}" '
            f'data-learn="learn-theme-{html.escape(tid)}">{html.escape(title)}</a>'
        )
    nav += [
        '<a class="learn-nav-a" href="#learn-l3" data-learn="learn-l3">第三层：按卷索引</a>',
        '<a class="learn-nav-a" href="#learn-discipline" data-learn="learn-discipline">阅读纪律</a>',
        '<div class="side-label" style="margin-top:18px">分卷目录</div>',
        "</div>",
    ]

    # —— pages ——
    pages: list[str] = []

    # overview
    pages.append(
        f"""<section class="learn-page" id="learn-overview">
<header><div class="crumb">结构化学习</div><h1>怎么学毛选</h1></header>
<div class="learn-body">
<p class="lead">毛选不是散文集，而是<strong>党在不同危局里怎么看局面、定方针</strong>的实录。建议按「局面 → 问题 → 方法」分层学，不要按页从头硬啃。</p>
<div class="learn-cards">
  <a class="learn-card" href="#learn-thread" data-learn="learn-thread"><span class="n">01</span><strong>总脉络</strong><span>四句方法压成操作系统</span></a>
  <a class="learn-card" href="#learn-timeline" data-learn="learn-timeline"><span class="n">02</span><strong>时间线</strong><span>局面与方针对照表</span></a>
  <a class="learn-card" href="#learn-l1" data-learn="learn-l1"><span class="n">03</span><strong>第一层</strong><span>8 篇建坐标系（必读）</span></a>
  <a class="learn-card" href="#learn-l2" data-learn="learn-l2"><span class="n">04</span><strong>第二层</strong><span>六条专题线加深</span></a>
  <a class="learn-card" href="#learn-l3" data-learn="learn-l3"><span class="n">05</span><strong>第三层</strong><span>七卷当编年索引</span></a>
  <a class="learn-card" href="#learn-discipline" data-learn="learn-discipline"><span class="n">06</span><strong>纪律</strong><span>怎么读才不空转</span></a>
</div>
<div class="callout">官方一至五卷为主；第六、七卷为非官方静火整理，入门不做主线。读每篇只记三栏：<strong>局面 / 判断 / 办法</strong>。</div>
</div></section>"""
    )

    # thread
    pages.append(
        """<section class="learn-page" id="learn-thread">
<header><div class="crumb">结构化学习 · 总脉络</div><h1>贯穿始终的四句方法</h1></header>
<div class="learn-body">
<ol class="method-list">
  <li><strong>分清敌我友</strong><span>谁是依靠、谁是联合、谁是打击</span></li>
  <li><strong>从实际出发</strong><span>反对本本；调查；实践检验</span></li>
  <li><strong>抓主要矛盾</strong><span>不同阶段换主要矛盾，策略跟着换</span></li>
  <li><strong>组织起来落地</strong><span>群众、根据地、统一战线、党的作风</span></li>
</ol>
<pre class="mindmap">敌我友分析
    ↓
农村根据地 + 武装斗争 + 统一战线
    ↓
用《实践论》《矛盾论》校准认识与策略
    ↓
抗战：持久战 / 游击战 / 新民主主义
    ↓
整风：把党建成能执行路线的组织
    ↓
解放战争胜利 → 人民民主专政
    ↓
执政：十大关系、人民内部矛盾</pre>
<p>读任何一篇，先问三句：当时<strong>主要矛盾</strong>是什么？他要<strong>团结谁、打击谁</strong>？用什么<strong>组织形式</strong>落地？</p>
<p><a class="learn-nav-a inline" href="#learn-l1" data-learn="learn-l1">下一步：第一层坐标系 →</a></p>
</div></section>"""
    )

    # timeline
    rows = []
    for stage, years, situ, q, titles in LEARN_TIMELINE:
        links = "".join(art_link(articles, t) for t in titles)
        rows.append(
            f"<tr><td><strong>{html.escape(stage)}</strong><div class='y'>{html.escape(years)}</div></td>"
            f"<td>{html.escape(situ)}</td><td>{html.escape(q)}</td>"
            f"<td class='arts'>{links}</td></tr>"
        )
    pages.append(
        f"""<section class="learn-page" id="learn-timeline">
<header><div class="crumb">结构化学习 · 时间线</div><h1>局面与方针对照</h1></header>
<div class="learn-body">
<p class="lead">先看「党与作者当时卡在什么局里」，再点进对应篇目。方法可迁移，结论要回历史。</p>
<div class="table-wrap"><table class="learn-table">
<thead><tr><th>阶段</th><th>所处局面</th><th>核心问题</th><th>读什么</th></tr></thead>
<tbody>{''.join(rows)}</tbody>
</table></div>
</div></section>"""
    )

    # layer 1
    items = []
    for i, (title, note) in enumerate(LEARN_READING, 1):
        items.append(
            f'<li><span class="step">{i:02d}</span>{art_link(articles, title, note)}</li>'
        )
    pages.append(
        f"""<section class="learn-page" id="learn-l1">
<header><div class="crumb">结构化学习 · 第一层</div><h1>坐标系：8 篇必读</h1></header>
<div class="learn-body">
<p class="lead">按此顺序读完，再进战争与政策细节。每篇只追一个问题，笔记三栏：局面 / 判断 / 办法。</p>
<ol class="reading-list">{''.join(items)}</ol>
<div class="callout">读完这 8 篇，你已经有「敌我友—实践—矛盾—战争—建国」的操作系统。接着用第二层专题线加深。</div>
<p><a href="#learn-l2" data-learn="learn-l2">进入第二层专题线 →</a></p>
</div></section>"""
    )

    # layer 2 index
    theme_cards = []
    for tid, title, blurb, _ in LEARN_THEMES:
        theme_cards.append(
            f'<a class="learn-card" href="#learn-theme-{html.escape(tid)}" data-learn="learn-theme-{html.escape(tid)}">'
            f"<strong>{html.escape(title)}</strong><span>{html.escape(blurb)}</span></a>"
        )
    pages.append(
        f"""<section class="learn-page" id="learn-l2">
<header><div class="crumb">结构化学习 · 第二层</div><h1>六条专题线</h1></header>
<div class="learn-body">
<p class="lead">比按卷通读更有效：同一专题内按时间读，看方针如何随局面改口。</p>
<div class="learn-cards">{''.join(theme_cards)}</div>
</div></section>"""
    )

    for tid, title, blurb, titles in LEARN_THEMES:
        lis = "".join(
            f"<li>{art_link(articles, t)}</li>" for t in titles
        )
        pages.append(
            f"""<section class="learn-page" id="learn-theme-{html.escape(tid)}">
<header><div class="crumb">第二层 · 专题线</div><h1>{html.escape(title)}</h1></header>
<div class="learn-body">
<p class="lead">{html.escape(blurb)}</p>
<ol class="reading-list">{lis}</ol>
<p><a href="#learn-l2" data-learn="learn-l2">← 返回专题总览</a></p>
</div></section>"""
        )

    # layer 3 volumes
    vol_blocks = []
    guides = {
        "001": "找道路：农村、战争、哲学（坐标系多在此卷）",
        "002": "抗战战略上半：游击、持久、新民主主义",
        "003": "抗战下半：整风、文艺、联合政府",
        "004": "胜利前夜：军事—政治收束与建国逻辑",
        "005": "执政初期：建设关系与人民内部矛盾",
        "006": "非官方静火整理——补充史料，不作入门主线",
        "007": "非官方静火整理——补充史料，不作入门主线",
    }
    landmark_keys: list[str] = []
    for key, _ in LEARN_READING:
        landmark_keys.append(key)
    for _, _, _, titles in LEARN_THEMES:
        landmark_keys.extend(titles)
    for v in catalog["volumes"]:
        tip = guides.get(v["no"], "")
        vol_titles = {a["title"] for a in v["articles"]}
        seen_keys: set[str] = set()
        uniq_links: list[str] = []
        for key in landmark_keys:
            if key in seen_keys:
                continue
            hit = next((t for t in vol_titles if key in t or t in key), None)
            if not hit:
                continue
            seen_keys.add(key)
            uniq_links.append(art_link(articles, key))
        vol_blocks.append(
            f"<div class='vol-guide'><h3>{html.escape(v['short'])} · {html.escape(v['period'])}"
            f"<small>{html.escape(v['kind'])} · {v['count']} 篇</small></h3>"
            f"<p>{html.escape(tip)}</p>"
            f"<div class='arts'>{''.join(uniq_links[:8]) or '<span class=\"hint\">见左侧分卷目录浏览全文</span>'}</div>"
            f"<button type='button' class='open-vol' data-vol='{html.escape(v['no'])}'>在左侧打开本卷目录</button></div>"
        )
    pages.append(
        f"""<section class="learn-page" id="learn-l3">
<header><div class="crumb">结构化学习 · 第三层</div><h1>七卷当编年索引</h1></header>
<div class="learn-body">
<p class="lead">坐标系与专题读完后，用卷册按年代补全上下文。点击可跳到代表篇；或打开左侧该卷目录。</p>
{''.join(vol_blocks)}
</div></section>"""
    )

    pages.append(
        """<section class="learn-page" id="learn-discipline">
<header><div class="crumb">结构化学习</div><h1>阅读纪律</h1></header>
<div class="learn-body">
<ul class="discipline">
  <li><strong>先局面后观点</strong>——不知道 1927 / 1937 / 1945 差在哪，句子会读成空话。</li>
  <li><strong>一篇一个问题</strong>——例如只追问「持久战何以成立」，不要一篇里贪多。</li>
  <li><strong>方法可迁移，结论要回历史</strong>——把「抓主要矛盾、调查、统一战线」当思维工具；具体敌我划分属于当时条件。</li>
  <li><strong>官方五卷为主</strong>——入门与引用以前五卷为准；六、七卷慎读、对照。</li>
  <li><strong>用注释</strong>——正文脚注可跳到文末；专名与事件多在注释里。</li>
</ul>
<div class="callout">建议起步：先完成「第一层 8 篇」，再选一条你最关心的专题线深挖。</div>
<p><a href="#learn-l1" data-learn="learn-l1">从第一层开始 →</a></p>
</div></section>"""
    )

    return "\n".join(nav), "\n".join(pages)


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
/* structured learning */
.side-label{margin:4px 12px 8px;font:700 11px/1 var(--sans);letter-spacing:.12em;color:#777;text-transform:uppercase}
.learn-nav-a{display:block;padding:7px 12px;margin:0 4px;border-radius:8px;color:#ddd;font:13px/1.35 var(--sans)}
.learn-nav-a.sub{padding-left:22px;font-size:12.5px;color:#bbb}
.learn-nav-a:hover,.learn-nav-a.active{background:rgba(245,197,66,.1);color:#ffe08a;text-decoration:none}
.learn-page{display:none}
.learn-page.on{display:block;animation:fade .25s ease}
.learn-page header{margin-bottom:18px;padding-bottom:14px;border-bottom:1px solid var(--line)}
.learn-page h1{margin:0;font:700 28px/1.3 var(--sans);color:#fff}
.learn-body{font:15px/1.75 var(--sans);color:#e8e8e8}
.learn-body .lead{color:#bdbdbd;font-size:15px;max-width:62ch;margin:0 0 1.2em}
.learn-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px;margin:18px 0}
.learn-card{display:flex;flex-direction:column;gap:6px;padding:16px;border:1px solid #2e2e2e;border-radius:14px;background:#121212;color:#eee;text-decoration:none}
.learn-card:hover{border-color:#f5c542;background:#181818;text-decoration:none;color:#fff}
.learn-card .n{font:700 12px var(--sans);color:#f5c542}
.learn-card strong{font:700 16px/1.3 var(--sans)}
.learn-card span{color:#999;font-size:13px}
.callout{margin:18px 0;padding:14px 16px;border-left:3px solid #f5c542;background:rgba(245,197,66,.06);color:#d6d6d6;border-radius:0 10px 10px 0}
.method-list{margin:0;padding:0;list-style:none;counter-reset:m}
.method-list li{counter-increment:m;margin:0 0 12px;padding:14px 16px 14px 56px;position:relative;border:1px solid #2a2a2a;border-radius:12px;background:#121212}
.method-list li::before{content:counter(m, decimal-leading-zero);position:absolute;left:14px;top:14px;font:700 14px var(--sans);color:#f5c542}
.method-list strong{display:block;font-size:16px;margin-bottom:4px}
.method-list span{color:#aaa;font-size:13.5px}
.mindmap{margin:18px 0;padding:16px 18px;background:#0f0f0f;border:1px solid #2a2a2a;border-radius:12px;color:#d0d0d0;font:13px/1.6 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;overflow:auto;white-space:pre}
.reading-list{margin:0;padding:0;list-style:none}
.reading-list li{display:flex;gap:12px;align-items:flex-start;margin:0 0 10px;padding:12px 14px;border:1px solid #2a2a2a;border-radius:12px;background:#121212}
.reading-list .step{flex:0 0 auto;font:700 13px var(--sans);color:#f5c542;padding-top:2px}
a.learn-art{display:block;color:#eee;text-decoration:none;flex:1}
a.learn-art:hover{color:#ffe08a;text-decoration:none}
a.learn-art .d{display:inline;margin-left:8px;color:#888;font-size:12px}
a.learn-art .hint{display:block;margin-top:4px;color:#aaa;font-size:13px;font-weight:400}
.table-wrap{overflow:auto;border:1px solid #2a2a2a;border-radius:12px}
.learn-table{width:100%;border-collapse:collapse;font:13.5px/1.5 var(--sans);min-width:720px}
.learn-table th,.learn-table td{padding:12px 14px;border-bottom:1px solid #2a2a2a;vertical-align:top;text-align:left}
.learn-table th{background:#151515;color:#f5c542;font-weight:700;position:sticky;top:0}
.learn-table tr:hover td{background:#141414}
.learn-table .y{color:#888;font-size:12px;margin-top:4px}
.learn-table .arts a.learn-art{margin:0 0 8px;padding:0;border:0;background:transparent}
.vol-guide{margin:0 0 16px;padding:16px 18px;border:1px solid #2a2a2a;border-radius:14px;background:#121212}
.vol-guide h3{margin:0 0 8px;font:700 17px var(--sans);color:#fff}
.vol-guide h3 small{display:block;margin-top:4px;font:12px var(--sans);color:#888;font-weight:500}
.vol-guide .arts{display:flex;flex-direction:column;gap:8px;margin:10px 0}
.open-vol{margin-top:8px;border:1px solid #3a3a3a;background:#1a1a1a;color:#eee;border-radius:8px;padding:8px 12px;font:12px var(--sans);cursor:pointer}
.open-vol:hover{border-color:#f5c542;color:#ffe08a}
.discipline{margin:0;padding-left:1.2em;color:#ddd}
.discipline li{margin:0 0 12px}
.missing{color:#888}
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
const learnEls = new Map([...document.querySelectorAll('.learn-page')].map(el => [el.id, el]));

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
    else if (!forceOpen) {/* keep others as-is */}
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
  (target || el).scrollIntoView({behavior:'smooth', block:'start'});
}

function showLearn(id){
  hideAllMain();
  const el = learnEls.get(id);
  if (!el){ showHome(); return; }
  el.classList.add('on');
  document.querySelectorAll('.learn-nav-a').forEach(a => a.classList.toggle('active', a.dataset.learn === id));
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
    vol.classList.toggle('open');
    document.querySelectorAll('.vol').forEach(v => v.classList.toggle('active', v === vol));
  });
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
    if (vol) vol.scrollIntoView({behavior:'smooth', block:'nearest'});
  });
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

    learn_nav, learn_pages = build_learn_pages(articles, catalog)

    side_parts = [learn_nav]
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
        articles_force = "<style>.article{display:block!important}.side,.search,#results,#home,.learn-page{display:none!important}.app{display:block}.main{padding:24px}</style>"

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>毛泽东选集 · 结构化学习与检索</title>
<meta name="description" content="毛泽东选集七卷：结构化学习路径、分卷目录、全文检索、注释跳转。官方五卷为主，第六、七卷为静火非官方整理。">
<style>{READER_CSS}</style>
{articles_force}
</head>
<body>
<div class="{mode_class}">
  <aside class="side">
    <div class="brand">
      <h1><a href="#" id="homeLink">毛泽东选集</a></h1>
      <p>七卷 · {catalog['article_count']} 篇<br>结构化学习 · 注释跳转 · 检索</p>
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
      <p>按「局面 → 问题 → 方法」分层学：先建坐标系，再走专题线，最后用七卷当编年索引。左侧「结构化学习」可聚焦；点篇名进入原文，脚注与注释可双向跳转。</p>
      <div class="toolbar">
        <a class="chip" href="#learn-overview" data-learn="learn-overview">开始结构化学习</a>
        <a class="chip" href="#learn-l1" data-learn="learn-l1">第一层：8 篇必读</a>
        <a class="chip" href="#learn-timeline" data-learn="learn-timeline">局面时间线</a>
        <span class="chip">{catalog['article_count']} 篇 · 7 卷</span>
      </div>
      <p style="margin-top:14px">第六、七卷为非官方版本，可能有错误或误导，请注意鉴别。标题前序号仅为排序方便，不存在于原文。</p>
    </section>
    <div id="results" class="results"></div>
    {learn_pages}
    {''.join(article_parts)}
    <footer class="foot">
      正文整理来自 <a href="https://github.com/NpTIme/MaoZeDongAnthology" target="_blank" rel="noopener">NpTIme/MaoZeDongAnthology</a>。
      本页含结构化学习路径（章节 / 检索 / 注释跳转），生成自仓库构建脚本，不改变原文表述。
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
