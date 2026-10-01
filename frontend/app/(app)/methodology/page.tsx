export default function Methodology() {
  return (
    <article className="prose max-w-2xl space-y-3 text-sm">
      <h1 className="text-2xl font-semibold">Methodology</h1>
      <p>All figures are analytics on user-entered transactions and <strong>synthetic sample prices</strong>. This is not investment advice, tax accounting, or brokerage-reported performance.</p>
      <h2 className="font-semibold">Portfolio value</h2>
      <p>Cash balance + Σ(quantity × latest closing price). A missing or stale price is flagged, never treated as zero.</p>
      <h2 className="font-semibold">Cost basis</h2>
      <p>Weighted average. A buy adds quantity × price + fee; a sell removes cost in proportion to the quantity sold. Dividends affect cash only.</p>
      <h2 className="font-semibold">Returns</h2>
      <p>Daily return = (ending value − external cash flow) ÷ previous ending value − 1. Deposits and withdrawals are assumed to occur at the end of the day, so they are not counted as return. The first day of a window has no return, and days following a zero value are excluded. Cumulative return compounds daily returns.</p>
      <h2 className="font-semibold">Risk metrics</h2>
      <p>Volatility = stdev(daily returns) × √252. Sharpe = mean(excess daily return) ÷ stdev(excess daily return) × √252 with a 2% annual risk-free rate. Max drawdown = largest peak-to-trough decline of the compounded return index. Risk metrics need at least 20 daily returns and are hidden otherwise.</p>
      <h2 className="font-semibold">Benchmark</h2>
      <p>A sample broad-market ETF (BNCH) rebased to 100 at the start of the selected window.</p>
    </article>
  );
}
