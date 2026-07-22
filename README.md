# Trading Bot (autónomo, paper-first)

Projeto de engenharia: um trading bot 100% autónomo, focado em **fiabilidade**, não em lucro.
Ver `CLAUDE.md` para o objetivo, arquitetura, roadmap e regras. Estado atual em `PROGRESS.md`.

## Arranque rápido
```bash
pip install -r requirements.txt
python backtester.py            # corre em dados sintéticos (prova o motor)
```
Para dados reais, no `__main__` do `backtester.py` troca `synthetic_ohlcv()` por
`fetch_ohlcv_ccxt("BTC/USDT", "1h", 1500)`.

## Princípio central
"Está a funcionar" = corre sozinho, fiável, reconciliável — **não** "deu dinheiro".
