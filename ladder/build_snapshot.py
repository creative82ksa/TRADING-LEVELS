#!/usr/bin/env python3
"""Normalize raw FlashAlpha responses into one ladder snapshot.

Inputs are the raw JSON bodies of three FlashAlpha endpoints, saved to disk:

  --quotes    /v1/option/quote?symbol=SPX&expiry=YYYY-MM-DD   (full chain, both sides)
  --exposure  /v1/exposure/sheet?symbol=SPX                   (per-strike call_oi/put_oi)
  --levels    /v1/flow/levels?symbol=SPX&expiry=YYYY-MM-DD    (call wall / put wall / max pain)

Only --quotes is required; the other two add the dashed key-level rows.
The output is the single file the renderer and any UI read from, so the fetch
layer stays swappable (MCP dump today, websocket tomorrow).
"""

import argparse
import json
from datetime import datetime, timezone


def load(path):
    if not path:
        return None
    with open(path) as fh:
        return json.load(fh)


def mid_price(leg):
    """Mid, falling back to whichever side of the book is quoted."""
    for key in ("mid", "lastPrice", "last"):
        val = leg.get(key)
        if val:
            return float(val)
    bid, ask = leg.get("bid"), leg.get("ask")
    if bid and ask:
        return (float(bid) + float(ask)) / 2
    return float(bid or ask or 0)


def spread_pct(leg):
    bid, ask = leg.get("bid") or 0, leg.get("ask") or 0
    if not bid or not ask:
        return None
    return round((ask - bid) / ((ask + bid) / 2) * 100, 1)


def build_rows(quotes, settled_oi):
    """Collapse the flat quote list into one row per strike."""
    rows = {}
    for leg in quotes:
        strike = float(leg["strike"])
        row = rows.setdefault(strike, {"strike": strike})
        side = "call" if leg.get("type", "").upper().startswith("C") else "put"
        row[f"{side}_price"] = mid_price(leg)
        row[f"{side}_bid"] = leg.get("bid")
        row[f"{side}_ask"] = leg.get("ask")
        row[f"{side}_oi"] = int(leg.get("open_interest") or 0)
        row[f"{side}_vol"] = int(leg.get("volume") or 0)
        row[f"{side}_iv"] = leg.get("implied_vol")
        row[f"{side}_delta"] = leg.get("delta")
        row[f"{side}_gamma"] = leg.get("gamma")
        row[f"{side}_spread_pct"] = spread_pct(leg)

    # The exposure sheet carries settled OI across every expiry. Where the
    # per-expiry quote has no OI yet (fresh strike, pre-open), fall back to it.
    for strike, sheet_row in (settled_oi or {}).items():
        row = rows.get(strike)
        if not row:
            continue
        for side in ("call", "put"):
            if not row.get(f"{side}_oi"):
                row[f"{side}_oi"] = int(sheet_row.get(f"{side}_oi") or 0)

    return [rows[k] for k in sorted(rows)]


def liquidity(row, metric):
    """Bar length for a row: volume when the session is live, else open interest."""
    if metric == "volume":
        live = (row.get("call_vol") or 0) + (row.get("put_vol") or 0)
        if live:
            return live
    return (row.get("call_oi") or 0) + (row.get("put_oi") or 0)


def window(rows, spot, width):
    """Keep `width` strikes either side of spot — the ladder is a local view."""
    if not rows:
        return rows
    nearest = min(range(len(rows)), key=lambda i: abs(rows[i]["strike"] - spot))
    return rows[max(0, nearest - width) : nearest + width + 1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quotes", required=True)
    ap.add_argument("--exposure")
    ap.add_argument("--levels")
    ap.add_argument("--symbol", default="SPX")
    ap.add_argument("--spot", type=float)
    ap.add_argument("--metric", choices=["open_interest", "volume"], default="open_interest")
    ap.add_argument("--width", type=int, default=15, help="strikes shown each side of spot")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    quotes = load(args.quotes)
    if isinstance(quotes, dict):
        quotes = quotes.get("quotes") or quotes.get("data") or []

    exposure = load(args.exposure) or {}
    levels = load(args.levels) or {}

    settled_oi = {float(r["strike"]): r for r in exposure.get("strikes", [])}
    spot = args.spot or levels.get("underlying_price") or exposure.get("underlying_price")
    if not spot:
        raise SystemExit("no spot price: pass --spot or supply --levels/--exposure")

    rows = window(build_rows(quotes, settled_oi), spot, args.width)
    for row in rows:
        row["liquidity"] = liquidity(row, args.metric)

    # Strongest contracts: OTM side only, since that is what the ladder ranks —
    # an ITM strike carries size for reasons that have nothing to do with a day trade.
    calls = [r for r in rows if r["strike"] > spot]
    puts = [r for r in rows if r["strike"] < spot]
    top_calls = sorted(calls, key=lambda r: r.get("call_oi", 0), reverse=True)[:4]
    top_puts = sorted(puts, key=lambda r: r.get("put_oi", 0), reverse=True)[:4]

    snapshot = {
        "symbol": args.symbol,
        "expiry": quotes[0]["expiry"] if quotes else None,
        "spot": spot,
        "metric": args.metric,
        "as_of": levels.get("as_of") or datetime.now(timezone.utc).isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "key_levels": {
            "call_wall": levels.get("live_call_wall"),
            "put_wall": levels.get("live_put_wall"),
            "max_pain": levels.get("live_max_pain"),
            "gamma_flip": levels.get("live_gamma_flip"),
        },
        "best_call": {"strike": top_calls[0]["strike"], "oi": top_calls[0].get("call_oi"),
                      "price": top_calls[0].get("call_price")} if top_calls else None,
        "best_put": {"strike": top_puts[0]["strike"], "oi": top_puts[0].get("put_oi"),
                     "price": top_puts[0].get("put_price")} if top_puts else None,
        "top_calls": [{"strike": r["strike"], "oi": r.get("call_oi")} for r in top_calls],
        "top_puts": [{"strike": r["strike"], "oi": r.get("put_oi")} for r in top_puts],
        "rows": rows,
    }

    with open(args.out, "w") as fh:
        json.dump(snapshot, fh, indent=2)
    print(f"{args.out}: {len(rows)} strikes around {spot} ({args.symbol} {snapshot['expiry']})")


if __name__ == "__main__":
    main()
