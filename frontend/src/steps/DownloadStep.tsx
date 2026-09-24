import { useState } from "react";
import { downloadUrl, sendToBenchmark } from "../api";
import type { BenchmarkResult, Quality } from "../types";

export function DownloadStep({
  sessionId,
  name,
  slideCount,
  quality,
  onStartOver,
}: {
  sessionId: string;
  name: string;
  slideCount: number;
  quality?: Quality;
  onStartOver: () => void;
}) {
  const base = name.replace(/\.pptx$/i, "");
  const [benchOn, setBenchOn] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<BenchmarkResult | null>(null);
  const [err, setErr] = useState<string | undefined>();

  const clean = quality?.lint_clean ?? true;
  const lintFail = quality?.lint_fail ?? 0;

  const toggle = async () => {
    const next = !benchOn;
    setBenchOn(next);
    setErr(undefined);
    if (!next) {
      setResult(null);
      sendToBenchmark(sessionId, false).catch(() => {});
      return;
    }
    setBusy(true);
    try {
      const r = await sendToBenchmark(sessionId, true);
      setResult(r);
    } catch (e: any) {
      setBenchOn(false);
      setErr(e.message || "Could not add to benchmark.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto flex max-w-2xl flex-col items-center px-8 py-14 text-center">
      <div className="animate-pop-in grid h-16 w-16 place-items-center rounded-2xl bg-gradient-to-br from-[#1f8a5b] to-[#14663f] text-3xl text-white shadow-glow">
        {"\u2713"}
      </div>
      <h1 className="mt-5 text-3xl font-extrabold text-stevens-ink">
        Your deck is ready
      </h1>
      <p className="mt-2 text-sm text-stevens-gray">
        <b className="text-stevens-ink">{base} (Stevens).pptx</b> {"\u2014"}{" "}
        {slideCount} source slides rebuilt on the Stevens template. Open it in
        PowerPoint for any final manual tweaks.
      </p>

      {quality && (
        <div className="mt-4 flex items-center gap-2 text-xs font-semibold">
          <span
            className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 ${
              clean
                ? "bg-[#e8f5ee] text-[#14663f]"
                : "bg-[#fdecee] text-stevens-red"
            }`}
          >
            <span
              className={`diamond h-2 w-2 ${
                clean ? "bg-[#1f8a5b]" : "bg-stevens-red"
              }`}
            />
            {clean
              ? "Brand-lint: all slides clean"
              : `Brand-lint: ${lintFail} issue(s) to review`}
          </span>
          <span className="rounded-full bg-stevens-lightblue px-3 py-1 text-stevens-blue">
            Quality {quality.score}/100
          </span>
        </div>
      )}

      <a
        className="btn-red mt-8 px-6 py-3 text-base"
        href={downloadUrl(sessionId)}
      >
        {"\u2193"} Download PowerPoint
      </a>

      {/* Approval-gated benchmark: reviewer verifies the deck is good, then it
          becomes a new gold benchmark the tool keeps learning from. */}
      <div className="card mt-8 w-full max-w-xl p-5 text-left">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="diamond h-2.5 w-2.5 bg-stevens-red" />
              <h3 className="text-sm font-extrabold text-stevens-ink">
                Send to benchmark
              </h3>
            </div>
            <p className="mt-1 text-xs leading-relaxed text-stevens-gray">
              Verify this deck is up to standard and add it to the gold
              benchmark set. Approved decks set the new baseline and the tool
              keeps learning from them {"\u2014"} nothing is captured unless you
              turn this on.
            </p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={benchOn}
            aria-label="Send to benchmark"
            disabled={busy}
            onClick={toggle}
            className={`toggle ${benchOn ? "bg-[#1f8a5b]" : "bg-stevens-lightgray"} disabled:opacity-60`}
          >
            <span
              className={`toggle-knob ${benchOn ? "translate-x-5" : ""}`}
            />
          </button>
        </div>

        {busy && (
          <p className="mt-3 text-xs font-semibold text-stevens-blue">
            Adding to benchmark{"\u2026"}
          </p>
        )}
        {result?.benchmarked && (
          <p className="mt-3 rounded-md bg-[#e8f5ee] px-3 py-2 text-xs font-semibold text-[#14663f]">
            {"\u2713"} Added as benchmark{" "}
            {result.total_benchmarks ? `(#${result.total_benchmarks} in the set)` : ""}
            . Future rebuilds will learn from this deck.
          </p>
        )}
        {err && (
          <p className="mt-3 rounded-md bg-[#fdecee] px-3 py-2 text-xs font-semibold text-stevens-red">
            {err}
          </p>
        )}
      </div>

      <button className="btn-ghost mt-6" onClick={onStartOver}>
        Start a new deck
      </button>

      <p className="mt-8 text-[11px] text-stevens-gray">
        Your files are processed temporarily and are automatically deleted after
        your session.
      </p>
    </div>
  );
}
