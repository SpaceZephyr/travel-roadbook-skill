#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_roadbook.py — 旅行路书网页构建器

用法:
    python3 build_roadbook.py roadbook.json [输出.html] [--fragment]

读取结构化路书 JSON，渲染成自包含的手机端 HTML：
开头（标题 + 目的地文化装饰）、七天一览、路线示意图（按真实经纬度）、
高德行程按钮、气温区间图、逐日行程（可生成长图分享）、每日门票条形图、
花费区间图、出发前清单、穿着、注意事项、资料来源。

--fragment  不输出 <!DOCTYPE>/<html>/<head>/<body> 外壳，
            用于发布到 claude.ai Artifact（平台会自动包一层）。

字段见 assets/roadbook.sample.json 与 references/roadbook-spec.md。
所有文本做 HTML 转义；文本里写 {{本地文字}} 会渲染成当地文字字体。
"""
import html
import json
import math
import os
import re
import sys

# ---------------------------------------------------------------- 文化装饰预设
# 新增国家：照 "thai" 的结构加一项，hero 是开头右侧的线描（只用描边），
# border 是一行重复纹样的 <pattern> 内容（22×12 单元，用 currentColor 填充）。
ORNAMENTS = {
    "thai": {
        "hero_viewbox": "0 0 160 112",
        # 泰式寺庙山墙：三层屋檐，檐角上翘，顶端是 chofa
        "hero": [
            "M54 50 L80 18 L106 50", "M80 18 C79 10 83 5 89 6",
            "M54 50 C49 50 46 47 45 42", "M106 50 C111 50 114 47 115 42",
            "M38 66 L60 43", "M122 66 L100 43",
            "M38 66 C33 66 30 63 29 58", "M122 66 C127 66 130 63 131 58",
            "M22 82 L44 59", "M138 82 L116 59",
            "M22 82 C17 82 14 79 13 74", "M138 82 C143 82 146 79 147 74",
            "M54 50 H106 M38 66 H122 M22 82 H138",
            "M40 82 V104 M62 82 V104 M98 82 V104 M120 82 V104 M28 104 H132",
        ],
        "hero_circles": [[80, 37, 4]],
        # 莲花苞
        "border": ('<path d="M11 11 C7 9 7 4 11 1 C15 4 15 9 11 11Z" fill="currentColor"/>'
                   '<circle cx="0" cy="9" r="1.2" fill="currentColor"/>'
                   '<circle cx="22" cy="9" r="1.2" fill="currentColor"/>'),
    },
    "none": {"hero": [], "hero_circles": [], "border": ""},
}

LOCAL_FONTS = {
    "th": ("Noto+Serif+Thai:wght@500;700", '"Noto Serif Thai","Thonburi","Leelawadee UI",serif'),
    "ja": ("Noto+Serif+JP:wght@500;700", '"Noto Serif JP","Hiragino Mincho ProN",serif'),
    "ko": ("Noto+Serif+KR:wght@500;700", '"Noto Serif KR","AppleMyungjo",serif'),
    "vi": ("Noto+Serif:wght@500;700", '"Noto Serif",serif'),
}


def esc(s):
    return html.escape(str(s if s is not None else ""), quote=True)


def rich(s, lang):
    """转义文本，并把 {{本地文字}} 包成当地文字字体。"""
    out = esc(s)
    return re.sub(r"\{\{(.+?)\}\}",
                  lambda m: '<span class="th" lang="%s">%s</span>' % (lang, m.group(1)), out)


def pct(v, lo, hi):
    return round((v - lo) / float(hi - lo) * 100, 3)


def nice_ticks(lo, hi, step):
    t = math.ceil(lo / step) * step
    out = []
    while t < hi:
        if t > lo:
            out.append(t)
        t += step
    return out


def fmt_num(n):
    return "{:,}".format(int(n)) if float(n).is_integer() else str(n)


# ---------------------------------------------------------------- 各模块
def render_hero(d, orn, lang):
    h1 = "".join('<span class="nw">%s</span>' % esc(x) for x in d.get("h1", [d.get("title", "旅行路书")]))
    roof = ""
    if orn.get("hero"):
        paths = "".join('<path d="%s"/>' % p for p in orn["hero"])
        circles = "".join('<circle cx="%s" cy="%s" r="%s"/>' % tuple(c) for c in orn.get("hero_circles", []))
        roof = '<svg class="roof" viewBox="%s" aria-hidden="true">%s%s</svg>' % (orn["hero_viewbox"], paths, circles)
    border = ""
    if orn.get("border"):
        border = ('<div class="lotus" aria-hidden="true"><svg preserveAspectRatio="none"><defs>'
                  '<pattern id="orn-p" width="22" height="12" patternUnits="userSpaceOnUse">%s</pattern></defs>'
                  '<rect width="100%%" height="12" fill="url(#orn-p)"/></svg></div>') % orn["border"]
    return ('<div class="hero"><div><div class="eyebrow">%s</div><h1>%s</h1></div>%s</div>\n'
            '<p class="lede">%s</p>\n%s') % (esc(d.get("eyebrow", "")), h1, roof, rich(d.get("lede", ""), lang), border)


def render_overview(days, regions):
    if not days:
        return ""
    legend = "".join('<span><i class="sw r-%s"></i>%s</span>' % (k, esc(r["name"])) for k, r in regions.items())
    legend += '<span><svg width="13" height="13"><use href="#i-plane"/></svg>坐飞机</span>'
    if any(x.get("night") for x in days):
        legend += '<span><svg width="13" height="13"><use href="#i-lantern"/></svg>有夜市</span>'
    cells = []
    for i, x in enumerate(days):
        prev_same = i > 0 and days[i - 1].get("region") == x.get("region")
        next_same = i < len(days) - 1 and days[i + 1].get("region") == x.get("region")
        rad = "%s %s %s %s" % ("0" if prev_same else "3px", "0" if next_same else "3px",
                               "0" if next_same else "3px", "0" if prev_same else "3px")
        marks = ""
        if x.get("flight"):
            marks += '<svg width="13" height="13" aria-label="坐飞机"><use href="#i-plane"/></svg>'
        if x.get("night"):
            marks += '<svg width="13" height="13" aria-label="有夜市"><use href="#i-lantern"/></svg>'
        cells.append(
            '<div class="cell r-%s" tabindex="0" data-tip="%s"><div class="wd">%s</div><div class="dt">%s</div>'
            '<div class="bar" style="border-radius:%s"></div><div class="marks">%s</div><div class="num">%s</div></div>'
            % (esc(x.get("region", "")), esc(x.get("tip", "")), esc(x.get("weekday", "")), esc(x.get("date", "")),
               rad, marks, esc(x.get("local_num", ""))))
    return ('<section id="overview" style="margin-top:26px"><div class="legend">%s</div>'
            '<div class="week" style="grid-template-columns:repeat(%d,minmax(0,1fr))">%s</div></section>'
            % (legend, len(days), "".join(cells)))


def render_route(route):
    """按经纬度等比投影（W=380），航线画成二次曲线。"""
    nodes = route.get("nodes", [])
    if len(nodes) < 2:
        return ""
    W, pad_l, pad_r, pad_t, pad_b = 380.0, 40.0, 50.0, 30.0, 50.0
    lons = [n["lon"] for n in nodes]
    lats = [n["lat"] for n in nodes]
    for ln in route.get("lines", []):
        lats.append(ln["lat"])
    lo_lon, hi_lon, lo_lat, hi_lat = min(lons), max(lons), min(lats), max(lats)
    k = (W - pad_l - pad_r) / max(hi_lon - lo_lon, 0.5)
    H = round(pad_t + pad_b + (hi_lat - lo_lat) * k, 1)
    H = max(H, 160.0)

    def xy(lon, lat):
        return round(pad_l + (lon - lo_lon) * k, 1), round(pad_t + (hi_lat - lat) * k, 1)

    idx = {n["id"]: n for n in nodes}
    parts = []
    # 经线网格：每 5°
    for lon in nice_ticks(lo_lon - 3, hi_lon + 3, 5):
        x, _ = xy(lon, lo_lat)
        if 20 < x < W - 40:
            parts.append('<line class="r-grid" x1="%s" y1="10" x2="%s" y2="%s"/>' % (x, x, H - 18))
            parts.append('<text class="r-small" x="%s" y="%s">%s°E</text>' % (x + 3, H - 4, lon))
    for ln in route.get("lines", []):
        _, y = xy(lo_lon, ln["lat"])
        parts.append('<line class="r-tropic" x1="0" y1="%s" x2="%s" y2="%s"/>' % (y, W, y))
        parts.append('<text class="r-small" x="4" y="%s">%s</text>' % (y - 6, esc(ln.get("label", ""))))
    for leg in route.get("legs", []):
        a, b = idx[leg["from"]], idx[leg["to"]]
        x1, y1 = xy(a["lon"], a["lat"])
        x2, y2 = xy(b["lon"], b["lat"])
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        dx, dy = x2 - x1, y2 - y1
        L = math.hypot(dx, dy) or 1
        bend = leg.get("bend", 0.18) * L
        cx, cy = round(mx - dy / L * bend, 1), round(my + dx / L * bend, 1)
        cls = "r-leg back" if leg.get("dashed") else "r-leg"
        parts.append('<path class="%s" d="M%s %s Q %s %s %s %s"/>' % (cls, x1, y1, cx, cy, x2, y2))
        if leg.get("label"):
            lx = (x1 + 2 * cx + x2) / 4 + leg.get("label_dx", 6)
            ly = (y1 + 2 * cy + y2) / 4 + leg.get("label_dy", 4)
            parts.append('<text class="r-date" x="%s" y="%s">%s</text>' % (round(lx, 1), round(ly, 1), esc(leg["label"])))
    for n in nodes:
        x, y = xy(n["lon"], n["lat"])
        fill = "var(--r-%s)" % n["region"] if n.get("region") else "var(--ink)"
        r = 7 if n.get("region") else 5
        parts.append('<circle class="r-dot" cx="%s" cy="%s" r="%s" style="fill:%s"/>' % (x, y, r, fill))
        tx = x + n.get("label_dx", 12)
        ty = y + n.get("label_dy", 5)
        anchor = ' text-anchor="end"' if n.get("label_dx", 12) < 0 else ""
        parts.append('<text class="r-name" x="%s" y="%s"%s>%s</text>' % (tx, ty, anchor, esc(n["name"])))
        if n.get("note"):
            parts.append('<text class="r-small" x="%s" y="%s"%s>%s</text>' % (tx, ty + 15, anchor, esc(n["note"])))
    return ('<figure class="route"><svg viewBox="0 0 %d %d" role="img" aria-label="%s">%s</svg>'
            '<figcaption>%s</figcaption></figure>'
            % (W, math.ceil(H), esc(route.get("aria", "路线示意图")), "".join(parts),
               esc(route.get("caption", "城市按真实经纬度摆放，航线是示意"))))


def render_amap(d):
    uri = d.get("amap_uri")
    if not uri:
        return ""
    return ('<div class="amap"><a class="btn" href="%s">在高德地图打开全程行程</a>'
            '<p>%s点了没反应（比如在微信里）就长按下面的链接复制，粘贴到手机浏览器打开：<code>%s</code></p></div>'
            % (esc(uri), esc(d.get("amap_note", "")), esc(uri)))


def _bar_label(start, end, text, cls="v"):
    """数值标签：放在条的右侧；条太长就放到条左侧或上方。"""
    if end <= 78:
        return '<span class="%s" style="left:calc(%s%% + 6px)">%s</span>' % (cls, end, text)
    if start >= 22:
        return '<span class="%s" style="right:calc(%s%% + 6px)">%s</span>' % (cls, round(100 - start, 3), text)
    return '<span class="%s" style="right:%s%%;top:-18px">%s</span>' % (cls, round(100 - end, 3), text)


def _ticks(ticks, lo, hi):
    return "".join('<i class="tick" style="left:%s%%"></i>' % pct(t, lo, hi) for t in ticks)


def _axis(ticks, lo, hi, fmt):
    return '<div class="axis">%s</div>' % "".join(
        '<span style="left:%s%%">%s</span>' % (pct(t, lo, hi), fmt(t)) for t in ticks)


def render_weather(w, lang):
    rows = w.get("rows", [])
    if not rows:
        return ""
    lo = math.floor((min(r["low"] for r in rows) - 4) / 2.0) * 2
    hi = math.ceil((max(r["high"] for r in rows) + 2) / 2.0) * 2
    ticks = nice_ticks(lo, hi, 5)
    body, aria = [], []
    for r in rows:
        s, e = pct(r["low"], lo, hi), pct(r["high"], lo, hi)
        body.append(
            '<div class="lab">%s<small>%s</small></div><div class="plot">%s'
            '<i class="mark r-%s" style="left:%s%%;width:%s%%"></i>'
            '<span class="v" style="right:calc(%s%% + 6px)">%s°</span>'
            '<span class="v" style="left:calc(%s%% + 6px)">%s°</span>'
            '<i class="hit" data-tip="%s"></i></div>'
            % (esc(r["name"]), esc(r.get("sub", "")), _ticks(ticks, lo, hi), esc(r.get("region", "")),
               s, round(e - s, 3), round(100 - s, 3), r["low"], e, r["high"],
               esc(r.get("tip", "%s：平均最低 %s°C，最高 %s°C" % (r["name"], r["low"], r["high"])))))
        aria.append("%s最低 %s 度最高 %s 度" % (r["name"], r["low"], r["high"]))
    return ('<section><div class="sh"><h2>天气</h2><span class="note">%s</span></div>'
            '<div class="hchart" role="img" aria-label="%s">%s%s</div><p class="fine">%s</p></section>'
            % (esc(w.get("note", "")), esc("，".join(aria)), "".join(body),
               _axis(ticks, lo, hi, lambda t: "%s°C" % t), rich(w.get("fine", ""), lang)))


def render_plan(p, regions, lang):
    out = []
    transits = {t["after_city"]: t for t in p.get("transits", [])}
    for i, c in enumerate(p.get("cities", [])):
        reg = regions.get(c["region"], {})
        days = []
        for dd in c.get("days", []):
            plan = "".join("<dt>%s</dt><dd>%s</dd>" % (esc(a), rich(b, lang)) for a, b in dd.get("plan", []))
            meta = ""
            if dd.get("meta"):
                items = []
                for m in dd["meta"]:
                    extra = ' <span class="cash">%s</span>' % esc(m[2]) if len(m) > 2 and m[2] else ""
                    items.append("<dt>%s</dt><dd>%s%s</dd>" % (esc(m[0]), rich(m[1], lang), extra))
                meta = '<dl class="meta">%s</dl>' % "".join(items)
            local = '<span class="th" lang="%s">%s</span>' % (lang, esc(dd["local_label"])) if dd.get("local_label") else ""
            days.append(
                '<article class="day"><div class="date"><div class="d">%s</div><div class="w">%s</div>%s</div>'
                '<div><h4>%s</h4><dl class="plan">%s</dl>%s</div></article>'
                % (esc(dd["date"]), esc(dd.get("weekday", "")), local, esc(dd["title"]), plan, meta))
        local_name = '<span class="th" lang="%s">%s</span>' % (lang, esc(reg["local"])) if reg.get("local") else ""
        out.append(
            '<div class="city r-%s"><div class="city-head"><h3>%s</h3>%s<span class="span">%s</span></div>'
            '<p class="city-intro">%s</p>%s</div>'
            % (esc(c["region"]), esc(reg.get("name", "")), local_name, esc(c.get("span", "")),
               rich(c.get("intro", ""), lang), "".join(days)))
        if i in transits:
            t = transits[i]
            out.append('<div class="transit"><div class="d">%s</div><div><b>%s</b>%s</div></div>'
                       % (esc(t["date"]), esc(t["title"]), rich(t.get("text", ""), lang)))
    share_btn = ""
    if p.get("share", True):
        share_btn = ('<span><button type="button" id="share-btn" class="share">生成长图</button>'
                     '<span id="share-status" class="share-status" role="status"></span></span>')
    return ('<section id="plan"><div class="sh"><h2>%s</h2>%s</div>%s</section>'
            % (esc(p.get("heading", "每天怎么走")), share_btn, "".join(out)))


def render_tickets(t, lang):
    rows = t.get("rows", [])
    if not rows:
        return ""
    hi = t.get("max") or max((r.get("value") or 0) for r in rows) or 1
    ticks = t.get("ticks") or [hi / 2.0]
    unit = t.get("unit", "")
    body = []
    for r in rows:
        v = r.get("value")
        inner = _ticks(ticks, 0, hi)
        if v:
            e = pct(v, 0, hi)
            inner += '<i class="mark r-%s" style="left:0;width:%s%%"></i>' % (esc(r.get("region", "")), e)
            inner += _bar_label(0, e, esc(r.get("text", fmt_num(v))))
            if r.get("tip"):
                inner += '<i class="hit" data-tip="%s"></i>' % esc(r["tip"])
        else:
            inner += '<span class="v" style="left:0">%s</span>' % esc(r.get("text", "0"))
        body.append('<div class="lab">%s</div><div class="plot">%s</div>' % (esc(r["label"]), inner))
    table = ""
    if t.get("table"):
        trs = "".join("<tr><td>%s</td><td>%s</td><td class=\"n\">%s</td></tr>" % tuple(esc(x) for x in row)
                      for row in t["table"])
        table = ('<details class="tbl"><summary>看明细表</summary><table class="rows"><thead><tr><th>日期</th>'
                 '<th>地方</th><th class="n">%s</th></tr></thead><tbody>%s</tbody></table></details>' % (esc(unit), trs))
    axis_ticks = [0] + list(ticks) + [hi]
    axis = '<div class="axis">%s</div>' % "".join(
        '<span style="left:%s%%;%s">%s</span>' % (
            pct(x, 0, hi),
            "transform:none" if x == 0 else ("transform:translateX(-100%)" if x == hi else ""),
            fmt_num(x) + (" " + esc(unit) if x == hi else ""))
        for x in axis_ticks)
    return ('<section><div class="sh"><h2>%s</h2><span class="note">%s</span></div>'
            '<div class="hchart" role="img" aria-label="%s">%s%s</div>'
            '<div class="total"><span>%s</span><b>%s</b></div>%s</section>'
            % (esc(t.get("heading", "每天门票花多少")), esc(t.get("note", "")), esc(t.get("aria", "每日门票")),
               "".join(body), axis, esc(t.get("total_label", "")), esc(t.get("total", "")), table))


def render_budget(b, lang):
    rows = b.get("rows", [])
    if not rows:
        return ""
    hi = b.get("max") or max(r.get("max", r.get("value", 0)) for r in rows)
    ticks = b.get("ticks") or nice_ticks(0, hi, hi / 2.5)
    pre = b.get("prefix", "")
    body = []
    for r in rows:
        inner = _ticks(ticks, 0, hi)
        if "min" in r:
            s, e = pct(r["min"], 0, hi), pct(r["max"], 0, hi)
            inner += '<i class="mark ink" style="left:%s%%;width:%s%%"></i>' % (s, round(e - s, 3))
            inner += _bar_label(s, e, esc(r.get("text", "%s–%s" % (fmt_num(r["min"]), fmt_num(r["max"])))))
        else:
            s = pct(r["value"], 0, hi)
            inner += '<i class="mark ink dot" style="left:%s%%"></i>' % s
            inner += '<span class="v" style="left:calc(%s%% + 10px)">%s</span>' % (s, esc(r.get("text", fmt_num(r["value"]))))
        if r.get("tip"):
            inner += '<i class="hit" data-tip="%s"></i>' % esc(r["tip"])
        sub = "<small>%s</small>" % esc(r["sub"]) if r.get("sub") else ""
        body.append('<div class="lab">%s%s</div><div class="plot">%s</div>' % (esc(r["label"]), sub, inner))
    axis_ticks = [0] + list(ticks)
    axis = '<div class="axis">%s</div>' % "".join(
        '<span style="left:%s%%;%s">%s</span>' % (pct(x, 0, hi), "transform:none" if x == 0 else "",
                                                  (esc(pre) if x == 0 else "") + fmt_num(x))
        for x in axis_ticks)
    return ('<section><div class="sh"><h2>%s</h2><span class="note">%s</span></div>'
            '<div class="hchart" role="img" aria-label="%s">%s%s</div>'
            '<div class="total"><span>%s</span><b>%s</b></div><p class="fine">%s</p></section>'
            % (esc(b.get("heading", "整趟每人大概花多少")), esc(b.get("note", "")), esc(b.get("aria", "花费区间")),
               "".join(body), axis, esc(b.get("total_label", "每人合计")), esc(b.get("total", "")),
               rich(b.get("fine", ""), lang)))


def render_todo(t, lang):
    items = t.get("items", [])
    if not items:
        return ""
    lis = []
    for i, it in enumerate(items):
        sub = "<small>%s</small>" % rich(it["sub"], lang) if it.get("sub") else ""
        lis.append('<li><label><input type="checkbox" id="todo-%d"><span class="by%s">%s</span>'
                   '<span class="what">%s%s</span></label></li>'
                   % (i, " now" if it.get("urgent") else "", esc(it.get("by", "")), rich(it["text"], lang), sub))
    return ('<section><div class="sh"><h2>%s</h2><span class="note">勾选只存在这台设备上</span></div>'
            '<ul class="todo" data-key="%s">%s</ul></section>'
            % (esc(t.get("heading", "出发前要办的事")), esc(t.get("key", "roadbook-todo")), "".join(lis)))


def render_list(heading, items, lang):
    if not items:
        return ""
    lis = []
    for it in items:
        if isinstance(it, dict):
            lis.append("<li><b>%s</b><span>%s</span></li>" % (esc(it.get("title", "")), rich(it.get("text", ""), lang)))
        else:
            lis.append("<li><span>%s</span></li>" % rich(it, lang))
    return '<section><div class="sh"><h2>%s</h2></div><ul class="plain">%s</ul></section>' % (esc(heading), "".join(lis))


def render_footer(d, lang):
    src = " · ".join('<a href="%s" target="_blank" rel="noopener">%s</a>' % (esc(s["url"]), esc(s["label"]))
                     for s in d.get("sources", []))
    bye = ""
    fw = d.get("theme", {}).get("farewell")
    if fw:
        bye = '<span class="bye"><span class="th" lang="%s">%s</span> · %s</span>' % (lang, esc(fw.get("local", "")), esc(fw.get("zh", "")))
    return '<footer>%s%s<br>%s%s</footer>' % (esc(d.get("sources_label", "资料来源：")), src,
                                             rich(d.get("footer_note", ""), lang), bye)


# ---------------------------------------------------------------- 样式与脚本
CSS = r"""
:root{
  --bg:#fbfaf6; --ink:#1b1d1c; --ink-2:#565a58; --ink-3:#8c908d; --line:#e7e5de; --track:#efede6;
  --btn:#1b1d1c; --btn-ink:#fbfaf6; --orn:%(orn_light)s;
%(region_light)s
  --serif:"Noto Serif SC","Songti SC","STSong",serif;
  --sans:"Noto Sans SC",-apple-system,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
  --local:%(local_stack)s;
  color-scheme:light;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --bg:#15171a; --ink:#e9e9e6; --ink-2:#b2b4b0; --ink-3:#80837f; --line:#2b2e31; --track:#23262a;
    --btn:#e9e9e6; --btn-ink:#15171a; --orn:%(orn_dark)s;
%(region_dark)s
    color-scheme:dark;
  }
}
:root[data-theme="dark"]{
  --bg:#15171a; --ink:#e9e9e6; --ink-2:#b2b4b0; --ink-3:#80837f; --line:#2b2e31; --track:#23262a;
  --btn:#e9e9e6; --btn-ink:#15171a; --orn:%(orn_dark)s;
%(region_dark)s
  color-scheme:dark;
}
%(region_classes)s
*{box-sizing:border-box;}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:15px;line-height:1.75;-webkit-font-smoothing:antialiased;font-variant-numeric:tabular-nums;}
.page{max-width:640px;margin:0 auto;padding-inline:20px;padding-block:36px 56px;}
h1,h2,h3,h4{margin:0;font-weight:700;text-wrap:balance;}
p{margin:0;}
a{color:inherit;}
:focus-visible{outline:2px solid var(--ink-2);outline-offset:3px;border-radius:4px;}
.th{font-family:var(--local);font-weight:500;}

