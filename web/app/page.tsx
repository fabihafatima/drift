"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Radar } from "lucide-react";
import { api, setToken } from "@/lib/api";

type DemoUser = { id: string; name: string; email: string; role: string; org_name: string };

export default function Login() {
  const router = useRouter();
  const [users, setUsers] = useState<DemoUser[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    const load = () =>
      api<DemoUser[]>("/api/demo-users").then(
        (u) => {
          setUsers(u);
          setError(null);
        },
        () => {
          setError("Can't reach the Drift API on :8000. Retrying…");
          timer = setTimeout(load, 2000);
        },
      );
    load();
    return () => clearTimeout(timer);
  }, []);

  async function signIn(id: string) {
    const { token } = await api<{ token: string }>("/api/login", { json: { user_id: id } });
    setToken(token);
    router.push("/ask");
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-6">
      <div className="w-full max-w-md">
        <div className="mb-10 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-400/10 ring-1 ring-emerald-400/30">
            <Radar className="h-5 w-5 text-emerald-300" />
          </div>
          <div>
            <div className="text-lg font-semibold tracking-tight text-white">Drift</div>
            <div className="text-sm text-zinc-400">The Company Brain that notices when it is wrong.</div>
          </div>
        </div>

        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-2">
          <div className="px-3 pb-2 pt-3 text-xs font-medium uppercase tracking-wider text-zinc-500">
            Sign in as a demo user
          </div>
          {error && <div className="px-3 py-4 text-sm text-rose-300">{error}</div>}
          {users.map((u) => (
            <button
              key={u.id}
              onClick={() => signIn(u.id)}
              className="group flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left transition hover:bg-white/[0.04]"
            >
              <div className="flex h-9 w-9 items-center justify-center rounded-full bg-zinc-800 text-sm font-medium text-zinc-200">
                {u.name[0]}
              </div>
              <div className="flex-1">
                <div className="text-sm font-medium text-zinc-100">{u.name}</div>
                <div className="text-xs text-zinc-500">
                  {u.org_name} · {u.role.toLowerCase()}
                </div>
              </div>
              <ArrowRight className="h-4 w-4 text-zinc-600 transition group-hover:translate-x-0.5 group-hover:text-zinc-300" />
            </button>
          ))}
        </div>
        <p className="mt-6 text-center text-xs text-zinc-600">
          Live verification powered by TriggerWare · synthetic demo company
        </p>
      </div>
    </main>
  );
}
