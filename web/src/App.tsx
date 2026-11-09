import { useEffect, useMemo, useState } from "react";

type PRItem = { id: number; owner: string; repo: string; number: number };

type Finding = {
  id: number;
  file_path: string;
  line_start: number;
  line_end: number;
  severity: string;
  category: string;
  title: string;
  explanation: string;
  confidence: number;
  agent_name: string;
  feedback: string | null;
};

type Run = {
  id: number;
  head_sha: string;
  prompt_tokens: number;
  completion_tokens: number;
  agent_latency_ms: Record<string, number> | null;
  findings: Finding[];
};

type PRDetail = PRItem & { runs: Run[] };

const SEVERITIES = ["all", "critical", "high", "medium", "low"] as const;

export default function App() {
  const [theme, setTheme] = useState<"light" | "dark">(() =>
    window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light",
  );
  const [prs, setPrs] = useState<PRItem[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<PRDetail | null>(null);
  const [severity, setSeverity] = useState<(typeof SEVERITIES)[number]>("all");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [theme]);

  useEffect(() => {
    void (async () => {
      try {
        const res = await fetch("/api/prs");
        if (!res.ok) throw new Error(`Failed to load PRs (${res.status})`);
        const data = (await res.json()) as PRItem[];
        setPrs(data);
        if (data.length && selectedId === null) setSelectedId(data[0].id);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load");
      }
    })();
  }, []);

  useEffect(() => {
    if (selectedId == null) return;
    void (async () => {
      setLoading(true);
      setError(null);
      try {
        const q = severity === "all" ? "" : `?severity=${severity}`;
        const res = await fetch(`/api/prs/${selectedId}${q}`);
        if (!res.ok) throw new Error(`Failed to load PR (${res.status})`);
        setDetail((await res.json()) as PRDetail);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load PR");
      } finally {
        setLoading(false);
      }
    })();
  }, [selectedId, severity]);

  const latest = detail?.runs[0];
  const latencyEntries = useMemo(
    () => Object.entries(latest?.agent_latency_ms ?? {}),
    [latest],
  );

  async function feedback(findingId: number, action: "accept" | "dismiss") {
    const res = await fetch("/api/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ finding_id: findingId, action }),
    });
    if (!res.ok) {
      setError("Feedback failed");
      return;
    }
    if (selectedId != null) {
      const q = severity === "all" ? "" : `?severity=${severity}`;
      const refreshed = await fetch(`/api/prs/${selectedId}${q}`);
      setDetail((await refreshed.json()) as PRDetail);
    }
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-6xl flex-col gap-6 px-4 py-8 md:px-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="mono text-sm tracking-[0.18em] text-[var(--accent)] uppercase">
            ReviewPilot
          </p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight md:text-4xl">
            Pull request reviews
          </h1>
          <p className="mt-2 max-w-xl text-[var(--muted)]">
            Findings from security, performance, correctness, and style agents —
            filtered, ranked, and ready for feedback.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <a
            className="rounded-md border border-[var(--line)] bg-[var(--bg-elevated)] px-3 py-2 text-sm"
            href="/api/export/findings.csv"
          >
            Export CSV
          </a>
          <button
            type="button"
            className="rounded-md border border-[var(--line)] bg-[var(--bg-elevated)] px-3 py-2 text-sm"
            onClick={() => setTheme((t) => (t === "light" ? "dark" : "light"))}
          >
            {theme === "light" ? "Dark" : "Light"} theme
          </button>
        </div>
      </header>

      {error && (
        <div className="rounded-md border border-[var(--danger)] bg-[var(--bg-elevated)] px-4 py-3 text-sm text-[var(--danger)]">
          {error}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[240px_1fr]">
        <aside className="rounded-xl border border-[var(--line)] bg-[var(--bg-elevated)] p-3">
          <h2 className="px-2 pb-2 text-xs font-medium tracking-wide text-[var(--muted)] uppercase">
            Pull requests
          </h2>
          <ul className="space-y-1">
            {prs.length === 0 && (
              <li className="px-2 py-3 text-sm text-[var(--muted)]">No reviews yet.</li>
            )}
            {prs.map((pr) => (
              <li key={pr.id}>
                <button
                  type="button"
                  onClick={() => setSelectedId(pr.id)}
                  className={`w-full rounded-lg px-3 py-2 text-left text-sm transition ${
                    selectedId === pr.id
                      ? "bg-[var(--accent-soft)] text-[var(--accent)]"
                      : "hover:bg-[color-mix(in_oklab,var(--bg)_70%,var(--accent-soft))]"
                  }`}
                >
                  <span className="font-medium">
                    {pr.owner}/{pr.repo}
                  </span>
                  <span className="mono ml-2 text-[var(--muted)]">#{pr.number}</span>
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <main className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            {SEVERITIES.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setSeverity(s)}
                className={`rounded-md px-3 py-1.5 text-sm ${
                  severity === s
                    ? "bg-[var(--accent)] text-white"
                    : "border border-[var(--line)] bg-[var(--bg-elevated)]"
                }`}
              >
                {s}
              </button>
            ))}
          </div>

          {loading && <p className="text-sm text-[var(--muted)]">Loading…</p>}

          {latest && (
            <section className="grid gap-4 md:grid-cols-2">
              <div className="rounded-xl border border-[var(--line)] bg-[var(--bg-elevated)] p-4">
                <h3 className="text-sm text-[var(--muted)]">Token cost</h3>
                <p className="mono mt-2 text-2xl font-medium">
                  {latest.prompt_tokens + latest.completion_tokens}
                </p>
                <p className="mt-1 text-sm text-[var(--muted)]">
                  prompt {latest.prompt_tokens} · completion {latest.completion_tokens}
                </p>
              </div>
              <div className="rounded-xl border border-[var(--line)] bg-[var(--bg-elevated)] p-4">
                <h3 className="text-sm text-[var(--muted)]">Agent latency (ms)</h3>
                <ul className="mt-2 space-y-1">
                  {latencyEntries.length === 0 && (
                    <li className="text-sm text-[var(--muted)]">No latency data</li>
                  )}
                  {latencyEntries.map(([name, ms]) => (
                    <li key={name} className="flex justify-between text-sm">
                      <span>{name}</span>
                      <span className="mono">{Math.round(ms)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </section>
          )}

          <section className="space-y-3">
            {(latest?.findings ?? []).map((f) => (
              <article
                key={f.id}
                className="rounded-xl border border-[var(--line)] bg-[var(--bg-elevated)] p-4"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-xs tracking-wide text-[var(--muted)] uppercase">
                      {f.severity} · {f.agent_name} · {f.category}
                    </p>
                    <h3 className="mt-1 text-lg font-medium">{f.title}</h3>
                    <p className="mono mt-1 text-sm text-[var(--muted)]">
                      {f.file_path}:{f.line_start}
                      {f.line_end !== f.line_start ? `-${f.line_end}` : ""}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      className="rounded-md bg-[var(--accent)] px-3 py-1.5 text-sm text-white"
                      onClick={() => void feedback(f.id, "accept")}
                    >
                      Accept
                    </button>
                    <button
                      type="button"
                      className="rounded-md border border-[var(--line)] px-3 py-1.5 text-sm"
                      onClick={() => void feedback(f.id, "dismiss")}
                    >
                      Dismiss
                    </button>
                  </div>
                </div>
                <p className="mt-3 text-sm leading-relaxed text-[var(--muted)]">
                  {f.explanation}
                </p>
                {f.feedback && (
                  <p className="mt-2 text-xs text-[var(--accent)]">Feedback: {f.feedback}</p>
                )}
              </article>
            ))}
            {latest && latest.findings.length === 0 && (
              <p className="rounded-xl border border-dashed border-[var(--line)] p-6 text-sm text-[var(--muted)]">
                No findings for this filter.
              </p>
            )}
            {!latest && !loading && (
              <p className="rounded-xl border border-dashed border-[var(--line)] p-6 text-sm text-[var(--muted)]">
                Select a pull request to inspect findings.
              </p>
            )}
          </section>
        </main>
      </div>
    </div>
  );
}
