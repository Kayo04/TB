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

### Milestone 4 — FEITO (2026-07-22)
- **`RiskGate` (`bot/risk/gate.py`) é um `Broker` que envolve um `Broker`** — mesmo protocolo
  (`submit_order`, `position`), mesmo truque de seam que `ExternalPositionSource` já usava para
  reconciliação. Um chamador futuro (orquestração, milestone 5) segura "um `Broker`" sem saber
  nem precisar de saber se é o `PaperBroker` cru ou o `RiskGate` à volta dele.
- **Fail-closed é a regra central, aplicada em dois pontos concretos, não só documentada:**
  1. `kill_switch.is_halted()` — se a própria leitura falhar (ligação em baixo, etc.), devolve
     `True`. Não-conseguir-ler-estado e estar-halted são tratados como o mesmo caso.
  2. `RiskGate.submit_order()` — toda a avaliação (kill-switch + checks) corre dentro de um único
     `try/except`; qualquer exceção de qualquer check é convertida em bloqueio, nunca propagada
     nem tratada como "permitir implícito". O broker por baixo nunca é chamado nesse caminho.
  Verificado por comportamento real, não só por design: `test_risk_check_exception_defaults_to_block`
  (check a levantar exceção → ordem rejeitada, zero linhas em `orders`) e
  `test_is_halted_returns_true_when_read_fails` (ligação fechada → `True`). Diferente do
  grep-test rejeitado no milestone 3 — isto testa comportamento em runtime, não padrão estático
  no código-fonte.
- **Kill-switch durável**: tabela `risk_events` (append-only, mesmo padrão do ledger/
  `reconciliation_checks`) — `event_type` `'halt'`/`'clear'`, estado atual = tipo da linha mais
  recente. Sobrevive a restart por construção: nada vive em memória, `is_halted()` lê sempre do
  Postgres. `clear_halt()` só é chamado a partir de `scripts/clear_halt.py` (CLI manual,
  `cleared_by`/`note` obrigatórios e não-vazios) — nenhum caminho automático do código chama
  `clear_halt()`, por isso um bot halted que reinicia continua halted até intervenção humana.
  Testado: halt → nova ligação (restart simulado) → continua halted → `RiskGate` novo nessa
  ligação rejeita uma ordem por "kill switch" → só `clear_halt` desbloqueia, visível de qualquer
  ligação depois.
- **Dois tipos de resposta, deliberadamente diferentes:**
  - **Rejeição por-ordem** (bot continua a correr): `max_position_size` (default 1.0 unidade por
    símbolo — sizing real por risco continua adiado até existir uma estratégia real; `qty`
    placeholder mantém-se 1.0) e `max_orders_per_period` (default 10/1h, guarda contra um bug a
    disparar ordens em loop, não uma restrição de rotina). Uma ordem rejeitada não mexe posição
    nem halted; a próxima ordem dentro dos limites continua a passar — testado explicitamente
    (`test_max_position_size_rejects_order_but_bot_keeps_running`).
  - **Halt ao nível do bot** (durável, para tudo até intervenção humana): `max_daily_drawdown`
    (default 5%, mark-to-market — ver abaixo) e divergência de reconciliação
    (`checks.handle_reconciliation`, alimentado pelo `list[Divergence]` que `reconcile()` já
    devolvia no milestone 3). `reconciliation.py` continua **sem qualquer import de `bot.risk`**
    — a dependência vai de risk para o tipo `Divergence`, nunca ao contrário; reconciliação
    continua a não saber que halting existe.
  Todos os três limites são `RiskLimits`, configuráveis com defaults conservadores — não
  hardcoded, para poderem ser afinados depois de ver comportamento real.
