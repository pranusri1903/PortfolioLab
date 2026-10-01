"use client";
import useSWR from "swr";
import { useSession } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(message: string, public status: number, public details?: unknown) {
    super(message);
  }
}

export function useApi() {
  const { getToken } = useSession();
  return async (path: string, init: RequestInit = {}) => {
    const headers = new Headers(init.headers);
    headers.set("Authorization", `Bearer ${await getToken()}`);
    if (typeof init.body === "string") headers.set("Content-Type", "application/json");
    const res = await fetch(API + path, { ...init, headers });
    if (!res.ok) {
      const e = (await res.json().catch(() => null))?.error;
      throw new ApiError(e?.message ?? res.statusText, res.status, e?.details);
    }
    if (res.status === 204) return null;
    return res.headers.get("content-type")?.includes("json") ? res.json() : res.text();
  };
}

export function useData<T>(path: string | null) {
  return useSWR<T>(path, useApi());
}

export const base = (pid: string) => `/api/v1/portfolios/${pid}`;
