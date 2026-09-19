#!/usr/bin/env python3
"""Render a ladder snapshot as a self-contained HTML page.

The layout mirrors the classic liquidity ladder: strikes descending, a bar per
strike sized by liquidity (green above spot, red below), the call mid on one
side and the put mid on the other, the spot row pinned in the middle, and the
key levels drawn as dashed rows.
"""

import argparse
import json
import html


def fmt_size(n):
    if not n:
        return ""
    if n >= 1000:
        return f"{n / 1000:.0f}K" if n >= 10000 or n % 1000 < 100 else f"{n / 1000:.1f}K"
    return str(n)


def fmt_price(p):
    if p is None:
        return "—"
    return f"{p:.2f}" if p < 100 else f"{p:.1f}"


def fmt_strike(s):
    return f"{s:g}"


def render(snap):
    rows = sorted(snap["rows"], key=lambda r: r["strike"], reverse=True)
    spot = snap["spot"]
    peak = max((r.get("liquidity") or 0) for r in rows) or 1
    key_levels = {v: k for k, v in (snap.get("key_levels") or {}).items() if v}
    metric_label = "الفوليوم" if snap.get("metric") == "volume" else "العقود المفتوحة"

    # The spot row is injected between the two strikes it sits between.
    body = []
    spot_drawn = False
    for row in rows:
        strike = row["strike"]
        if not spot_drawn and strike < spot:
            body.append(
                f'<div class="row spot"><div class="strike">{spot:g}</div>'
                f'<div class="track"><span class="spot-line"></span></div>'
                f'<div class="px spot-label" style="grid-column:span 2">السعر الحالي</div></div>'
            )
            spot_drawn = True

        side = "call" if strike > spot else "put"
        width = (row.get("liquidity") or 0) / peak * 100
        size = row.get(f"{side}_oi") or row.get(f"{side}_vol") or 0
        level = key_levels.get(strike)
        classes = f"row {side}" + (" keylevel" if level else "")
        tag = f'<span class="tag">{html.escape(LEVEL_AR.get(level, level or ""))}</span>' if level else ""

        body.append(
            f'<div class="{classes}" title="{fmt_strike(strike)} · call OI {row.get("call_oi",0)} · put OI {row.get("put_oi",0)}">'
            f'<div class="strike">{fmt_strike(strike)}{tag}</div>'
            f'<div class="track"><span class="bar" style="width:{width:.1f}%">'
            f'<span class="size">{fmt_size(size)}</span></span></div>'
            f'<div class="px call-px">{fmt_price(row.get("call_price"))}</div>'
            f'<div class="px put-px">{fmt_price(row.get("put_price"))}</div>'
            f"</div>"
        )

    best_call, best_put = snap.get("best_call"), snap.get("best_put")
    chips = "".join(
        f'<span class="chip c">{fmt_size(t["oi"])} · {fmt_strike(t["strike"])}</span>'
        for t in (snap.get("top_calls") or [])[1:]
    ) + "".join(
        f'<span class="chip p">{fmt_size(t["oi"])} · {fmt_strike(t["strike"])}</span>'
        for t in (snap.get("top_puts") or [])[1:]
    )

    kl = snap.get("key_levels") or {}
    legend = " · ".join(
        f"{LEVEL_AR[k]} {v:g}" for k, v in kl.items() if v and k in LEVEL_AR
    )

    return TEMPLATE.format(
        symbol=html.escape(snap["symbol"]),
        expiry=html.escape(str(snap.get("expiry") or "")),
        spot=f"{spot:g}",
        as_of=html.escape(str(snap.get("as_of") or ""))[:19].replace("T", " "),
        metric=metric_label,
        rows="\n".join(body),
        best_call=(f'{fmt_size(best_call["oi"])} · {fmt_strike(best_call["strike"])}'
                   if best_call else "—"),
        best_put=(f'{fmt_size(best_put["oi"])} · {fmt_strike(best_put["strike"])}'
                  if best_put else "—"),
        chips=chips,
        legend=html.escape(legend),
    )


LEVEL_AR = {
    "call_wall": "جدار الكول",
    "put_wall": "جدار البوت",
    "max_pain": "ماكس بين",
    "gamma_flip": "انقلاب الجاما",
}

