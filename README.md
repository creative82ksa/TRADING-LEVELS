# TRADING-LEVELS

مستويات التداول اليومية، وسلّم سيولة العقود.

## المحتويات

- `levels.json` — مستويات الدخول والأهداف اليومية لكل رمز.
- `ladder/` — بناء وعرض سلّم سيولة العقود (option chain ladder).
- `data/` — لقطات جاهزة للعرض.
- `docs/LADDER-AR.md` — شرح البنية وكيفية التوسعة.

## سلّم السيولة

```bash
python3 ladder/build_snapshot.py --quotes raw/quotes.json \
  --exposure raw/exposure.json --levels raw/levels.json \
  --symbol SPX --out data/SPX-2026-09-21.json

python3 ladder/render.py data/SPX-2026-09-21.json --out ladder.html
```

التفاصيل كاملة في [`docs/LADDER-AR.md`](docs/LADDER-AR.md).
