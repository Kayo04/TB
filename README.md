# Trading Bot (autónomo, paper-first)

Projeto de engenharia: um trading bot 100% autónomo, focado em **fiabilidade**, não em lucro.
Ver `CLAUDE.md` para o objetivo, arquitetura, roadmap e regras. Estado atual em `PROGRESS.md`.

## Arranque rápido
```bash
pip install -r requirements.txt
python scripts/run_backtest.py  # MA crossover (20/50) em BTC/USDT real, via binance
pytest tests/                    # inclui paridade vectorizado/incremental + testes de execução (Postgres)
```

### Postgres local (necessário para os testes de execução)
Container Docker `trading-bot-postgres`, volume nomeado `trading-bot-pgdata` (persiste entre
restarts do container). Se já existir:
```bash
docker start trading-bot-postgres
```
Se não existir, ver `.env.example` para o formato de `DATABASE_URL` (o `.env` real está no
`.gitignore`, nunca commitado).

Estrutura: `bot/data` (histórico paginado + live), `bot/strategy` (interface `Strategy`),
`bot/backtest` (motor), `bot/execution` (paper broker + idempotência via Postgres).
Ver `CLAUDE.md` para a arquitetura completa.

## Princípio central
"Está a funcionar" = corre sozinho, fiável, reconciliável — **não** "deu dinheiro".