.hero{display:grid;grid-template-columns:1fr auto;gap:12px;align-items:end;}
.eyebrow{font-size:13px;color:var(--ink-3);letter-spacing:.08em;}
h1{font-family:var(--serif);font-size:clamp(30px,7.5vw,40px);line-height:1.3;margin-top:8px;}
h1 .nw{white-space:nowrap;display:inline-block;}
.roof{width:clamp(92px,24vw,140px);height:auto;color:var(--orn);}
.roof path,.roof circle{fill:none;stroke:currentColor;stroke-width:1.6;stroke-linecap:round;stroke-linejoin:round;}
.lede{margin-top:14px;color:var(--ink-2);}
.lotus{height:12px;margin:26px 0 0;color:var(--orn);opacity:.75;}
.lotus svg{display:block;width:100%;height:12px;}

.legend{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:12.5px;color:var(--ink-2);margin-bottom:12px;}
.legend span{display:inline-flex;align-items:center;gap:6px;}
.sw{width:14px;height:6px;border-radius:3px;display:inline-block;background:var(--rc);}
.week{display:grid;gap:2px;}
.cell{text-align:center;padding:2px 0 6px;border-radius:6px;cursor:default;}
.cell:hover,.cell:focus-visible{background:var(--track);}
.cell .wd{font-size:11.5px;color:var(--ink-3);}
.cell .dt{font-family:var(--serif);font-weight:700;font-size:15px;line-height:1.3;}
.cell .bar{height:6px;margin:6px 0;background:var(--rc);}
.cell .marks{height:18px;display:flex;justify-content:center;gap:4px;color:var(--ink-2);align-items:center;}
.cell .num{font-family:var(--local);font-size:11px;color:var(--ink-3);min-height:1em;}

