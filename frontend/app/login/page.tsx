"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { authApi, getToken, ApiError } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (getToken()) router.replace("/");
  }, [router]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === "signup") {
        await authApi.signup(email.trim(), fullName.trim(), password);
      }
      await authApi.login(email.trim(), password);
      router.replace("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col bg-[#f4f6f9]">
      <div className="flex h-1.5">
        <div className="flex-1 bg-[#e87722]" />
        <div className="flex-1 bg-white" />
        <div className="flex-1 bg-[#1a7a3c]" />
      </div>
      <div className="flex flex-1 items-center justify-center px-4 py-10">
        <div className="w-full max-w-md">
          <div className="mb-8 text-center">
            <span className="mx-auto mb-4 flex h-14 w-14 items-center justify-center border-2 border-[#e87722] bg-[#0f2a52] font-serif text-2xl font-bold text-white">
              N
            </span>
            <h1 className="font-serif text-3xl font-bold tracking-wide text-[#0f2a52]">NIRIKSH</h1>
            <p className="mt-1 text-sm uppercase tracking-widest text-slate-500">
              Legal Metrology Compliance System
            </p>
            <p className="mx-auto mt-3 max-w-sm text-xs leading-relaxed text-slate-500">
              Enforcement support platform for the Legal Metrology (Packaged Commodities) Rules, 2011
            </p>
          </div>

          <div className="border border-[#d7dde6] bg-white p-7 shadow-sm">
            <div className="mb-6 grid grid-cols-2 border border-[#d7dde6]">
              {(["login", "signup"] as const).map((m) => (
                <button
                  key={m}
                  onClick={() => {
                    setMode(m);
                    setError(null);
                  }}
                  className={`px-3 py-2 text-sm font-semibold transition ${
                    mode === m
                      ? "bg-[#0f2a52] text-white"
                      : "bg-white text-slate-600 hover:bg-[#f4f6f9]"
                  }`}
                >
                  {m === "login" ? "Sign in" : "Create account"}
                </button>
              ))}
            </div>

            <form onSubmit={submit} className="space-y-4">
              {mode === "signup" && (
                <div>
                  <label className="mb-1.5 block text-sm font-semibold text-[#0f2a52]">Full name</label>
                  <input
                    required
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    className="w-full border border-[#c9d1de] px-3 py-2 text-sm outline-none focus:border-[#1e4f9c] focus:ring-1 focus:ring-[#1e4f9c]"
                    placeholder="Officer name"
                  />
                </div>
              )}
              <div>
                <label className="mb-1.5 block text-sm font-semibold text-[#0f2a52]">Email</label>
                <input
                  required
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full border border-[#c9d1de] px-3 py-2 text-sm outline-none focus:border-[#1e4f9c] focus:ring-1 focus:ring-[#1e4f9c]"
                  placeholder="officer@example.gov.in"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-sm font-semibold text-[#0f2a52]">Password</label>
                <input
                  required
                  type="password"
                  minLength={8}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full border border-[#c9d1de] px-3 py-2 text-sm outline-none focus:border-[#1e4f9c] focus:ring-1 focus:ring-[#1e4f9c]"
                  placeholder="••••••••"
                />
              </div>

              {error && (
                <p className="border border-[#a02c2c]/30 bg-[#fbeaea] px-3 py-2 text-sm text-[#a02c2c]">
                  {error}
                </p>
              )}

              <button
                type="submit"
                disabled={busy}
                className="w-full bg-[#0f2a52] px-4 py-2.5 text-sm font-semibold uppercase tracking-wide text-white transition hover:bg-[#12294a] disabled:opacity-50"
              >
                {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account & sign in"}
              </button>
            </form>
          </div>
          <p className="mt-4 text-center text-xs text-slate-500">
            The first registered account becomes the system administrator
          </p>
        </div>
      </div>
    </div>
  );
}
