import type { AiFlag } from "../types";

const SEV_STYLE: Record<string, string> = {
  high: "bg-stevens-red/10 text-stevens-red border-stevens-red/30",
  med: "bg-amber-50 text-amber-700 border-amber-200",
  low: "bg-stevens-lightblue text-stevens-blue border-stevens-blue/20",
};

function Toggle({ on, onChange }: { on: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      onClick={() => onChange(!on)}
      className={
        "relative h-6 w-11 shrink-0 rounded-full transition " +
        (on ? "bg-stevens-blue" : "bg-stevens-lightgray")
      }
    >
      <span
        className={
          "absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all " +
          (on ? "left-[22px]" : "left-0.5")
        }
      />
    </button>
  );
}

export function AiCheckPanel({
  enabled,
  available,
  busy,
  result,
  onToggle,
  onRun,
  onClear,
}: {
  enabled: boolean;
  available: boolean;
  busy: boolean;
  result?: AiFlag[];
  onToggle: (on: boolean) => void;
  onRun: () => void;
  onClear: () => void;
}) {
  const hasResult = Array.isArray(result);

  return (
    <div className="mt-4 rounded-lg border border-stevens-lightgray bg-white px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[12px] font-extrabold text-stevens-ink">
            AI visual check {"\u00b7"} Gemini
          </div>
          <p className="mt-0.5 text-[11px] leading-relaxed text-stevens-gray">
            {available
              ? "Inspects the rebuilt slide for overlap, overflow, contrast and off-palette text. Runs only on the slides you pick, so it uses API quota sparingly."
              : "Gemini is not configured on this server, so the AI visual check is unavailable."}
          </p>
        </div>
        <Toggle on={enabled && available} onChange={(v) => available && onToggle(v)} />
      </div>

      {enabled && available && (
        <div className="mt-3">
          <div className="flex items-center gap-2">
            <button className="btn-ghost !py-1.5 !text-[13px]" disabled={busy} onClick={onRun}>
              {busy
                ? "Checking\u2026"
                : hasResult
                ? "Re-run AI check on this slide"
                : "Run AI check on this slide"}
            </button>
            {hasResult && (
              <button
                className="text-[12px] font-semibold text-stevens-gray hover:text-stevens-red"
                onClick={onClear}
              >
                Clear
              </button>
            )}
          </div>

          {hasResult && result!.length === 0 && (
            <div className="mt-3 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-[12px] font-semibold text-emerald-700">
              {"\u2713"} No visual issues found on this slide.
            </div>
          )}

          {hasResult && result!.length > 0 && (
            <ul className="mt-3 space-y-2">
              {result!.map((f, i) => (
                <li
                  key={i}
                  className={
                    "rounded-md border px-3 py-2 text-[12px] " +
                    (SEV_STYLE[f.severity] || SEV_STYLE.low)
                  }
                >
                  <div className="flex items-center gap-2">
                    <span className="rounded bg-white/60 px-1.5 py-0.5 text-[10px] font-extrabold uppercase tracking-wide">
                      {f.type}
                    </span>
                    {f.where && <span className="text-[11px] opacity-80">{f.where}</span>}
                  </div>
                  <p className="mt-1 leading-relaxed">{f.note}</p>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