.route{margin:28px 0 0;}
.route svg{display:block;width:100%;height:auto;max-width:100%;}
.r-grid{stroke:var(--line);stroke-width:1;}
.r-tropic{stroke:var(--ink-3);stroke-width:1;stroke-dasharray:2 4;}
.r-leg{fill:none;stroke:var(--ink-2);stroke-width:1.5;}
.r-leg.back{stroke:var(--ink-3);stroke-dasharray:4 4;}
.r-dot{stroke:var(--bg);stroke-width:2;}
.r-name{fill:var(--ink);font-size:15px;font-weight:700;font-family:var(--sans);}
.r-small{fill:var(--ink-3);font-size:11px;font-family:var(--sans);}
.r-date{fill:var(--ink-2);font-size:11.5px;font-family:var(--sans);}
.route figcaption{font-size:12px;color:var(--ink-3);margin-top:6px;}

.amap{margin-top:22px;}
.btn{display:flex;align-items:center;justify-content:center;gap:8px;width:100%;text-decoration:none;background:var(--btn);color:var(--btn-ink);border-radius:10px;padding:14px 16px;font-size:16px;font-weight:500;}
.amap p{margin-top:10px;font-size:12.5px;color:var(--ink-3);}
.amap code{display:block;margin-top:6px;font-family:ui-monospace,Menlo,monospace;font-size:11px;color:var(--ink-2);word-break:break-all;user-select:all;-webkit-user-select:all;}

