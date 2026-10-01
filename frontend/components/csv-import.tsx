"use client";
import { useState } from "react";
import { useSWRConfig } from "swr";
import { ErrorBox } from "@/components/ui";
import { base, useApi } from "@/lib/api";
import type { ImportResult } from "@/lib/types";

const COLOR = { valid: "text-emerald-700", invalid: "text-red-700", duplicate: "text-amber-700" };

export function CsvImport({ pid, onClose }: { pid: string; onClose: () => void }) {
  const api = useApi();
  const { mutate } = useSWRConfig();
  const [file, setFile] = useState<File>();
  const [res, setRes] = useState<ImportResult>();
  const [error, setError] = useState<Error>();

  async function run(commit: boolean) {
    setError(undefined);
    const body = new FormData();
    body.set("file", file!);
    try {
      setRes(await api(`${base(pid)}/transactions/import?commit=${commit}`, { method: "POST", body }));
      if (commit) await mutate(() => true);
    } catch (e) { setError(e as Error); setRes(undefined); }
  }

  return (
    <section className="card space-y-3" aria-label="Import CSV">
      <h2 className="font-semibold">Import transactions from CSV</h2>
      <p className="text-xs text-slate-500">Header: <code>trade_date,type,symbol,quantity,price,fee,cash_amount,notes</code>. Nothing is saved until you confirm the preview.</p>
      <input type="file" accept=".csv,text/csv" aria-label="CSV file" onChange={(e) => { setFile(e.target.files?.[0]); setRes(undefined); }} />
      <button className="btn ml-2" disabled={!file || res?.committed} onClick={() => run(false)}>Preview</button>
      {error && <ErrorBox error={error} />}
      {res && (
        <>
          <p role="status" className="text-sm">
            {res.committed && res.result
              ? `Imported ${res.result.imported}, skipped ${res.result.skipped} duplicates, rejected ${res.result.rejected}.`
              : `${res.valid} valid, ${res.duplicate} duplicate (will be skipped), ${res.invalid} invalid (will be rejected).`}
          </p>
          <div className="max-h-64 overflow-auto">
            <table className="w-full"><thead><tr><th className="th">Row</th><th className="th">Status</th><th className="th">Details</th></tr></thead>
              <tbody>{res.rows.map((r) => (
                <tr key={r.row_number} className="row"><td className="td">{r.row_number}</td><td className={`td font-medium ${COLOR[r.status]}`}>{r.status}</td>
                  <td className="td">{r.reasons.join("; ") || `${r.data.type} ${r.data.symbol ?? ""} ${r.data.trade_date}`}</td></tr>))}</tbody></table>
          </div>
        </>
      )}
      <div className="flex gap-2">
        {res && !res.committed && <button className="btn-primary" disabled={res.valid === 0} onClick={() => run(true)}>Confirm import of {res.valid} rows</button>}
        <button className="btn" onClick={onClose}>{res?.committed ? "Done" : "Cancel"}</button>
      </div>
    </section>
  );
}
