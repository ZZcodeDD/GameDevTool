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
        '<div class="nav-fold open" data-fold="themes">',
        '<button type="button" class="nav-fold-btn" aria-expanded="true"><span>第二层：专题线</span><i class="chev"></i></button>',
        '<div class="nav-fold-body">',
        '<a class="learn-nav-a sub" href="#learn-l2" data-learn="learn-l2">专题总览</a>',
    ]
    for tid, title, _, _ in LEARN_THEMES:
        nav.append(
            f'<a class="learn-nav-a sub" href="#learn-theme-{html.escape(tid)}" '
            f'data-learn="learn-theme-{html.escape(tid)}">{html.escape(title)}</a>'
        )
    nav += [
        "</div></div>",
        '<a class="learn-nav-a" href="#learn-l3" data-learn="learn-l3">第三层：按卷索引</a>',
        '<a class="learn-nav-a" href="#learn-discipline" data-learn="learn-discipline">阅读纪律</a>',
        '<div class="side-label dim">分卷目录 <button type="button" class="linkish" id="collapseAllVols">全部折叠</button></div>',
        "</div>",
    ]

    # —— pages ——
    pages: list[str] = []

    # overview
    pages.append(
        f"""<section class="learn-page" id="learn-overview">
<header><div class="crumb">结构化学习</div><h1>怎么学毛选</h1>
<p class="subhead">局面 → 问题 → 方法 · 分层聚焦，不要通篇硬啃</p></header>
<div class="learn-body">
<p class="lead">毛选不是散文集，而是<strong class="hi">党在不同危局里怎么看局面、定方针</strong>的实录。</p>
<div class="logic-flow tier-a" aria-label="学习路径逻辑图">
  <div class="lf-node primary">总脉络<br><small>四句方法</small></div>
  <div class="lf-arrow"></div>
  <div class="lf-node">时间线<br><small>局面对照</small></div>
  <div class="lf-arrow"></div>
  <div class="lf-node accent">第一层<br><small>8 篇坐标系</small></div>
  <div class="lf-arrow"></div>
  <div class="lf-node">第二层<br><small>六条专题</small></div>
  <div class="lf-arrow"></div>
  <div class="lf-node muted">第三层<br><small>七卷索引</small></div>
</div>
<div class="learn-cards">
  <a class="learn-card c1" href="#learn-thread" data-learn="learn-thread"><span class="n">01</span><strong>总脉络</strong><span>四句方法压成操作系统</span></a>
  <a class="learn-card c2" href="#learn-timeline" data-learn="learn-timeline"><span class="n">02</span><strong>时间线</strong><span>局面与方针对照</span></a>
  <a class="learn-card c3" href="#learn-l1" data-learn="learn-l1"><span class="n">03</span><strong>第一层</strong><span>8 篇建坐标系（必读）</span></a>
  <a class="learn-card c2" href="#learn-l2" data-learn="learn-l2"><span class="n">04</span><strong>第二层</strong><span>六条专题线加深</span></a>
  <a class="learn-card c4" href="#learn-l3" data-learn="learn-l3"><span class="n">05</span><strong>第三层</strong><span>七卷当编年索引</span></a>
  <a class="learn-card c4" href="#learn-discipline" data-learn="learn-discipline"><span class="n">06</span><strong>纪律</strong><span>怎么读才不空转</span></a>
</div>
<div class="callout">官方一至五卷为主；第六、七卷为非官方静火整理，入门不做主线。读每篇只记三栏：<strong>局面 / 判断 / 办法</strong>。</div>
</div></section>"""
    )

    # thread
    pages.append(
        """<section class="learn-page" id="learn-thread">
<header><div class="crumb">结构化学习 · 总脉络</div><h1>贯穿始终的四句方法</h1>
<p class="subhead">先装操作系统，再读具体战争与政策</p></header>
<div class="learn-body">
<ol class="method-list">
  <li class="m1"><strong>分清敌我友</strong><span>谁是依靠、谁是联合、谁是打击</span></li>
  <li class="m2"><strong>从实际出发</strong><span>反对本本；调查；实践检验</span></li>
  <li class="m3"><strong>抓主要矛盾</strong><span>不同阶段换主要矛盾，策略跟着换</span></li>
  <li class="m4"><strong>组织起来落地</strong><span>群众、根据地、统一战线、党的作风</span></li>
</ol>
<div class="diagram-panel tier-b">
  <div class="diagram-title">历史推进逻辑</div>
  <div class="flow-col">
    <div class="flow-step s1"><b>敌我友</b><span>认清依靠与打击</span></div>
    <div class="flow-join"></div>
    <div class="flow-step s2"><b>三结合</b><span>根据地 · 武装 · 统一战线</span></div>
    <div class="flow-join"></div>
    <div class="flow-step s3"><b>认识论</b><span>实践论 · 矛盾论校准</span></div>
    <div class="flow-join"></div>
    <div class="flow-row">
      <div class="flow-step s2"><b>抗战</b><span>持久 / 游击 / 新民主主义</span></div>
      <div class="flow-step s3"><b>整风</b><span>学风党风文风</span></div>
    </div>
    <div class="flow-join"></div>
    <div class="flow-step s1"><b>建国</b><span>人民民主专政</span></div>
    <div class="flow-join"></div>
    <div class="flow-step s4"><b>执政</b><span>十大关系 · 人民内部矛盾</span></div>
  </div>
</div>
<div class="diagram-panel tier-c">
  <div class="diagram-title">读一篇时的三问（思维导图）</div>
  <div class="mind-map">
    <div class="mm-center">这一篇</div>
    <div class="mm-branch b1"><span class="mm-label">局面</span><span class="mm-text">主要矛盾是什么？</span></div>
    <div class="mm-branch b2"><span class="mm-label">敌我</span><span class="mm-text">团结谁、打击谁？</span></div>
    <div class="mm-branch b3"><span class="mm-label">落地</span><span class="mm-text">用什么组织与方法？</span></div>
  </div>
</div>
<p class="next-link"><a href="#learn-l1" data-learn="learn-l1">下一步：第一层坐标系 →</a></p>
</div></section>"""
    )

    # timeline as visual rail + foldable table
    rail = []
    for i, (stage, years, situ, q, titles) in enumerate(LEARN_TIMELINE, 1):
        links = "".join(art_link(articles, t) for t in titles)
        rail.append(
            f'<div class="tl-item"><div class="tl-dot"></div>'
            f'<div class="tl-card"><div class="tl-meta"><span class="tl-no">{i:02d}</span>'
            f'<span class="tl-years">{html.escape(years)}</span></div>'
            f'<h3>{html.escape(stage)}</h3>'
            f'<p class="tl-situ">{html.escape(situ)}</p>'
            f'<p class="tl-q"><span>核心问题</span>{html.escape(q)}</p>'
            f'<div class="tl-arts">{links}</div></div></div>'
        )
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
<header><div class="crumb">结构化学习 · 时间线</div><h1>局面与方针对照</h1>
<p class="subhead">先看卡在什么局里，再点进对应篇目</p></header>
<div class="learn-body">
<p class="lead">方法可迁移，结论要回历史。下方时间轴可直接跳原文。</p>
<div class="timeline tier-b">{''.join(rail)}</div>
<details class="fold-block">
  <summary>展开对照表（便于扫描）</summary>
  <div class="table-wrap"><table class="learn-table">
  <thead><tr><th>阶段</th><th>所处局面</th><th>核心问题</th><th>读什么</th></tr></thead>
  <tbody>{''.join(rows)}</tbody>
  </table></div>