section{margin-top:56px;}
.sh{display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin-bottom:18px;}
.sh h2{font-family:var(--serif);font-size:24px;}
.sh .note{font-size:12.5px;color:var(--ink-3);text-align:right;}
.fine{font-size:12.5px;color:var(--ink-3);margin-top:14px;line-height:1.7;}

.hchart{display:grid;grid-template-columns:auto 1fr;column-gap:12px;row-gap:12px;align-items:center;}
.hchart .lab{font-size:13.5px;white-space:nowrap;}
.hchart .lab small{display:block;font-size:11.5px;color:var(--ink-3);line-height:1.3;}
.plot{position:relative;height:22px;}
.plot .tick{position:absolute;top:-4px;bottom:-4px;width:1px;background:var(--line);}
.plot .mark{position:absolute;top:8px;height:6px;border-radius:3px;background:var(--rc);}
.plot .mark.ink{background:var(--ink-2);}
.plot .mark.dot{width:10px;height:10px;top:6px;border-radius:50%;margin-left:-5px;}
.plot .v{position:absolute;top:0;font-size:12px;color:var(--ink-2);line-height:22px;white-space:nowrap;}
.plot .hit{position:absolute;inset:-6px 0;cursor:default;}
.axis{grid-column:2;position:relative;height:16px;font-size:11px;color:var(--ink-3);}
.axis span{position:absolute;transform:translateX(-50%);white-space:nowrap;}
details.tbl{margin-top:14px;font-size:13.5px;}
details.tbl summary{cursor:pointer;color:var(--ink-2);font-size:13px;}
.rows{width:100%;border-collapse:collapse;font-size:13.5px;margin-top:8px;}
.rows td,.rows th{padding:8px 0;border-bottom:1px solid var(--line);text-align:left;vertical-align:top;}
.rows th{font-size:12px;font-weight:400;color:var(--ink-3);}
.rows .n{text-align:right;white-space:nowrap;padding-left:12px;}
.total{display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin-top:18px;padding-top:12px;border-top:1px solid var(--line);}
.total b{font-family:var(--serif);font-size:22px;}
.total span{font-size:13px;color:var(--ink-2);}

