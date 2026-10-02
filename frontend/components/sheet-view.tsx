"use client";
import { useState } from "react";
import { Seg } from "@/components/ui";
import type { Inspect } from "@/lib/types";

type Props = { info: Inspect; onPickTable: (index: number) => void; onPickHeader: (row: number) => void };

/** The uploaded file as a spreadsheet, with the tables we found outlined. Click a table to import it,
 *  or a row number to say "the column names are on this row". Personal identifiers arrive already masked. */
export function SheetView({ info, onPickTable, onPickHeader }: Props) {
  const firstWithTable = Math.max(0, info.sheets.findIndex((s) => s.name === info.chosen.sheet));
  const [active, setActive] = useState(firstWithTable);
  const sheet = info.sheets[Math.min(active, info.sheets.length - 1)];
  const tables = info.tables.filter((t) => t.sheet === sheet.name);
  const cols = Array.from({ length: sheet.columns }, (_, i) => i);
  const inChosen = (r: number) => sheet.name === info.chosen.sheet && r >= info.chosen.header_row && r <= info.chosen.end_row;

  return (
    <div className="space-y-2">
      {info.sheets.length > 1 && <Seg label="Sheet" opts={info.sheets.map((s, i) => [String(i), s.name || `Sheet ${i + 1}`])} value={String(active)} set={(v) => setActive(Number(v))} />}
      <div className="flex flex-wrap gap-3 text-xs text-slate-500">
        <span className="inline-flex items-center gap-1"><i className="size-3 rounded bg-indigo-200" />Table being imported</span>
        <span className="inline-flex items-center gap-1"><i className="size-3 rounded bg-slate-200 dark:bg-slate-700" />Other tables found (click to switch)</span>
        <span>Click a row number to use that row as the column names.</span>
      </div>
      <div className="max-h-80 overflow-auto rounded-xl border border-slate-200 dark:border-slate-700">
        <table className="w-full border-collapse text-xs">
          <caption className="sr-only">Your file, with detected tables highlighted</caption>
          <tbody>
            {sheet.rows.map((row, i) => {
              const r = i + 1;
              const region = tables.find((t) => r >= t.header_row && r <= t.end_row);
              const chosen = inChosen(r);
              const isHeader = !!region && r === region.header_row;
              const shade = chosen ? (r === info.chosen.header_row ? "bg-indigo-200/80 font-semibold dark:bg-indigo-500/40" : "bg-indigo-100/70 dark:bg-indigo-500/15")
                : region ? (isHeader ? "bg-slate-200 font-semibold dark:bg-slate-700" : "bg-slate-100 dark:bg-slate-800/60") : "";
              return (
                <tr key={r} className={shade} onClick={() => region && !chosen && onPickTable(region.index)} style={{ cursor: region && !chosen ? "pointer" : undefined }}>
                  <th scope="row" className="sticky left-0 w-10 border-r border-slate-200 bg-slate-50 p-0 text-right font-normal text-slate-400 dark:border-slate-700 dark:bg-slate-900">
                    <button type="button" title={`Use row ${r} as the column names`} aria-label={`Use row ${r} as the column names`} className="w-full px-2 py-1 hover:bg-indigo-100 hover:text-indigo-700 dark:hover:bg-indigo-500/20"
                      onClick={(e) => { e.stopPropagation(); onPickHeader(r); }}>{r}</button>
                  </th>
                  {cols.map((c) => <td key={c} className="max-w-44 truncate whitespace-nowrap px-2 py-1" title={row[c]}>{row[c] ?? ""}</td>)}
                </tr>);
            })}
          </tbody>
        </table>
      </div>
      {sheet.total_rows > sheet.rows.length && <p className="text-xs text-slate-500">Showing the first {sheet.rows.length} of {sheet.total_rows} rows.</p>}
    </div>
  );
}
