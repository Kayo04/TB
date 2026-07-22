# Trading Bot — Contexto do Projeto (CLAUDE.md)

## Objetivo (lê com atenção — é fácil de perceber mal)
Construir um trading bot **100% autónomo** que corre 24/7 sem intervenção.
O objetivo é de **engenharia e aprendizagem** — fiabilidade de sistemas, distributed
systems, um serviço long-running robusto. **Não** é de rendimento. Portefólio > lucro.

**"Está a funcionar" NÃO significa "deu dinheiro".** Lucro de amostra pequena é ruído:
podes ser lucrativo por sorte com uma estratégia de esperança matemática negativa.
"A funcionar" = corre sozinho de forma fiável, não crasha, não duplica ordens, e o
comportamento ao vivo bate certo com o backtest. Mede-se com **uptime, logs e
reconciliação** — nunca com o saldo.

## Não-objetivos / anti-padrões (NÃO violar)
- **NUNCA pôr o LLM no loop de decisão em tempo real.** É lento, caro, não-determinístico
  e alucina. A estratégia é **código determinístico**. O LLM ajuda a construir e testar,
  e no máximo faz reflexão *offline* sobre o ledger.
- **NUNCA dinheiro real** até uma estratégia passar backtest out-of-sample E semanas de
  paper trading estáveis. Default = **paper**.
- **NUNCA automatizar** uma estratégia que não bata buy & hold out-of-sample no
  backtester, após custos. (Ver Gates.)
- Estratégias "populares" copiadas (MA crossover simples incluído) servem só para provar
  o motor, **não** como fonte de edge.

## Stack (decisões fechadas)
- **Linguagem:** Python. (Melhor ecossistema de trading/backtesting; alinhado com o spike AI/ML.)
- **Mercado:** Crypto (24/7 real). Motor **agnóstico ao mercado** — trocar para ações/ETFs
  deve ser trocar um *adapter*, não reescrever.
- **Dados/execução crypto:** `ccxt` (acesso agnóstico a exchanges; histórico público sem API key).
- **Persistência:** PostgreSQL (o dono já domina Postgres) via SQLAlchemy ou psycopg.
- **Deploy alvo:** VPS (processo long-running). **NÃO** Vercel/serverless — não corre processos persistentes.

## Arquitetura (camadas desacopladas)
1. **Dados** — histórico (backtest) + ao vivo (websocket).
2. **Estratégia** — sinais determinísticos, testável isoladamente, sem tocar na corretora.
3. **Execução** — ordens via adapter (paper primeiro). **Idempotente**: reinício a meio de
   uma ordem nunca pode duplicá-la (usar client order IDs).
4. **Estado/persistência** — ledger, posições, ordens em Postgres. Fonte de verdade,
   reconciliável com a corretora.
5. **Risco** — position sizing, limites (max posição, max drawdown diário) e **kill-switch**.
6. **Orquestração** — loop 24/7 / event-driven, com recuperação de crash (retoma estado da BD, não da memória).
7. **Observabilidade** — logs estruturados + alertas (saber QUANDO parte; vai partir).

## Roadmap (atualizar sempre em PROGRESS.md)
- [x] **0** — Backtester honesto (sem look-ahead, com custos). Ver `backtester.py`.
- [ ] **1** — Interface `Strategy` + camada de dados ao vivo.
- [ ] **2** — Execução em paper com idempotência.
- [ ] **3** — Persistência Postgres (ledger/posições/ordens) + reconciliação.
- [ ] **4** — Risk layer + kill-switch.
- [ ] **5** — Loop autónomo 24/7 + observabilidade.
- [ ] **6** — Deploy VPS; correr semanas em paper. Sucesso = uptime + reconciliação, não P&L.

## Gates (bloqueiam avanço)
- **Gate estratégia:** nada entra em execução sem bater buy & hold **out-of-sample** no
  backtester, após custos.
- **Gate dinheiro real:** só após gate estratégia + N semanas de paper estável + kill-switch
  testado. Verificar também disponibilidade da corretora para residentes em **Portugal**.

## Convenções de código
- Determinístico e testável. Estratégia e execução separadas.
- Sem look-ahead nos backtests (posição decidida em t entra em vigor em t+1).
- Custos (fees + slippage) sempre incluídos em qualquer simulação; buy & hold sempre como benchmark.
- Segredos via `.env` / variáveis de ambiente, **nunca** no repo.
- Testes para a lógica de estratégia e para a idempotência de execução.
- CLI/terminal-first, eficiente em tokens.

## Estilo de trabalho (preferência do dono)
Direto e honesto, não concordar por concordar. Desafiar pressupostos fracos; se algo está
errado, dizer "estás errado" e explicar. Avaliar ideias de 0–10. Se incerto, dizer que é
incerto em vez de adivinhar com confiança.

## Começar aqui
1. Lê `PROGRESS.md` para o estado atual.
2. Confirma o milestone 0: corre `backtester.py` com dados reais (ccxt) e regista os números em PROGRESS.md.
3. Arranca o milestone 1: propõe a estrutura de pastas e a interface `Strategy` **antes** de escrever muito código.
