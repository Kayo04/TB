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

## TODO imediato
- [ ] Milestone 1: interface `Strategy` + camada de dados (histórico paginado + live) — design
      aprovado pelo dono, a construir a seguir.
- [ ] (Futuro, pré-requisito do gate) Paginação `since` no fetch histórico.
- [ ] (Futuro, pré-requisito do gate) Split out-of-sample / walk-forward no backtester.
