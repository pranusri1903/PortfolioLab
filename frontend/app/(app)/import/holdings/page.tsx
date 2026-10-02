"use client";
import { usePid } from "../../layout";
import { ImportWizard } from "@/components/import-wizard";
import { PageTitle } from "@/components/ui";

export default function ImportHoldings() {
  return (
    <div className="space-y-5">
      <PageTitle title="Import holdings" sub="A file of what you own today: stocks, ETFs or mutual funds. CSV or Excel." />
      <ImportWizard pid={usePid()} kind="holdings" />
    </div>
  );
}
