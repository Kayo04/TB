# Trading Bot (autónomo, paper-first)

Projeto de engenharia: um trading bot 100% autónomo, focado em **fiabilidade**, não em lucro.
Ver `CLAUDE.md` para o objetivo, arquitetura, roadmap e regras. Estado atual em `PROGRESS.md`.

## Arranque rápido
```bash
pip install -r requirements.txt
python scripts/run_backtest.py  # MA crossover (20/50) em BTC/USDT real, via binance
pytest tests/                    # inclui o teste de paridade vectorizado vs incremental
```
Estrutura: `bot/data` (histórico paginado + live), `bot/strategy` (interface `Strategy`),
`bot/backtest` (motor). Ver `CLAUDE.md` para a arquitetura completa.

## Princípio central
"Está a funcionar" = corre sozinho, fiável, reconciliável — **não** "deu dinheiro".