.share{font:inherit;font-size:13.5px;color:var(--ink);background:none;border:1px solid var(--line);border-radius:999px;padding:5px 14px;cursor:pointer;white-space:nowrap;}
.share:hover{border-color:var(--ink-3);}
.share:disabled{opacity:.55;cursor:progress;}
.share-status{display:block;font-size:12px;color:var(--ink-3);text-align:right;}
.city{margin-top:40px;}
.sh + .city{margin-top:8px;}
.city-head{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;}
.city-head h3{font-family:var(--serif);font-size:30px;line-height:1.3;}
.city-head .th{font-size:20px;color:var(--rc);}
.city-head .span{font-size:13px;color:var(--ink-3);margin-left:auto;}
.city-intro{margin-top:6px;color:var(--ink-2);font-size:14px;}
.day{display:grid;grid-template-columns:68px 1fr;gap:4px;padding:22px 0;border-top:1px solid var(--line);}
.city-intro + .day{margin-top:18px;}
.date .d{font-family:var(--serif);font-size:24px;font-weight:700;line-height:1.2;color:var(--rc);}
.date .w{font-size:12.5px;color:var(--ink-3);}
.date .th{font-size:12px;color:var(--ink-3);display:block;margin-top:2px;}
.day h4{font-size:17px;line-height:1.5;margin-bottom:8px;}
.plan{display:grid;grid-template-columns:44px 1fr;column-gap:10px;row-gap:6px;margin:0;font-size:14.5px;}
.plan dt{color:var(--ink-3);font-size:13px;padding-top:1px;}
.plan dd{margin:0;}
.meta{display:grid;grid-template-columns:44px 1fr;column-gap:10px;row-gap:3px;margin:12px 0 0;font-size:13px;color:var(--ink-2);}
.meta dt{color:var(--ink-3);}
.meta dd{margin:0;}
.cash{font-size:12px;color:var(--ink);border-bottom:1px dotted var(--ink-3);white-space:nowrap;}
.transit{margin-top:6px;padding:18px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line);font-size:14px;color:var(--ink-2);display:grid;grid-template-columns:68px 1fr;gap:4px;}
.transit .d{font-family:var(--serif);font-weight:700;color:var(--ink);}
.transit b{color:var(--ink);font-weight:500;}

