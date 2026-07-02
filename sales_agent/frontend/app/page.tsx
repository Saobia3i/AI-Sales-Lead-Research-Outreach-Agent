"use client";

import { FormEvent, useState } from "react";

type EvidenceRef = {
  url: string;
  relevance_score: number;
  used_for_claim: string;
};

type CompanyProfile = {
  company_name: string;
  website: string | null;
  industry: string | null;
  company_size_estimate: string | null;
  hq_location: string | null;
  recent_news: { headline: string; summary: string; source_url: string; date: string | null }[];
  pain_point_signals: string[];
  evidence_sources: EvidenceRef[];
  insufficient_evidence: string[];
};

type FullPipelineResponse = {
  profile: CompanyProfile;
  draft_email: { subject: string; body: string; claims_used: string[] };
  verification_report: {
    claim: string;
    status: "verified" | "unverified" | "not_a_factual_claim";
    evidence_ref: string | null;
    confidence: number;
  }[];
  errors: string[];
};

const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export default function Home() {
  const [companyInput, setCompanyInput] = useState("");
  const [productDescription, setProductDescription] = useState("");
  const [result, setResult] = useState<FullPipelineResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  async function runPipeline(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await fetch(`${apiBase}/api/v1/full_pipeline`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ company_input: companyInput, product_description: productDescription }),
      });
      if (!response.ok) {
        throw new Error(`Pipeline failed with ${response.status}`);
      }
      setResult((await response.json()) as FullPipelineResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-paper">
      <section className="border-b border-line bg-white">
        <div className="mx-auto grid max-w-6xl gap-6 px-5 py-8 lg:grid-cols-[0.8fr_1.2fr]">
          <div>
            <p className="text-sm font-semibold uppercase text-moss">LinearAI service line</p>
            <h1 className="mt-3 text-3xl font-semibold text-ink">Sales Lead Research Agent</h1>
            <p className="mt-3 max-w-xl text-sm leading-6 text-ink/70">
              Research a single company, draft a concise outreach email, and verify every factual claim against retrieved evidence.
            </p>
          </div>

          <form onSubmit={runPipeline} className="grid gap-4">
            <label className="grid gap-2 text-sm font-medium text-ink">
              Company name or website
              <input
                className="h-11 rounded-md border border-line bg-white px-3 outline-none focus:border-moss"
                value={companyInput}
                onChange={(event) => setCompanyInput(event.target.value)}
                placeholder="OpenAI or openai.com"
                required
              />
            </label>
            <label className="grid gap-2 text-sm font-medium text-ink">
              Product or value proposition
              <textarea
                className="min-h-28 resize-y rounded-md border border-line bg-white p-3 outline-none focus:border-moss"
                value={productDescription}
                onChange={(event) => setProductDescription(event.target.value)}
                placeholder="We build custom agentic AI systems for sales and operations teams."
                required
              />
            </label>
            <button
              className="h-11 rounded-md bg-moss px-4 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
              disabled={isLoading}
            >
              {isLoading ? "Researching..." : "Run pipeline"}
            </button>
          </form>
        </div>
      </section>

      <section className="mx-auto grid max-w-6xl gap-5 px-5 py-6">
        {error ? <div className="rounded-md border border-coral/30 bg-white p-4 text-sm text-coral">{error}</div> : null}
        {result ? <Results result={result} /> : null}
      </section>
    </main>
  );
}

function Results({ result }: { result: FullPipelineResponse }) {
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <Panel title="Company Profile">
        <dl className="grid gap-3 text-sm">
          <Row label="Name" value={result.profile.company_name} />
          <Row label="Website" value={result.profile.website ?? "No data found"} />
          <Row label="Industry" value={result.profile.industry ?? "No data found"} />
          <Row label="HQ" value={result.profile.hq_location ?? "No data found"} />
          <Row label="Size" value={result.profile.company_size_estimate ?? "No data found"} />
        </dl>
        {result.profile.insufficient_evidence.length ? (
          <p className="mt-4 text-sm text-coral">Insufficient evidence: {result.profile.insufficient_evidence.join(", ")}</p>
        ) : null}
      </Panel>

      <Panel title="Verified Draft">
        <p className="text-sm font-semibold text-ink">{result.draft_email.subject}</p>
        <pre className="mt-3 whitespace-pre-wrap rounded-md border border-line bg-paper p-3 text-sm leading-6 text-ink">
          {result.draft_email.body}
        </pre>
      </Panel>

      <Panel title="Recent News">
        <List
          items={result.profile.recent_news.map((item) => `${item.headline}: ${item.summary}`)}
          fallback="No data found"
        />
      </Panel>

      <Panel title="Verification">
        <List
          items={result.verification_report.map(
            (item) => `${item.status.toUpperCase()} - ${item.claim}${item.evidence_ref ? ` (${item.evidence_ref})` : ""}`,
          )}
          fallback="No factual claims used"
        />
      </Panel>

      <Panel title="Pain Signals">
        <List items={result.profile.pain_point_signals} fallback="No data found" />
      </Panel>

      <Panel title="Evidence">
        <List
          items={result.profile.evidence_sources.map(
            (source) => `${Math.round(source.relevance_score * 100)}% - ${source.used_for_claim} - ${source.url}`,
          )}
          fallback="No evidence retained"
        />
      </Panel>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-md border border-line bg-white p-4">
      <h2 className="text-base font-semibold text-ink">{title}</h2>
      <div className="mt-4">{children}</div>
    </section>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-[8rem_1fr] gap-3">
      <dt className="text-ink/60">{label}</dt>
      <dd className="min-w-0 break-words text-ink">{value}</dd>
    </div>
  );
}

function List({ items, fallback }: { items: string[]; fallback: string }) {
  if (!items.length) {
    return <p className="text-sm text-ink/60">{fallback}</p>;
  }
  return (
    <ul className="grid gap-2 text-sm leading-6 text-ink">
      {items.map((item) => (
        <li key={item} className="break-words border-b border-line pb-2 last:border-0 last:pb-0">
          {item}
        </li>
      ))}
    </ul>
  );
}
