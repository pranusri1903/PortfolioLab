export type Metric = { value: number | null; reason: string | null };
export type Metrics = Record<"cumulative_return" | "annualized_volatility" | "sharpe_ratio" | "max_drawdown" | "benchmark_cumulative_return", Metric>;
export type Portfolio = { id: string; name: string; is_demo: boolean; base_currency: "USD" | "INR" };
export type Summary = {
  as_of: string | null; is_sample_data: boolean; value_complete: boolean; unavailable_symbols: string[];
  total_value: string; market_value: string; cash_balance: string; net_contributions: string;
  total_gain_loss: string; total_gain_loss_pct: number | null;
  realized_gain_loss: string; dividend_income: string; fees_paid: string; transaction_count: number; period_return: Metric; metrics: Metrics;
};
export type Performance = {
  start_date: string | null; end_date: string | null; partial: boolean; benchmark_symbol: string;
  series: { date: string; total_value: string; portfolio_index: number; benchmark_index: number | null }[];
  metrics: Metrics; risk_free_rate: number; assumptions: string[];
};
export type Holding = {
  symbol: string; name: string; asset_type: string; quantity: string; average_cost: string; cost_basis: string;
  latest_price: string | null; price_date: string | null; price_status: "ok" | "stale" | "unavailable";
  market_value: string | null; unrealized_gain_loss: string | null; unrealized_gain_loss_pct: number | null; weight: number | null;
};
export type Holdings = { as_of: string | null; is_sample_data: boolean; value_complete: boolean; unavailable_symbols: string[]; holdings: Holding[] };
export type Slice = { key: string; label: string; value: string; weight: number };
export type Allocation = { by_holding: Slice[]; by_asset_type: Slice[] };
export type Tx = {
  id: string; trade_date: string; type: string; symbol: string | null; asset_name: string | null;
  quantity: string | null; price: string | null; fee: string; cash_amount: string | null; notes: string | null;
};
export type TxPage = { items: Tx[]; total: number; page: number; page_size: number };
export type HoldingDetail = {
  holding: Holding | null; symbol: string; name: string; is_sample_data: boolean; price_source: string | null;
  position_history: { date: string; quantity: string; cost_basis: string }[];
  price_history: { date: string; close: string }[]; transactions: Tx[];
};
export type ImportRow = {
  row_number: number; status: "valid" | "invalid" | "duplicate"; reasons: string[]; data: Record<string, string | null>;
  resolved_symbol: string | null; resolved_name: string | null; will_add_asset: boolean;
};
export type FoundTable = { index: number; sheet: string; title: string; header_row: number; columns: string[]; row_count: number };
export type Inspect = {
  tables: FoundTable[]; selected: number | null; columns: string[]; sample: Record<string, string>[]; row_count: number; header_row: number;
};
export type ImportResult = {
  committed: boolean; total_rows: number; valid: number; invalid: number; duplicate: number; rows: ImportRow[];
  result: { imported: number; skipped: number; rejected: number } | null;
};
export type Asset = { symbol: string; name: string; asset_type: string; currency: string; exchange: string | null };
export type MonthlyReturns = { is_sample_data: boolean; months: { month: string; portfolio: number | null; benchmark: number | null }[] };
export type SearchResult = { symbol: string; name: string; asset_type: string; currency: string; exchange: string | null; in_db: boolean; sample: boolean };
export type HoldingAnalytics = {
  symbol: string; name: string; asset_type: string; open: boolean; quantity: string; total_invested: string;
  current_value: string | null; unrealized_gain_loss: string | null; realized_gain_loss: string; dividends: string;
  total_return: string | null; total_return_pct: number | null; xirr: number | null; first_buy: string | null;
  holding_days: number | null; weight: number | null; share_of_profit: number | null; volatility_1y: number | null;
  max_drawdown_1y: number | null; return_1y: number | null; high_52w: string | null; low_52w: string | null; pct_from_high: number | null;
};
export type Analytics = {
  currency: string; as_of: string | null; is_sample_data: boolean; portfolio_xirr: Metric; realized_total: string; dividends_total: string;
  holdings: HoldingAnalytics[];
  concentration: { top1: number | null; top3: number | null; hhi: number | null; effective_holdings: number | null };
  by_class: { asset_type: string; value: string; weight: number; total_return: string; count: number }[];
  correlation: { symbols: string[]; matrix: (number | null)[][]; window_days: number };
  drawdown: { date: string; drawdown: number }[];
};
export type Sip = {
  id: string; symbol: string; name: string; asset_type: string; amount: string; day_of_month: number; start_date: string;
  end_date: string | null; active: boolean; installments: number; invested: string; units: string;
  current_value: string | null; gain_loss: string | null; xirr: number | null; next_date: string | null;
};