</details>
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


ASSETS = Path(__file__).resolve().parent
READER_CSS = (ASSETS / "reader.css").read_text(encoding="utf-8")
READER_JS = (ASSETS / "reader.js").read_text(encoding="utf-8")


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
        intro_block = ""
        if a.intro:
            intro_block = (
                f'<details class="intro-fold" open><summary>题解 / 背景说明</summary>'
                f'<div class="intro">{md_inline(a.intro)}</div></details>'
            )
        toc = ""
        if a.subsections:
            toc_links = "".join(
                f'<a href="#{html.escape(a.id)}-h-{html.escape(slugify(s))}">{html.escape(s)}</a>'
                for s in a.subsections[:24]
            )
            toc = f'<nav class="article-toc"><div class="toc-label">本文目录</div>{toc_links}</nav>'
        notes = ""
        if a.notes_html:
            notes = (
                f'<details class="notes-fold" open><summary>注释 · {a.note_count} 条</summary>'
                f'<section class="notes-wrap">{a.notes_html}</section></details>'
            )
        bar = (
            f'<div class="reading-bar">'
            f'<button type="button" data-back-learn="learn-overview">← 学习路径</button>'
            f'<button type="button" data-back-learn="learn-l1">坐标系</button>'
            f'<span class="bar-title">{html.escape(a.title)}</span>'
            f'{"<button type=button data-scroll-notes>跳到注释</button>" if a.notes_html else ""}'
            f'</div>'
        )
        article_parts.append(
            f'<article class="article" id="{html.escape(a.id)}" data-volume="{html.escape(a.volume_no)}">'
            f"{bar}"
            f'<header><div class="crumb">{html.escape(a.volume_title)}'
            f'{" · 非官方静火整理" if not a.official else ""}</div>'
            f'<h1>{html.escape(a.title)}</h1>'
            f'{f"<div class=date>（{html.escape(a.date)}）</div>" if a.date else ""}'
            f"</header>{intro_block}{toc}<div class='body'>{a.body_html}</div>{notes}</article>"
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
<button type="button" class="back-top" id="backTop" title="回到顶部">↑ 顶部</button>
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