.todo{list-style:none;margin:0;padding:0;}
.todo li{border-top:1px solid var(--line);}
.todo li:last-child{border-bottom:1px solid var(--line);}
.todo label{display:grid;grid-template-columns:22px 60px 1fr;gap:10px;align-items:start;padding:12px 0;cursor:pointer;font-size:14.5px;}
.todo input{width:17px;height:17px;margin:4px 0 0;accent-color:var(--ink);}
.todo .by{font-size:12.5px;color:var(--ink-3);padding-top:2px;}
.todo .by.now{color:var(--ink);font-weight:700;}
.todo small{display:block;color:var(--ink-3);font-size:12.5px;}
.todo input:checked ~ .what{color:var(--ink-3);text-decoration:line-through;}
.plain{margin:0;padding:0;list-style:none;}
.plain li{padding:10px 0;border-top:1px solid var(--line);font-size:14.5px;}
.plain li:last-child{border-bottom:1px solid var(--line);}
.plain b{font-weight:500;display:block;}
.plain span{color:var(--ink-2);font-size:14px;}
footer{margin-top:56px;font-size:12px;color:var(--ink-3);line-height:1.9;}
footer a{color:var(--ink-2);}
footer .bye{display:block;margin-top:14px;font-size:15px;color:var(--orn);}

