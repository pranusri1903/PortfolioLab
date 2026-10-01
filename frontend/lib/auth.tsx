"use client";
import { ClerkProvider, useAuth, SignIn } from "@clerk/nextjs";
import { useState, useSyncExternalStore, type ReactNode } from "react";

/** With a Clerk key, Clerk handles sign-in. Without one, a local dev sign-in is used
 *  (the API must run with AUTH_MODE=dev). Never deploy dev mode. */
export const CLERK = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;
const KEY = "pl_dev_user";

function useClerkSession() {
  const { isLoaded, isSignedIn, getToken, signOut } = useAuth();
  return { ready: isLoaded, signedIn: !!isSignedIn, getToken, signOut: () => signOut({ redirectUrl: "/sign-in" }) };
}

function useDevSession() {
  const user = useSyncExternalStore(() => () => {}, () => localStorage.getItem(KEY), () => undefined);
  return {
    ready: user !== undefined,
    signedIn: !!user,
    getToken: async () => `dev:${localStorage.getItem(KEY)}`,
    signOut: () => { localStorage.removeItem(KEY); location.href = "/sign-in"; },
  };
}

export const useSession = CLERK ? useClerkSession : useDevSession;

export function AuthProvider({ children }: { children: ReactNode }) {
  return CLERK ? <ClerkProvider>{children}</ClerkProvider> : <>{children}</>;
}

export function SignInForm() {
  const [id, setId] = useState("demo_user");
  if (CLERK) return <SignIn forceRedirectUrl="/dashboard" />;
  return (
    <form
      className="space-y-3"
      onSubmit={(e) => { e.preventDefault(); localStorage.setItem(KEY, id.trim()); location.href = "/dashboard"; }}
    >
      <p className="text-sm text-slate-600">
        Local development sign-in (Clerk is not configured). Each user ID gets its own private portfolio.
      </p>
      <label className="block text-sm font-medium">
        User ID
        <input className="input mt-1 w-full" value={id} onChange={(e) => setId(e.target.value)} required />
      </label>
      <button className="btn-primary w-full">Sign in</button>
    </form>
  );
}
