# Trading Bot (autónomo, paper-first)

Projeto de engenharia: um trading bot 100% autónomo, focado em **fiabilidade**, não em lucro.
Ver `CLAUDE.md` para o objetivo, arquitetura, roadmap e regras. Estado atual em `PROGRESS.md`.

## Arranque rápido
```bash
pip install -r requirements.txt
python scripts/migrate.py        # aplica migrations pendentes (idempotente)
python scripts/run_backtest.py  # MA crossover (20/50) em BTC/USDT real, via binance
pytest tests/                    # inclui paridade vectorizado/incremental + testes de execução/persistência (Postgres)
```

### Postgres local (necessário para os testes de execução/persistência)
Container Docker `trading-bot-postgres`, volume nomeado `trading-bot-pgdata` (persiste entre
restarts do container). Se já existir:
```bash
docker start trading-bot-postgres
```
Se não existir, ver `.env.example` para o formato de `DATABASE_URL` (o `.env` real está no
`.gitignore`, nunca commitado). Schema gerido por migrations versionadas em
`bot/persistence/migrations/` — nunca `CREATE TABLE` manual; ver `scripts/migrate.py`.

Estrutura: `bot/data` (histórico paginado + live), `bot/strategy` (interface `Strategy`),
`bot/backtest` (motor), `bot/execution` (paper broker + idempotência), `bot/persistence`
(ledger append-only, posição derivada, reconciliação), `bot/risk` (kill-switch durável,
`RiskGate` fail-closed, limites configuráveis).
Ver `CLAUDE.md` para a arquitetura completa.

Se o bot estiver halted (kill-switch ligado), só um humano o desbloqueia:
`python scripts/clear_halt.py "<nome>" "<motivo>"`.

## Princípio central
"Está a funcionar" = corre sozinho, fiável, reconciliável — **não** "deu dinheiro".
