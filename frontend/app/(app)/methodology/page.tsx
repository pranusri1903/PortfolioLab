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
      <h2 id="benchmark" className="font-semibold">Portfolio vs. benchmark chart</h2>
      <p><b>What it shows.</b> Two lines that both start at <b>100</b> on the first day of the selected range. If the portfolio line ends at 112 and the benchmark at 108, the portfolio returned +12% against +8% for the benchmark over that period. The gap is the difference in return.</p>
      <p><b>Portfolio line.</b> A time-weighted return index built from the daily returns above. Deposits, withdrawals and SIP payments are removed, so adding money never looks like a gain, and the line can be compared fairly with an investment that had no cash flows.</p>
      <p><b>Benchmark line.</b> The benchmark&apos;s closing price (or NAV for a fund) on each date, divided by its value on the first day and multiplied by 100. If it has no price on a date, the most recent earlier price is used, never a later one.</p>
      <p><b>Which benchmark.</b></p>
      <ul className="list-disc space-y-1 pl-5">
        <li><b>INR portfolios:</b> the UTI Nifty 50 Index Fund (Direct, Growth), whose NAV tracks the Nifty 50 index. Growth plans reinvest dividends, so this is close to a total-return index, less a small fund fee.</li>
        <li><b>USD portfolios:</b> SPY, the S&amp;P 500 ETF. Its closing price excludes dividends, so it slightly understates the index&apos;s total return.</li>
        <li><b>Demo portfolios:</b> a fictional sample ETF, clearly labelled. It is made up and says nothing about real markets.</li>
        <li>A real portfolio never uses the fictional benchmark. If the real one isn&apos;t loaded yet, the line is simply absent and the benchmark return shows as unavailable.</li>
      </ul>
      <p><b>How to read it, and its limits.</b> A benchmark is a yardstick, not a recommendation. Holding cash makes a portfolio lag in a rising market, and a concentrated or sector portfolio will differ from a broad index simply because it takes different risks, not because it is better or worse managed. Past performance doesn&apos;t predict future results. The benchmark ignores your own taxes and costs, and the comparison is only as accurate as the prices behind it.</p>
    </article>
  );
}
