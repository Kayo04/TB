# PROGRESS

## Estado atual
- Milestone **0 (backtester) FEITO** — motor validado em dados sintéticos E em dados reais.
- Próximo: milestone 1 — interface `Strategy` + camada de dados ao vivo (aguarda go-ahead).

## Decisões tomadas
- Mercado: **crypto** (24/7). Motor agnóstico ao mercado.
- Stack: **Python** + `ccxt` + **Postgres**. Deploy **VPS** (não serverless).
- **LLM fora do loop de decisão.** Paper primeiro. Gate: bater buy & hold out-of-sample.

## Log de sessões
### Setup inicial
- Criado `backtester.py`: sem look-ahead (posição em t → vigor em t+1), fees + slippage,
  benchmark buy & hold.
- Resultado em dados sintéticos: MA crossover 20/50 ≈ **-32%**, abaixo do buy & hold (~-15%).
  Esperado — ruído + custos em cima de churn. Serve só para provar o motor.

### Dados reais (2026-07-22)
- `pip install -r requirements.txt` OK (ccxt 4.5.67, pandas 3.0.3, numpy 2.4.6).
- `__main__` trocado para `fetch_ohlcv_ccxt("BTC/USDT", "1h", 1500)`. Binance respondeu à
  primeira (não foi preciso fallback para kraken); devolveu **1000 barras**, não 1500 — limite
  default do ccxt/binance por pedido, não um erro. A revisitar se precisarmos de mais histórico
  (paginação com `since`).
- Resultado MA crossover (20/50), BTC/USDT 1h, binance, 1000 barras, fee 10bps + slippage 5bps:
  - `retorno_total`: **-2.23%**
  - `buy_and_hold`: **+6.67%**
  - `retorno_anual`: -17.9%
  - `sharpe`: **-0.66**
  - `max_drawdown`: -10.13%
  - `n_trades`: 10