TEMPLATE = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{symbol} — سلّم السيولة</title>
<style>
  :root {{
    --bg:#0b1016; --panel:#111823; --line:#1d2836; --text:#e6edf5; --muted:#7d8fa6;
    --call:#16c784; --call-dim:#16c78433; --put:#e3405f; --put-dim:#e3405f33;
    --spot:#f0b90b;
  }}
  * {{ box-sizing:border-box; }}
  body {{
    margin:0; background:var(--bg); color:var(--text);
    font:14px/1.4 -apple-system,"Segoe UI",Tahoma,sans-serif;
    padding:16px; display:flex; justify-content:center;
  }}
  .wrap {{ width:100%; max-width:560px; }}
  header {{
    display:flex; align-items:center; gap:12px; flex-wrap:wrap;
    background:var(--panel); border:1px solid var(--line); border-radius:12px;
    padding:12px 14px; margin-bottom:10px;
  }}
  .sym {{ font-weight:700; letter-spacing:.5px; }}
  .now {{ color:var(--spot); font-size:20px; font-weight:700; font-variant-numeric:tabular-nums; }}
  .meta {{ color:var(--muted); font-size:12px; margin-inline-start:auto; text-align:start; }}
  .ladder {{
    background:var(--panel); border:1px solid var(--line); border-radius:12px;
    overflow:hidden;
  }}
  .row {{
    display:grid; grid-template-columns:112px 1fr 56px 56px;
    align-items:center; gap:8px; padding:3px 10px;
    border-bottom:1px solid #131b26; font-variant-numeric:tabular-nums;
  }}
  .row:last-child {{ border-bottom:none; }}
  .strike {{ color:var(--muted); font-size:12.5px; display:flex; align-items:center;
             gap:5px; justify-content:flex-start; }}
  .track {{ position:relative; height:16px; display:flex; align-items:center; }}
  .bar {{ height:13px; border-radius:2px; display:block; }}
  .call .bar {{ background:linear-gradient(90deg,var(--call-dim),var(--call)); }}
  .put  .bar {{ background:linear-gradient(90deg,var(--put-dim),var(--put)); }}
  .bar {{ position:relative; }}
  .size {{ position:absolute; inset-inline-end:100%; top:50%; transform:translateY(-50%);
           font-size:10.5px; color:var(--muted); padding-inline:6px; white-space:nowrap; }}
  .spot-label {{ white-space:nowrap; }}
  .px {{ text-align:end; font-size:12.5px; }}
  .call-px {{ color:var(--call); }}
  .put-px {{ color:var(--put); }}
  .keylevel {{ background:#141d2a; }}
  .keylevel .track::after {{
    content:""; position:absolute; inset-inline:0; top:50%;
    border-top:1px dashed #4a5b70;
  }}
  .tag {{ font-size:9px; white-space:nowrap; color:#9fb0c6; background:#1b2634; border-radius:4px; padding:1px 4px; }}
  .spot {{ background:#1a1608; }}
  .spot .strike {{ color:var(--spot); font-weight:700; font-size:13px; }}
  .spot .px {{ color:var(--spot); font-size:11px; }}
  .spot-line {{ display:block; width:100%; border-top:1px dashed var(--spot); }}
  footer {{ margin-top:10px; }}
  .best {{
    display:flex; gap:8px; justify-content:center; margin-bottom:8px; flex-wrap:wrap;
  }}
  .best div {{
    background:var(--panel); border:1px solid var(--line); border-radius:999px;
    padding:8px 16px; font-size:13px;
  }}
  .best .c {{ border-color:var(--call); color:var(--call); }}
  .best .p {{ border-color:var(--put); color:var(--put); }}
  .chips {{ display:flex; gap:6px; justify-content:center; flex-wrap:wrap; }}
  .chip {{ font-size:11.5px; border-radius:999px; padding:5px 11px; border:1px solid var(--line); color:var(--muted); }}
  .chip.c {{ border-color:#16c78455; color:var(--call); }}
  .chip.p {{ border-color:#e3405f55; color:var(--put); }}
  .note {{ color:var(--muted); font-size:11px; text-align:center; margin-top:10px; }}
  @media (max-width:420px) {{
    .row {{ grid-template-columns:96px 1fr 48px 48px; }}
  }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <span class="sym">{symbol}</span>
    <span class="now">{spot}</span>
    <span class="meta">انتهاء {expiry}<br>{as_of} · حجم الشريط: {metric}</span>
  </header>

  <div class="ladder">
{rows}
  </div>

  <footer>
    <div class="best">
      <div class="c">أقوى كول: {best_call}</div>
      <div class="p">أقوى بوت: {best_put}</div>
    </div>
    <div class="chips">{chips}</div>
    <div class="note">{legend}</div>
  </footer>
</div>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("snapshot")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    with open(args.snapshot) as fh:
        snap = json.load(fh)
    with open(args.out, "w") as fh:
        fh.write(render(snap))
    print(f"{args.out}: {len(snap['rows'])} strikes")


if __name__ == "__main__":
    main()
