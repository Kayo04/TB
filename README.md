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
Container Docker standalone, **separado** da stack `docker-compose` (essa não publica porta —
ver secção "Correr a stack completa" abaixo). Volume nomeado `trading-bot-pgdata-test`. Se já
existir:
```bash
docker start trading-bot-postgres-test
```
Se não existir:
```bash
docker run -d --name trading-bot-postgres-test \
  -e POSTGRES_PASSWORD=<escolhe uma> -e POSTGRES_DB=trading_bot \
  -p 5432:5432 -v trading-bot-pgdata-test:/var/lib/postgresql/data postgres:16
```
Ver `.env.example` para o formato de `DATABASE_URL` a apontar para este container (o `.env` real
está no `.gitignore`, nunca commitado). Schema gerido por migrations versionadas em
`bot/persistence/migrations/` — nunca `CREATE TABLE` manual; ver `scripts/migrate.py`.

Estrutura: `bot/data` (histórico paginado + live), `bot/strategy` (interface `Strategy`),
`bot/backtest` (motor), `bot/execution` (paper broker + idempotência), `bot/persistence`
(ledger append-only, posição derivada, reconciliação), `bot/risk` (kill-switch durável,
`RiskGate` fail-closed, limites configuráveis), `bot/orchestration` (loop autónomo bar-aligned,
`run_log` append-only, alertas), `dashboard/` (Next.js, só leitura — ver abaixo).

Se o bot estiver halted (kill-switch ligado), só um humano o desbloqueia:
`python scripts/clear_halt.py "<nome>" "<motivo>"`.

Correr o loop autónomo sozinho, fora do Docker (paper, BTC/USDT 1h): `python scripts/run_live.py`.

## Correr a stack completa (bot + Postgres + dashboard)
`docker-compose.yml` sobe os três serviços juntos — pensado tanto para correr **localmente** como
num VPS (ver `DEPLOY.md` para esse caso). `db` nunca publica porta (só alcançável pelos outros
dois serviços pela rede interna do Compose); `dashboard` publica só em `127.0.0.1:3000` — nunca
na rede local, só nesta máquina.

Nota: esta stack usa um Postgres **separado** do container de testes acima (volume `pgdata`
próprio, gerido pelo Compose) — normal ter os dois a existir ao mesmo tempo numa máquina de dev.

```bash
# .env (raiz do repo) -- gerar localmente é seguro aqui, sem ser um VPS remoto:
echo "POSTGRES_PASSWORD=$(openssl rand -base64 24 | tr -dc 'A-Za-z0-9')" > .env
echo "DASHBOARD_DB_PASSWORD=$(openssl rand -base64 24 | tr -dc 'A-Za-z0-9')" >> .env

docker compose up -d --build
```
A primeira subida cria o role `dashboard_ro` (migration `0004`) mas sem password — definir uma
vez, usando o mesmo valor de `DASHBOARD_DB_PASSWORD` que puseste no `.env`:
```bash
docker compose exec db psql -U postgres -d trading_bot \
  -c "ALTER ROLE dashboard_ro WITH PASSWORD '<o mesmo valor de DASHBOARD_DB_PASSWORD>'"
docker compose restart dashboard
```
Abrir **http://localhost:3000** no browser. Pronto — sem tunnel, é a tua própria máquina.

O dashboard só lê (role `dashboard_ro`, `GRANT SELECT` apenas — ver
`bot/persistence/migrations/0004_dashboard_readonly_role.sql` e
`tests/test_dashboard_role.py`, que prova com um `INSERT` real a ser recusado, não por convenção).

## Deploy (VPS, 24/7 real)
Ver `DEPLOY.md` para o runbook completo — Docker Compose (`bot` + `db`, sem portas publicadas),
`restart: unless-stopped`, backups diários, hardening do servidor, smoke test de conectividade à
exchange, e observabilidade remota.

## Princípio central
"Está a funcionar" = corre sozinho, fiável, reconciliável — **não** "deu dinheiro".