- **Drawdown diário: mark-to-market, não só realizado.** Decisão explícita: para uma estratégia
  sempre-em-posição (MA crossover), um check só-realizado seria cego a perdas não realizadas
  exatamente quando um halt mais importa. `equity_snapshots` (append-only) regista, a cada
  avaliação, `cash_flow` (fold do dia sobre `fills`, líquido de fees) + `mark_to_market`
  (posição × preço atual) = `total_equity`. `mark_prices` é passado pelo chamador
  (`MarkPriceSource` Protocol, `StaticMarkPriceSource` como implementação trivial) — o risk layer
  não importa `bot.data`, mesmo desacoplamento que `ExternalPositionSource`. Drawdown = pico do
  dia (UTC) menos equity atual, sobre o pico; breach chama `kill_switch.trip_halt()` a partir de
  dentro do próprio check. Testado: pico 100 (preço 200) → crash para preço 90 (equity -10,
  drawdown 110%) → halt disparado com `triggered_by='max_daily_drawdown'`, e uma ordem
  completamente inofensiva submetida a seguir é rejeitada só porque o kill-switch está ligado
  (`test_drawdown_breach_trips_durable_halt`) — prova que o halt é global, não por-ordem.
- **`Fill` ganhou campo `reason: Optional[str] = None`** (`bot/execution/base.py`) — motivo
  visível numa ordem rejeitada; default `None` mantém compatível com todas as construções
  existentes de `Fill`.
- **Migração `0002_risk_layer.sql`**: `risk_events`, `equity_snapshots`, índices por
  `created_at`/`recorded_at`. Aplicada e reconfirmada idempotente. Enforcement append-only:
  mesma nota do milestone 3 — convenção revista por review, `REVOKE` continua dívida técnica.
- **`bot/risk/`**: `base.py` (`RiskDecision`, `RiskLimits`), `kill_switch.py` (`is_halted`,
  `trip_halt`, `clear_halt`), `checks.py` (os quatro checks), `gate.py` (`RiskGate`,
  `MarkPriceSource`, `StaticMarkPriceSource`). `scripts/clear_halt.py` novo.
- **35/35 testes a passar**, incluindo os 4 pedidos especificamente isolados: os dois testes
  fail-closed, halt durável a sobreviver a restart só limpo pelo CLI, `max_position_size` a
  rejeitar uma ordem sem parar o bot, e um breach de drawdown a disparar o halt durável. Testado
  também de ponta a ponta fora do pytest: `scripts/clear_halt.py` correu contra um halt real,
  confirmado halted → cleared → not halted.
- Strategy e o motor de backtest continuam sem qualquer import de `bot.risk` — inalterado.

### Milestone 5 — FEITO (2026-07-22)
- **Loop bar-aligned, `stream()` como relógio.** `LiveRunner.run_forever()` é
  `async for bar in data_source.stream(symbol, timeframe): ...` — nenhum scheduler novo. Um
  timeframe de 1h só produz uma decisão nova quando um bar fecha, e `stream()` (milestone 1) já é
  exatamente esse gatilho (websocket `watch_ohlcv`, com fallback REST atrás da mesma interface).
  Um ciclo completo por bar: acrescenta ao buffer rolante → `compute_signal` → deriva transição →
  `RiskGate.submit_order` → `reconcile()` + `handle_reconciliation()` (SEMPRE, não só quando há
  ordem) → `check_daily_drawdown()` (SEMPRE também) → escreve uma linha em `run_log`. Fecha
  explicitamente o TODO deixado pelo milestone 4: reconciliação e drawdown agora têm cadência
  periódica real, não dependem de uma ordem acontecer.
- **Buffer em memória, deliberadamente não persistido.** `seed_from_history()` reconstrói via
  `fetch_history(since=now - warmup_bars*timeframe)` em todo arranque (frio ou restart) — barato,
  dados públicos, sem estado interno necessário. Só o que NÃO pode ser re-derivado de um feed
  público (posições/ordens/halt) vive em Postgres.
- **Sem ciclos sobrepostos, por construção.** `async for` sequencial: o gerador só produz o
  próximo bar quando o processamento do anterior já libertou o controlo. Timeout por ciclo
  (default 30s) via `asyncio.wait_for(asyncio.to_thread(_run_cycle_sync, bar), timeout=...)` — o
  corpo do ciclo é síncrono (Strategy e chamadas a Postgres não têm `await`), por isso corre numa
  thread à parte só para que `wait_for` tenha um ponto real onde poder desistir; sem isto o
  timeout seria decorativo, nunca interromperia nada.
