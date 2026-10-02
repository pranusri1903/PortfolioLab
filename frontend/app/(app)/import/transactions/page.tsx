"use client";
import { usePid } from "../../layout";
import { ImportWizard } from "@/components/import-wizard";
import { PageTitle } from "@/components/ui";

export default function ImportTransactions() {
  return (
    <div className="space-y-5">
      <PageTitle title="Import transactions" sub="Your trade history from a broker or fund house: buys, sells, SIPs, redemptions, dividends. CSV or Excel." />
      <ImportWizard pid={usePid()} kind="transactions" />
    </div>
  );
}
