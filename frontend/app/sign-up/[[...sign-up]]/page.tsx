import { BarChart3, LineChart, ShieldCheck, Upload } from "lucide-react";
import { SignUpForm } from "@/lib/auth";

const FEATURES = [[LineChart, "Track value, returns and risk against a benchmark"], [Upload, "Import transactions from CSV with a safe preview"], [ShieldCheck, "Transparent calculations — no black boxes"]] as const;

export default function SignUpPage() {
  return (
    <main className="grid min-h-screen md:grid-cols-2">
      <section className="hidden flex-col justify-between bg-gradient-to-br from-indigo-600 via-violet-600 to-fuchsia-600 p-12 text-white md:flex">
        <div className="flex items-center gap-2 text-xl font-bold"><BarChart3 />PortfolioLab</div>
        <div className="space-y-6">
          <h1 className="text-4xl font-bold leading-tight">Understand your portfolio,<br />not just its balance.</h1>
          <ul className="space-y-3">{FEATURES.map(([Icon, text]) => <li key={text} className="flex items-center gap-3 text-indigo-50"><Icon size={20} />{text}</li>)}</ul>
        </div>
        <p className="text-xs text-indigo-100">Demo uses synthetic sample data. Not investment advice.</p>
      </section>
      <section className="flex items-center justify-center p-8">
        <div className="w-full max-w-sm space-y-5">
          <h2 className="text-2xl font-bold">Create your account</h2>
          <SignUpForm />
        </div>
      </section>
    </main>
  );
}