- **Falha de stream vs. falha de ciclo, tratadas de forma diferente.** Falha do próprio `stream()`
  (queda de ligação) é existencial — sem stream, nenhum bar futuro chega — por isso tem retry com
  backoff exponencial (5s→300s, default) e reconecta. Falha de UM ciclo (bug, dado mau, timeout)
  não é retentada para esse bar — fica registada e o loop avança para o próximo bar assim que
  chegar. Decisão fail-closed deliberada: falhar = não negociar neste ciclo, nunca negociar com
  estado parcial. Nenhum caminho de código consegue chamar `submit_order()` depois de uma exceção
  algures antes dele no mesmo ciclo — o `try/except/finally` é único, não há recuperação parcial.
- **Bug real apanhado e corrigido durante a construção**: um timeout do `wait_for` não produzia,
  por si só, nenhuma linha em `run_log` — a thread abandonada só regista (no seu próprio
  `finally`) quando eventualmente terminar, e nessa altura pode ter tido sucesso, apagando
  silenciosamente o facto de o loop já ter desistido dela. Corrigido: o ramo `except
  asyncio.TimeoutError` em `run_forever` regista o ciclo como falhado imediatamente e de forma
  durável, sem depender do que a thread abandonada acabe por fazer. Distinto de qualquer outra
  exceção (essas já passam pelo `finally` do próprio `_run_cycle_sync` antes de propagar — registar
  outra vez a duplicava). Teste `test_hung_cycle_hits_timeout_and_loop_moves_on` falhou primeiro
  com o bug real, não só depois de ajustado — a thread tardia reescrevia a linha com
  `'no_transition'`, mascarando o timeout.
- **Corrida não-defendida, documentada e não corrigida (dívida técnica proporcional).** Uma thread
  verdadeiramente presa não pode ser morta à força em Python; continua a correr e pode, no caso
  patológico, ainda chamar `submit_order()` "fora de banda" depois do loop já ter avançado,
  correndo em paralelo com o ciclo seguinte na mesma ligação partilhada. Com ciclos ~1h à parte e
  timeout default de 30s, a janela é desprezável na prática; em paper o pior caso é inofensivo (a
  dedupe de `client_order_id` do milestone 2/3 apanha uma ordem duplicada de qualquer forma). Só
  se torna um problema real a resolver quando existir um `LiveBroker`, com âmbito próprio nessa
  altura — não corrigido aqui, decisão deliberada, mesmo espírito do `REVOKE` adiado no
  milestone 3.
- **Observabilidade**: log estruturado por ciclo via `logging` stdlib (sem dependência nova) para
  stdout. `run_log` (migração `0003_run_log.sql`, append-only, mesma convenção de todas as outras
  tabelas) — uma linha por tentativa de ciclo, sucesso ou falha, escrita a partir de um `finally`
  para nunca ser saltada; é a fonte de dados pretendida para o futuro dashboard (não construído
  aqui). `AlertSink` Protocol + `LogAlertSink` (`logger.critical`) — seam real, entrega a sério
  fica para mais tarde, mesmo padrão de `ExternalPositionSource`/`MarkPriceSource`. Disparado só
  na transição halt False→True dentro de um ciclo (edge-triggered, comparando
  `kill_switch.is_halted()` no início e no fim do ciclo) — nunca em todos os ciclos enquanto já
  halted.
- **Decisão do dono: o loop continua a correr enquanto halted.** Continua a consumir bars, a
  tentar `reconcile()`, a registar ciclos — só `submit_order()` é rejeitado, barato, pelo
  `RiskGate`, sempre. Um processo que sai ao ficar halted é indistinguível de um crash para quem
  está a monitorizar; "vivo, halted, à espera de um humano" nos logs é o estado observável certo
  e bate com o critério de sucesso do CLAUDE.md ("saber QUANDO parte").
- **`bot/orchestration/`**: `runner.py` (`LiveRunner`, `RunnerConfig`), `run_log.py`
  (`record_cycle`), `alerts.py` (`AlertSink`, `LogAlertSink`). `scripts/run_live.py` novo —
  mesmos defaults do `run_backtest.py` (BTC/USDT, 1h, binance, MA crossover 20/50): continua só a
  provar o motor, não uma alegação de edge.