#tip{position:fixed;z-index:30;max-width:240px;padding:6px 10px;border-radius:8px;background:var(--ink);color:var(--bg);font-size:12.5px;line-height:1.5;pointer-events:none;box-shadow:0 4px 14px rgba(0,0,0,.18);}
.sheet{position:fixed;inset:0;z-index:40;background:rgba(15,17,16,.78);display:flex;flex-direction:column;align-items:center;padding:calc(16px + env(safe-area-inset-top,0px)) 16px calc(16px + env(safe-area-inset-bottom,0px));}
.sheet-bar{width:100%;max-width:520px;display:flex;align-items:center;justify-content:space-between;gap:10px;color:#fff;font-size:13.5px;margin-bottom:10px;}
.sheet-bar .acts{display:flex;gap:8px;flex:none;}
.sheet-bar button,.sheet-bar a{font:inherit;font-size:14px;border-radius:999px;padding:6px 14px;cursor:pointer;border:1px solid rgba(255,255,255,.5);background:transparent;color:#fff;text-decoration:none;}
.sheet-bar .primary{background:#fff;color:#1b1d1c;border-color:#fff;font-weight:500;}
.sheet-img{flex:1;min-height:0;width:100%;max-width:520px;overflow-y:auto;border-radius:8px;background:#fff;}
.sheet-img img{display:block;width:100%;height:auto;}
.shot{
  --bg:#fbfaf6; --ink:#1b1d1c; --ink-2:#565a58; --ink-3:#8c908d; --line:#e7e5de; --track:#efede6; --orn:%(orn_light)s;
%(region_light)s
  position:absolute;left:-99999px;top:0;width:720px;padding:44px 44px 36px;background:var(--bg);color:var(--ink);
}
.shot .s-head{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;margin-bottom:22px;}
.shot .s-title{font-family:var(--serif);font-size:36px;font-weight:700;line-height:1.3;margin-top:6px;}
.shot .plan dd,.shot .meta dd,.shot .day h4{padding-right:12px;}
.shot .s-foot{margin-top:26px;font-size:12.5px;color:var(--ink-3);}
@media (max-width:420px){
  .page{padding-inline:16px;}
  .day,.transit{grid-template-columns:56px 1fr;}
  .date .d{font-size:21px;}
  .cell .dt{font-size:13.5px;}
  .city-head .span{margin-left:0;width:100%;}
}
@media (prefers-reduced-motion:reduce){*{transition:none!important;}}
"""

ICONS = """<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs>
<symbol id="i-plane" viewBox="0 0 24 24"><path d="M21 16v-2l-8-5V3.5a1.5 1.5 0 0 0-3 0V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5z" fill="currentColor"/></symbol>
<symbol id="i-lantern" viewBox="0 0 24 24"><path d="M12 2v2M8 5h8M7 6c-2 3-2 9 0 12h10c2-3 2-9 0-12zM9 19v2h6v-2" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></symbol>
</defs></svg>"""

JS = r"""
/* 悬停或点按显示说明 */
(function(){
  var tip=document.getElementById("tip"),cur=null;
  function show(el,x,y){
    tip.textContent=el.getAttribute("data-tip");if(!tip.textContent)return;tip.hidden=false;
    var r=tip.getBoundingClientRect(),vw=document.documentElement.clientWidth;
    var left=Math.min(Math.max(8,x-r.width/2),vw-r.width-8),top=y-r.height-12;if(top<8)top=y+16;
    tip.style.left=left+"px";tip.style.top=top+"px";cur=el;
  }
  function hide(){tip.hidden=true;cur=null;}
  function find(t){return t&&t.closest?t.closest("[data-tip]"):null;}
  document.addEventListener("pointerover",function(e){var el=find(e.target);if(el&&e.pointerType==="mouse")show(el,e.clientX,e.clientY);});
  document.addEventListener("pointermove",function(e){if(cur&&e.pointerType==="mouse")show(cur,e.clientX,e.clientY);});
  document.addEventListener("pointerout",function(e){if(e.pointerType==="mouse"&&cur&&!cur.contains(e.relatedTarget))hide();});
  document.addEventListener("click",function(e){var el=find(e.target);if(el)show(el,e.clientX,e.clientY);else hide();});
  document.addEventListener("focusin",function(e){var el=find(e.target);if(el){var r=el.getBoundingClientRect();show(el,r.left+r.width/2,r.top);}});
  document.addEventListener("focusout",hide);
  window.addEventListener("scroll",hide,{passive:true});
})();

/* 出发前清单：勾选存本机 */
(function(){
  var ul=document.querySelector(".todo");if(!ul)return;
  var KEY=ul.getAttribute("data-key"),saved={};
  try{saved=JSON.parse(localStorage.getItem(KEY)||"{}")||{};}catch(e){saved={};}
  ul.querySelectorAll("input[type=checkbox]").forEach(function(b){
    if(saved[b.id])b.checked=true;
    b.addEventListener("change",function(){saved[b.id]=b.checked;try{localStorage.setItem(KEY,JSON.stringify(saved));}catch(e){}});
  });
})();

/* 生成长图：克隆一览 + 逐日行程，用 html2canvas 画成 PNG */
(function(){
  var btn=document.getElementById("share-btn");if(!btn)return;
  var status=document.getElementById("share-status");
  var CFG=window.ROADBOOK_SHARE||{};
  var FILE=CFG.filename||"旅行路书.png";
  var libPromise=null;
  function loadLib(){
    if(window.html2canvas)return Promise.resolve();
    if(libPromise)return libPromise;
    libPromise=new Promise(function(ok,fail){
      var s=document.createElement("script");
      s.src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js";
      s.onload=ok;s.onerror=function(){libPromise=null;fail(new Error("lib"));};
      document.head.appendChild(s);
    });
    return libPromise;
  }
  // 长图里的 SVG 用固定颜色，导出时 CSS 变量可能丢失
  function inlineIcon(kind){
    var d=kind==="plane"
      ?'<path d="M21 16v-2l-8-5V3.5a1.5 1.5 0 0 0-3 0V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5z" fill="#565a58"/>'
      :'<path d="M12 2v2M8 5h8M7 6c-2 3-2 9 0 12h10c2-3 2-9 0-12zM9 19v2h6v-2" fill="none" stroke="#565a58" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>';
    return '<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24">'+d+'</svg>';
  }
  function buildSheet(){
    var box=document.createElement("div");box.className="shot";
    var head=document.createElement("div");head.className="s-head";
    head.innerHTML='<div><div class="eyebrow"></div><div class="s-title"></div></div>';
    head.querySelector(".eyebrow").textContent=CFG.eyebrow||"";
    head.querySelector(".s-title").textContent=CFG.title||document.title;
    var roof=document.querySelector(".roof");
    if(roof){
      roof=roof.cloneNode(true);roof.setAttribute("xmlns","http://www.w3.org/2000/svg");
      roof.querySelectorAll("path,circle").forEach(function(p){p.setAttribute("stroke",CFG.ornament||"#b3862a");p.setAttribute("fill","none");p.setAttribute("stroke-width","1.6");});
      head.appendChild(roof);
    }
    box.appendChild(head);
    var ov=document.getElementById("overview");
    if(ov){
      ov=ov.cloneNode(true);ov.removeAttribute("id");ov.style.marginTop="0";
      ov.querySelectorAll("svg").forEach(function(s){
        var use=s.querySelector("use");if(!use)return;
        var span=document.createElement("span");span.innerHTML=inlineIcon(use.getAttribute("href")==="#i-plane"?"plane":"lantern");
        s.replaceWith(span.firstChild);
      });
      box.appendChild(ov);
    }
    document.querySelectorAll("#plan .city, #plan .transit").forEach(function(el){box.appendChild(el.cloneNode(true));});
    var foot=document.createElement("p");foot.className="s-foot";foot.textContent=CFG.footer||"";box.appendChild(foot);
    document.body.appendChild(box);
    return box;
  }
  function showSheet(blob,url){
    var sheet=document.createElement("div");sheet.className="sheet";
    sheet.setAttribute("role","dialog");sheet.setAttribute("aria-label","长图预览");
    sheet.innerHTML='<div class="sheet-bar"><span id="sheet-hint">手机上长按图片也能保存</span>'+
      '<span class="acts"><button type="button" class="primary" id="sheet-save" hidden>保存图片</button>'+
      '<a class="primary" id="sheet-dl" hidden>下载图片</a>'+
      '<button type="button" id="sheet-close">关闭</button></span></div>'+
      '<div class="sheet-img"><img alt="逐日行程长图"></div>';
    sheet.querySelector("img").src=url;
    document.body.appendChild(sheet);
    var hint=sheet.querySelector("#sheet-hint"),save=sheet.querySelector("#sheet-save"),close=sheet.querySelector("#sheet-close");
    function done(){URL.revokeObjectURL(url);sheet.remove();btn.focus();}
    close.addEventListener("click",done);
    sheet.addEventListener("keydown",function(e){if(e.key==="Escape")done();});
    close.focus();
    if(!(window.claude&&window.claude.use)){
      // 普通网页（如飞书发布）：直接给下载链接
      var a=sheet.querySelector("#sheet-dl");a.href=url;a.download=FILE;a.hidden=false;return;
    }
    // claude.ai Artifact：页面不能自己下载，要走 downloads 能力（发布时声明 {"downloads": true}）
    window.claude.use("downloads").then(function(dl){
      if(!dl)return;
      save.hidden=false;
      save.addEventListener("click",function(){
        save.disabled=true;
        dl.save({filename:FILE,data:blob}).then(function(r){
          hint.textContent=r&&r.status==="delivered"?"已交出去了":"已保存";
        }).catch(function(err){
          var c=err&&err.code;
          if(c==="declined")hint.textContent="没有保存，想要的话再点一次";
          else if(c==="rate_limited")hint.textContent="已有一个保存窗口开着，先处理它";
          else{hint.textContent="这里存不了文件，长按图片保存";save.hidden=true;}
        }).then(function(){save.disabled=false;});
      });
    }).catch(function(){});
  }
  btn.addEventListener("click",function(){
    btn.disabled=true;status.textContent="正在生成…";
    var box=null;
    loadLib().then(function(){return document.fonts&&document.fonts.ready?document.fonts.ready:null;})
    .then(function(){
      box=buildSheet();
      var w=box.offsetWidth,h=box.offsetHeight,scale=Math.min(2,Math.sqrt(16000000/(w*h)));
      return window.html2canvas(box,{scale:scale,backgroundColor:"#fbfaf6",useCORS:true,logging:false,windowWidth:w});
    }).then(function(canvas){
      return new Promise(function(ok,fail){canvas.toBlob(function(b){b?ok(b):fail(new Error("blob"));},"image/png");});
    }).then(function(blob){status.textContent="";showSheet(blob,URL.createObjectURL(blob));})
    .catch(function(e){status.textContent=e&&e.message==="lib"?"画图工具没加载上，检查网络后再试":"没生成出来，再试一次";})
    .then(function(){if(box)box.remove();btn.disabled=false;});
  });
})();
"""


def build(d, fragment=False):
    theme = d.get("theme", {})
    orn = ORNAMENTS.get(theme.get("ornament", "none"), ORNAMENTS["none"])
    lang = theme.get("local_lang", "th")
    font_q, local_stack = LOCAL_FONTS.get(lang, ("", "serif"))
    regions = d.get("regions", {})
    orn_color = theme.get("ornament_color", {"light": "#b3862a", "dark": "#b88d30"})

    region_light = "\n".join("  --r-%s:%s;" % (k, r["light"]) for k, r in regions.items())
    region_dark = "\n".join("    --r-%s:%s;" % (k, r.get("dark", r["light"])) for k, r in regions.items())
    region_classes = "\n".join(".r-%s{--rc:var(--r-%s);}" % (k, k) for k in regions)
    css = CSS
    for key, val in {
        "orn_light": orn_color["light"], "orn_dark": orn_color["dark"],
        "region_light": region_light, "region_dark": region_dark, "region_classes": region_classes,
        "local_stack": local_stack,
    }.items():
        css = css.replace("%%(%s)s" % key, val)
    fonts = "family=Noto+Serif+SC:wght@500;700&family=Noto+Sans+SC:wght@400;500;700"
    if font_q:
        fonts += "&family=" + font_q
    share_cfg = {
        "filename": d.get("share", {}).get("filename", (d.get("title") or "旅行路书") + ".png"),
        "title": "".join(d.get("h1", [d.get("title", "")])),
        "eyebrow": d.get("eyebrow", ""),
        "footer": d.get("share", {}).get("footer", ""),
        "ornament": orn_color["light"],
    }
    body = "\n".join(x for x in [
        render_hero(d, orn, lang),
        render_overview(d.get("overview", []), regions),
        render_route(d.get("route", {})),
        render_amap(d),
        render_weather(d.get("weather", {}), lang),
        render_plan(d.get("plan", {}), regions, lang),
        render_tickets(d.get("tickets", {}), lang),
        render_budget(d.get("budget", {}), lang),
        render_todo(d.get("todo", {}), lang),
        render_list(d.get("wear_heading", "穿什么"), d.get("wear", []), lang),
        render_list(d.get("tips_heading", "注意事项"), d.get("tips", []), lang),
        render_footer(d, lang),
    ] if x)

    head = ('<title>%s</title>\n'
            '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
            '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
            '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?%s&display=swap">\n'
            '<style>%s</style>\n' % (esc(d.get("title", "旅行路书")), fonts, css))
    main_html = ('%s\n<main class="page">\n%s\n</main>\n<div id="tip" hidden></div>\n'
                 '<script>window.ROADBOOK_SHARE=%s;</script>\n<script>%s</script>\n'
                 % (ICONS, body, json.dumps(share_cfg, ensure_ascii=False).replace("</", "<\\/"), JS))
    if fragment:
        return head + main_html
    return ('<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n<meta charset="UTF-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">\n'
            '%s</head>\n<body>\n%s</body>\n</html>\n' % (head, main_html))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    fragment = "--fragment" in sys.argv
    if not args:
        print("usage: build_roadbook.py roadbook.json [output.html] [--fragment]", file=sys.stderr)
        sys.exit(2)
    with open(args[0], "r", encoding="utf-8") as f:
        d = json.load(f)
    out = args[1] if len(args) > 1 else os.path.splitext(args[0])[0] + ".html"
    with open(out, "w", encoding="utf-8") as f:
        f.write(build(d, fragment))
    print("saved:", out)


if __name__ == "__main__":
    main()