- **Não bate buy & hold.** Confirma o esperado: MA crossover simples é só prova de motor, não
  fonte de edge — consistente com o não-objetivo em CLAUDE.md ("estratégias populares copiadas
  servem só para provar o motor"). Gate estratégia continua por cumprir; nada disto entra em
  execução.
- **Aviso de amostra:** 1000 barras de 1h ≈ 42 dias, 10 trades. Isto é demasiado pequeno para
  concluir seja o que for sobre a estratégia em si (ruído domina com N tão baixo). A conclusão
  válida desta corrida é "o motor produz números honestos e plausíveis", não "MA crossover foi
  avaliado". Não sobre-interpretar este resultado, mesmo que pareça confirmar a intuição.

### Pré-requisitos do gate de estratégia (2026-07-22)
- O **gate estratégia** (bater buy & hold out-of-sample, após custos — ver CLAUDE.md) **não é
  aplicável ainda** com o backtester atual, por dois motivos:
  1. **Profundidade histórica** — `fetch_ohlcv_ccxt` só traz ~1000 barras por pedido (limite da
     exchange/ccxt), sem paginação via `since`. Sem mais histórico não há amostra credível.
  2. **Sem split out-of-sample / walk-forward** — o backtester atual corre a estratégia sobre
     toda a série e reporta um único número. Isso é in-sample por definição; "bater buy & hold
     out-of-sample" exige treinar/otimizar num período e validar noutro que a estratégia nunca
     viu.
- Estes dois pontos são pré-requisitos de infraestrutura do backtester, não da estratégia.
  Nenhuma estratégia deve ser considerada "aprovada" ou "reprovada" pelo gate até ambos existirem.

### Milestone 1 — FEITO (2026-07-22)
- `git init` + commit de baseline antes do refactor (restauro possível se algo correr mal).
- Reestruturado para pacote `bot/` (`data/`, `strategy/`, `backtest/`) + `scripts/run_backtest.py`
  + `tests/`. `backtester.py` (flat, raiz) removido — substituído por `bot/backtest/engine.py`.
  `execution/`, `persistence/`, `risk/`, `orchestration/` **não** criados ainda — só quando os
  respetivos milestones começarem.
- Interface `Strategy` (`bot/strategy/base.py`): `compute_signal(df) -> pd.Series` pura, mais
  `warmup_bars()` como **limite superior rígido de memória** (não só "válido a partir de N
  barras") — o sinal na barra t só pode depender das últimas `warmup_bars` barras fechadas.
  Estratégias recursivas/expanding-window (ex: EMA a partir da barra 0) violam o contrato e
  quebram a paridade backtest/live silenciosamente; têm de ser reformuladas para janela fixa ou
  ficam de fora desta interface. `MACrossoverStrategy` movida para `bot/strategy/ma_crossover.py`
  como exemplo de estratégia bounded-window válida.
- **Teste de paridade** (`tests/test_strategy.py::test_vectorized_incremental_parity`): compara,
  barra a barra, o `compute_signal` vectorizado (histórico completo) com o incremental (buffer
  rolante limitado a `warmup_bars`, tal como o runner ao vivo fará). **7/7 testes passam**,
  incluindo paridade para MA 20/50 e MA 5/10. Este teste é a garantia real por trás do critério
  de sucesso do CLAUDE.md ("comportamento ao vivo bate certo com o backtest") — a interface só
  torna a garantia possível, o teste é que a verifica.
- Camada de dados (`bot/data/`): `MarketDataSource` Protocol com `fetch_history` (histórico,
  paginado via `since`) e `stream` (live, async, só barras FECHADAS). `CcxtDataSource`
  implementa ambos.
  - `fetch_history`: loop `since`-forward, dedupe por timestamp, respeita `rateLimit`. Testado
    offline com exchange falso (`tests/test_data.py`, 3 testes) e confirmado end-to-end contra
    binance real: `scripts/run_backtest.py` agora traz as **1500 barras** pedidas (antes só
    1000, limite de um único pedido). Bug apanhado e corrigido durante os testes: o filtro de
    paginação usava `< until` (estrito) mas o filtro final usava `<= until` (inclusivo) — a
    barra exatamente em `until` era descartada silenciosamente antes de chegar ao filtro final.
  - `stream`: **verificado no build (2026-07-22) que `ccxt.pro` websocket (`watch_ohlcv`)
    funciona para OHLCV público da binance sem API key e sem gate de licença** — testado
    ao vivo, recebeu barra em ~15s. Por isso o caminho **websocket é o usado**, não o fallback.
    Fallback REST short-poll (`_stream_poll`, atrás do mesmo `stream()`) implementado e
    disponível para exchanges/timeframes sem `watchOHLCV`, mas não é o que corre hoje.
- Resultado do `scripts/run_backtest.py` com histórico completo (1500 barras, BTC/USDT 1h,
  binance): retorno_total -4.54%, buy_and_hold -15.3%, sharpe -0.98, max_drawdown -10.13%,
  n_trades 13. Ainda ~62 dias — mesmo aviso de amostra pequena de antes aplica-se; não é uma
  avaliação da estratégia, só prova que a paginação funciona ponta-a-ponta.

### Nota: venue de dados/execução (2026-07-22)
- Binance mantém-se como fonte de dados por agora (funciona, sem fricção). Mas tanto a fonte de
  dados como a futura venue de execução podem vir a mudar para uma exchange **autorizada MiCA**
  (ex: Kraken), relevante para o gate de dinheiro real e residência em Portugal (ver Gates no
  CLAUDE.md). Decisão adiada — não bloqueia milestone 1, que é agnóstico à exchange por design
  (`CcxtDataSource(exchange=...)`).

### Milestone 2 — FEITO (2026-07-22)
- **Infra Postgres**: sem Docker nem Postgres a correr na máquina. Achado relevante: havia um
  PostgreSQL 16 nativo (`C:\Program Files\PostgreSQL\16`), mas o `installation_summary.log`
  mostra que o **servidor foi desinstalado em 2024-06-29** — só ficou a pasta `data` órfã (do
  projeto MyBody, presumivelmente). Não foi tocada. Dono instalou Docker Desktop (fora do meu
  alcance — precisa admin/reboot). A partir daí:
  - Container `trading-bot-postgres` (imagem `postgres:16`), volume nomeado
    `trading-bot-pgdata` (persiste entre restarts do container), porta 5432, DB `trading_bot`.
  - Password gerada aleatoriamente, `DATABASE_URL` escrito em `.env` (gitignored, nunca
    commitado; `.env.example` no repo documenta o formato).
  - Ligação verificada com `psycopg` antes de escrever qualquer código do milestone 2.
- **Decisão de sequenciamento confirmada: opção (b), Postgres agora**, não SQLite. Razão do
  dono: testar idempotência contra SQLite e só validar concorrência/transações contra Postgres
  no milestone 3 seria testar a semântica errada — exatamente a classe de falha que este
  milestone existe para apanhar.
- **Tabela `orders`** (`bot/execution/db.py`), mínima mas com `symbol`/`side`/`qty` incluídos
  (além de `client_order_id`/`status`/`filled_price`/`filled_ts`) para permitir reconstruir
  posição depois de um restart — dedupe sozinho não chega para isso. `status` inclui `'pending'`
  reservado para um futuro `LiveBroker`; `PaperBroker` nunca o escreve.
- **Fronteira de transação**: o fill do `PaperBroker` é sintético e totalmente calculável em
  memória antes de qualquer I/O — por isso "registar o ID" e "registar o fill" são a MESMA
  escrita: um único `INSERT ... ON CONFLICT (client_order_id) DO NOTHING ... RETURNING`. Nunca
  existe uma linha `'pending'` escrita por este broker, logo não há janela de crash que deixe
  uma ordem a meio. Isto é uma simplificação específica do paper — um `LiveBroker` real (fill
  não é conhecido antes da chamada à venue) vai precisar do padrão clássico de duas fases
  (registar `pending` -> chamar a venue -> confirmar), daí o `status` já ter espaço para isso.
- **`bot/execution/`**: `base.py` (Broker Protocol, `Order`/`Fill`/`Transition`), `order_ids.py`
  (`make_client_order_id` — única implementação, partilhada por qualquer broker futuro),
  `transitions.py` (`diff_transitions` com `prior_position` explícito para o caso de restart a
  meio de posição, `order_from_transition`), `db.py`, `paper_broker.py`.
- **21/21 testes a passar** (`pytest tests/`), incluindo os 5 acordados contra Postgres real:
  clean replay, tentativa abortada (rollback simulando crash antes do commit), crash depois do
  commit mas antes do chamador ver o resultado, submissão concorrente duplicada (8 threads, só
  uma linha `filled`), e reconstrução de posição a partir do Postgres num `PaperBroker` novo.
  Teste de concorrência corrido 10x isolado para excluir flakiness — estável nas 10.
- **Bug real apanhado durante os testes** (não no `PaperBroker`, no próprio teste): as ligações
  criadas manualmente nas threads do teste de concorrência não tinham `row_factory=dict_row`,
  causando `TypeError` ao aceder a `row["symbol"]`. Corrigido para usar o helper partilhado
  `get_connection()` em vez de `psycopg.connect()` cru — o tipo de inconsistência que o helper
  único existe para evitar.
- `qty` continua fixo em 1.0 (placeholder) — sizing é o milestone 4 (risk layer), não decidido
  aqui. Broker construído e testado isoladamente; ainda não está ligado a um loop de trading
  real (isso é o milestone 5, orquestração).

### Milestone 3 — FEITO (2026-07-22)
- **`orders`/`fills` separados** (antes colapsados numa tabela em milestone 2). `orders` =
  intenção (client_order_id, strategy_name, symbol, side, qty, status, effective_ts). `fills` =
  execução (fill_id, client_order_id FK, symbol, side, qty, price, fee, filled_ts). Razão:
  `LiveBroker` futuro pode ter fills parciais (uma ordem, vários fills) — conflar 1:1 agora só
  para desfazer mais tarde, exatamente quando a correção mais importa (ordens reais).
  `strategy_name` passou a coluna própria em `orders` (antes só entrava no hash do
  `client_order_id`, nunca persistido).
- **A garantia de atomicidade do milestone 2 sobrevive à divisão**: uma CTE com escrita
  (`WITH new_order AS (INSERT ... RETURNING ...) INSERT INTO fills SELECT ... FROM new_order`)
  mantém tudo numa única instrução/round-trip. Se `orders` bate no conflito, `new_order` fica
  vazio, o INSERT em `fills` não escreve nada — o mesmo "sem falha nunca deixa uma ordem a
  meio" do milestone 2, agora a atravessar duas tabelas.
- **Migração versionada e reproduzível**: `bot/persistence/migrations/0001_...sql` +
  `bot/persistence/migrate.py` (runner mínimo, tabela `schema_migrations`, idempotente —
  correr duas vezes é no-op) + `scripts/migrate.py`. Não é um DROP/CREATE manual: é um passo
  deliberado e commitado. Corrido contra o container real, aplicado, reconfirmado idempotente.
- **Sem tabela `positions`.** `position(symbol)` é sempre o fold de `fills`
  (`bot/persistence/ledger.py::position_from_ledger`/`all_positions`) — nunca um contador
  guardado. O cache em memória do `PaperBroker` mantém-se (ganho real de performance), mas só é
  legítimo porque: (a) é reconstruído do Postgres em cada instanciação, (b) só é atualizado
  imediatamente a seguir a uma escrita durável bem-sucedida, com os mesmos valores. Reforçado
  por teste (`test_position_always_equals_fold_of_fills`), não só por convenção.
- **Reconciliação**: `bot/persistence/reconciliation.py`. `ExternalPositionSource` Protocol;
  `LedgerPositionSource` (agora) faz um fold independente e fresco de `fills`, sem tocar no
  cache do broker — apanha exatamente a classe de bug "cache divergiu do ledger". Seam para
  `VenuePositionSource` (futuro `LiveBroker`, via ccxt) fica explícito no docstring, incluindo a
  nota de que spot crypto tem saldos de carteira, não um campo "posição" como futuros — tradução
  a resolver nessa altura, não agora. `reconcile()` escreve sempre uma linha em
  `reconciliation_checks` (divergente ou não) e devolve `list[Divergence]` estruturado — hook de
  alerta pronto, sem mecanismo de entrega (isso é observability, milestone 5/7). Decisão de
  parar (kill-switch) fica para o milestone 4 — reconciliação só deteta e regista.
- **Apenas convenção, não reforçado pela BD**: append-only é revisto por review, não por
  `REVOKE UPDATE, DELETE`. Dívida técnica registada aqui deliberadamente — falta um role de
  aplicação não-superuser, que não existe ainda (tudo corre como `postgres`). Sem teste
  grep-based a fingir que isto está garantido (foi avaliado e rejeitado: falsos positivos em
  colunas tipo `updated_at`/comentários, falsos negativos em SQL construído dinamicamente —
  teatro de garantia, pior que admitir que é só convenção).
- **`bot/persistence/`**: `db.py` (ligação), `migrate.py` (runner), `migrations/` (SQL
  versionado), `ledger.py` (`record_fill`, `existing_fill`, `position_from_ledger`,
  `all_positions`, `fills_for`), `reconciliation.py`. `bot/execution/db.py` do milestone 2
  removido — schema e SQL de persistência vivem só em `bot/persistence/` agora;
  `PaperBroker` calcula o fill (específico do paper), a persistência trata do resto.
- **27/27 testes a passar**, incluindo os 3 pedidos especificamente: CTE atómica orders+fills
  com o caminho de conflito a não escrever nada em nenhuma tabela
  (`test_record_fill_conflict_inserts_nothing_in_either_table`), posição sempre igual ao fold de
  `fills` (`test_position_always_equals_fold_of_fills`), e reconciliação a detetar uma
  divergência cache-vs-ledger injetada deliberadamente
  (`test_reconciliation_detects_injected_cache_vs_ledger_divergence`). Teste de concorrência do
  milestone 2 recorrido 10x contra o novo schema — estável.
- Strategy e o motor de backtest continuam sem importar `bot.persistence` nem `bot.execution` —
  inalterado desde o milestone 1.
- **Não construído (por desenho, não esquecimento):** dashboard, alerta com entrega real,
  resposta a divergência além de log/registo (kill-switch é milestone 4), reconciliação
  agendada/contínua (precisa do loop de orquestração, milestone 5).

## TODO imediato
- [ ] Milestone 4: risk layer (position sizing, limites, kill-switch) — usa `reconcile()` como
      um dos possíveis gatilhos de halt (aguarda go-ahead do dono).
- [ ] (Dívida técnica) `REVOKE UPDATE, DELETE ... FROM app_role` quando existir um role de
      aplicação não-superuser — ver nota no milestone 3.
- [ ] (Futuro, pré-requisito do gate) Split out-of-sample / walk-forward no backtester.
- [ ] (Futuro) Avaliar Kraken (MiCA) como venue de dados/execução em alternativa à Binance.