- **38/38 testes a passar**, incluindo os 4 pedidos especificamente isolados: falha de ciclo a
  saltar o bar sem submeter ordem e mesmo assim registada em `run_log`
  (`test_cycle_failure_skips_bar_no_order_submitted_but_still_logged`), restart simulado a
  retomar de estado durável sem ordem duplicada — testado tanto pela deteção de posição correta
  (sem sequer tentar reenviar) como pelo caso pior direto via dedupe de `client_order_id`
  (`test_restart_resumes_from_durable_state_no_duplicate_order`), e ciclo preso a atingir o
  timeout com o loop a avançar (`test_hung_cycle_hits_timeout_and_loop_moves_on`). Testes de
  orquestração recorridos 5x isolados para excluir flakiness relacionada com timing — estáveis.
  Testes usam doubles (`ScriptedStrategy`, `FakeDataSource`) que satisfazem os Protocols
  `Strategy`/`MarketDataSource` em vez de `MACrossoverStrategy`/`CcxtDataSource` reais — teste mais
  honesto do desacoplamento do que importar uma implementação concreta.
- Strategy e o motor de backtest continuam sem qualquer import de `bot.orchestration` — e
  vice-versa, `bot.orchestration` nunca importa `bot.backtest`.
- **Não construído (por desenho):** o dashboard Next.js em si (só a fonte de dados, `run_log` +
  tudo o resto), entrega real de alertas (Slack/email/PagerDuty), correção da corrida de thread
  presa (fica para `LiveBroker`).

### Milestone 6 — artefactos construídos (2026-07-22), execução real pendente
Diferente dos milestones 0–5: isto não pode ser marcado FEITO da mesma forma, porque o critério de
sucesso real ("sobrevive semanas sem intervenção") só se prova no servidor real, ao longo do
tempo, fora do alcance desta conversa — não é algo que um `pytest` ou uma verificação minha possa
confirmar. O que existe agora: todos os ficheiros de deploy prontos e commitados; os passos no
servidor (secção "Comandos... correstes no servidor" do `DEPLOY.md`) ficam por conta do dono.
- **Docker Compose, dois serviços** (`Dockerfile`, `docker-compose.yml`, `docker/entrypoint.sh`):
  `db` (postgres:16, volume nomeado `pgdata`) + `bot` (build local, corre `migrate.py` depois
  `run_live.py` via `exec` no entrypoint para receber SIGTERM diretamente). **Nenhum dos dois
  publica portas para o host** — `db` só é alcançável pelo `bot` pela rede interna do Compose, o
  que também evita de raiz o problema conhecido de o Docker contornar regras do `ufw` em portas
  publicadas (não há portas publicadas, logo não há nada para contornar). `PYTHONUNBUFFERED=1` no
  Dockerfile — sem isto, `docker logs` podia mostrar output atrasado ou nada, por buffering do
  Python quando não há TTY. Container do bot corre como utilizador não-root (`botuser`).
- **`restart: unless-stopped` + `systemctl enable docker`** cobre crash de processo E reboot do
  servidor sem intervenção manual — `unless-stopped` (não `always`) respeita uma paragem
  deliberada (`docker compose stop`), só não reinicia sozinho nesse caso específico. Nenhum
  systemd unit extra à volta do `docker compose up` — redundante dado que o daemon Docker mais a
  política de restart já cobre os dois casos.
- **Halt durável sobrevive sem código novo.** `risk_events` vive no volume `pgdata`, que não é
  tocado por crash de container, reboot da VM, ou `docker compose up -d --build` — só
  `docker compose down -v` apaga volumes (aviso explícito no `DEPLOY.md`: nunca correr isto neste
  projeto). Mesma garantia já provada ao nível de teste no milestone 4
  (`test_durable_halt_survives_restart_and_only_clears_via_clear_halt`), agora sob infraestrutura
  real em vez de um laptop.
