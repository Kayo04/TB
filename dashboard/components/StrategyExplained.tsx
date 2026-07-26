import Panel from "./Panel";

export default function StrategyExplained() {
  return (
    <Panel title="Estratégia explicada">
      <div className="prose">
        <h3>Cruzamento de médias móveis (20/50)</h3>
        <p>
          O bot compara duas médias móveis do preço de fecho: uma <strong>rápida</strong> (últimas
          20 horas) e uma <strong>lenta</strong> (últimas 50 horas).
        </p>
        <ul>
          <li>
            <strong>Golden cross</strong> -- a rápida cruza <em>acima</em> da lenta → o bot compra
            (entra long).
          </li>
          <li>
            <strong>Death cross</strong> -- a rápida cruza <em>abaixo</em> da lenta → o bot vende
            (fecha a posição, fica flat).
          </li>
          <li>Fora destes cruzamentos, mantém a posição atual -- não faz nada.</li>
        </ul>
        <p>Sem venda a descoberto, sem alavancagem: a posição é sempre 0 (flat) ou 1 unidade (long).</p>

        <div className="disclaimer">
          <strong>Isto é um placeholder de engenharia, não uma fonte de vantagem.</strong> Foi
          escolhida por ser simples de implementar e testar -- não porque se espera lucro. Em
          backtest out-of-sample, com custos (fees + slippage), <strong>não bate buy &amp; hold</strong>.
          O valor deste projeto está na engenharia -- fiabilidade, idempotência, reconciliação,
          kill-switch -- não no lucro desta estratégia. Nenhuma ordem aqui é real.
        </div>
      </div>
    </Panel>
  );
}
