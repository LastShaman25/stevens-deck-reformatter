import type { Quality, QualityCheck, SlidePlan } from "../types";

const STATUS_STYLE: Record<QualityCheck["status"], string> = {
  ok: "bg-[#1f8a5b] text-white",
  warn: "bg-stevens-gold text-[#3a2e00]",
  fail: "bg-stevens-red text-white",
  off: "bg-stevens-lightgray text-stevens-gray",
};

const STATUS_MARK: Record<QualityCheck["status"], string> = {
  ok: "\u2713",
  warn: "!",
  fail: "\u2717",
  off: "\u2013",
};

function Ring({ score }: { score: number }) {
  const color = score >= 90 ? "#1f8a5b" : score >= 75 ? "#EBC73B" : "#A32638";
  return (
    <div
      className="grid h-14 w-14 place-items-center rounded-full"
      style={{ background: `conic-gradient(${color} ${score}%, #e5e8eb 0)` }}
    >
      <div className="grid h-11 w-11 place-items-center rounded-full bg-white text-sm font-extrabold text-stevens-ink">
        {score}
      </div>
    </div>
  );
}

function Checklist({ checks }: { checks: QualityCheck[] }) {
  return (
    <div className="mt-3">
      {checks.map((c) => (
        <div
          key={c.label}
          className="flex items-center gap-2 border-b border-[#f0f1f3] py-2 text-[12px] text-stevens-ink last:border-0"
        >
          <span className={`grid h-4 w-4 place-items-center rounded-full text-[9px] font-extrabold ${STATUS_STYLE[c.status]}`}>
            {STATUS_MARK[c.status]}
          </span>
          {c.label}
        </div>
      ))}
    </div>
  );
}

export function QualityPanel({
  slide,
  caps,
  quality,
}: {
  slide?: SlidePlan;
  caps?: { gemini: boolean };
  quality?: Quality;
}) {
  // Result mode: show the deck-level quality after generation.
  if (quality) {
    return (
      <aside className="w-[250px] shrink-0 border-l border-stevens-lightgray bg-white p-4">
        <div className="text-[11px] font-extrabold tracking-[0.14em] text-stevens-gray">
          DECK QUALITY
        </div>
        <div className="mt-3 flex items-center gap-3">
          <Ring score={quality.score} />
          <div className="text-[12px] font-bold text-stevens-gray">
            Brand &amp; layout score
          </div>
        </div>
        <Checklist checks={quality.checks} />
      </aside>
    );
  }

  // Review mode: per-slide checklist derived from the plan.
  const issues = slide?.issues ?? [];
  const hasDiagram = issues.some((i) => i.startsWith("diagram"));
  const isDense = issues.includes("dense");
  const checks: QualityCheck[] = [
    { label: "Palette: Stevens colors only", status: "ok" },
    { label: "Fonts: Arial, sizes in range", status: "ok" },
    { label: "Bullets: square \u2192 arrow \u2192 dash", status: "ok" },
    { label: "Text: black / white / red only", status: "ok" },
    {
      label: isDense ? "Dense: sizes tuned to fit" : "Density: balanced",
      status: "ok",
    },
    {
      label: hasDiagram ? "Diagram: rebuilt, review placement" : "No diagram risks",
      status: hasDiagram ? "warn" : "ok",
    },
    caps?.gemini
      ? { label: "Gemini visual check", status: "ok" }
      : { label: "Gemini visual check (off)", status: "off" },
  ];

  return (
    <aside className="w-[250px] shrink-0 border-l border-stevens-lightgray bg-white p-4">
      <div className="text-[11px] font-extrabold tracking-[0.14em] text-stevens-gray">
        SLIDE QUALITY
      </div>
      <Checklist checks={checks} />
      {slide?.needs_review && (
        <div className="mt-4 rounded-lg bg-stevens-lightblue px-3 py-2 text-[11px] font-semibold text-stevens-blue">
          {"\u2726"} This slide has a visual/diagram - worth a quick look after generate.
        </div>
      )}
    </aside>
  );
}