- **Segredos**: `.env` do servidor gerado diretamente no servidor via SSH (nunca no laptop, nunca
  em trânsito como ficheiro) — só `POSTGRES_PASSWORD`; `docker-compose.yml` interpola-o em ambos
  os serviços e constrói `DATABASE_URL` a apontar para o hostname interno `db`, não `localhost`
  (diferente do `.env` local — daí `.env.prod.example` separado do `.env.example` existente).
  Zero mudanças a `bot/persistence/db.py` — continua só a ler `os.environ["DATABASE_URL"]`.
- **Hardening**: só chave SSH (password auth e root login desligados), utilizador sudo não-root,
  duas camadas de firewall (Hetzner Cloud Firewall na consola web + `ufw` no host — nenhuma
  sozinha seria suficiente, juntas cobrem "bloqueado antes de chegar à VM" e "bloqueado no host"),
  `unattended-upgrades` para patches automáticos, `fail2ban` contra tentativas SSH repetidas.
  Passos manuais no servidor, documentados no `DEPLOY.md`, não código.
- **Backup adicionado depois da primeira proposta de design** — pedido explícito do dono: a
  primeira versão do design tinha isto como item futuro adiado; o dono corrigiu que "semanas de
  sobrevivência" é exatamente o que se perde se o servidor morrer à semana 3 sem backup, então o
  ledger/run_log/reconciliação (a própria evidência que o milestone existe para produzir)
  desaparecia com ele. `docker/backup.sh`: `pg_dump` diário via cron do host (não um serviço
  Compose extra) para `~/trading-bot-backups/`, rotação simples (últimos 7). Cobre
  crash/corrupção/erro humano — **não** cobre perda total do disco/servidor, que precisaria de
  cópia off-site, deixado deliberadamente como item futuro (documentado, não escondido).
- **Smoke test de conectividade promovido a passo explícito do runbook** — segundo pedido do dono:
  a proposta original mencionava o risco de a Binance bloquear IPs de cloud providers como nota de
  rodapé; passou a passo 7 do `DEPLOY.md`, correstes imediatamente a seguir ao `docker compose up`,
  antes de confiar em mais nada. Testa REST (`fetch_history`) e WebSocket (`watch_ohlcv` direto,
  sem esperar por um fecho de bar real — que podia demorar até uma hora) separadamente. Se
  bloqueado, o fallback já estava planeado (Kraken, MiCA) — o ponto é descobrir isso no minuto um.
- **`DEPLOY.md`**: runbook completo, passo a passo, com separação explícita entre "ficheiros deste
  repo" e "comandos correstes no servidor". Cobre: criação do servidor, hardening, Docker, clone +
  `.env`, subida do stack, smoke test, verificação, backups, observabilidade remota (logs,
  queries a `run_log`/`risk_events`/`reconciliation_checks`, `clear_halt.py` via `docker compose
  exec`), redeploy, recuperação total do zero, e a lista explícita do que fica fora de âmbito.
- **Nenhuma mudança a lógica do bot** — só empacotamento. `bot/`, `scripts/run_live.py` intocados.

## TODO imediato
- [ ] Milestone 6 (continuação): dono corre o runbook (`DEPLOY.md`) no servidor real — criação,
      hardening, deploy, smoke test, backups agendados. Confirmar de volta para marcar o roadmap
      em `CLAUDE.md` como feito; até lá o checkbox fica por marcar porque "sobrevive semanas" não é
      algo que eu consiga verificar a partir daqui.
- [ ] (Dívida técnica) Corrida de thread presa não-defendida em `LiveRunner` — ver nota no
      milestone 5. Resolver a sério só faz sentido com `LiveBroker`.
- [ ] (Dívida técnica) `REVOKE UPDATE, DELETE ... FROM app_role` quando existir um role de
      aplicação não-superuser — ver nota no milestone 3.
- [ ] (Dívida técnica, deliberada) Backup off-site — só local no servidor por agora, ver nota no
      milestone 6.
- [ ] (Futuro, pré-requisito do gate) Split out-of-sample / walk-forward no backtester.
- [ ] (Futuro) Avaliar Kraken (MiCA) como venue de dados/execução em alternativa à Binance.
