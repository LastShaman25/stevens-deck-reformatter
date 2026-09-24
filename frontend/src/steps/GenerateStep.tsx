import { Spinner } from "./UploadStep";
import type { Quality } from "../types";

export function GenerateStep({
  busy,
  quality,
  builtSlides,
  onContinue,
  onBack,
}: {
  busy: boolean;
  quality?: Quality;
  builtSlides?: number;
  onContinue: () => void;
  onBack: () => void;
}) {
  return (
    <div className="mx-auto flex max-w-2xl flex-col px-8 py-12">
      <div className="eyebrow">GENERATE</div>
      <h1 className="mt-1 text-3xl font-extrabold text-stevens-ink">
        {busy ? "Rebuilding your deck..." : "Deck generated"}
      </h1>

      {busy && (
        <div className="mt-10 grid place-items-center">
          <Spinner />
          <div className="mt-4 text-sm font-semibold text-stevens-gray">
            Applying Stevens rules {"\u00b7"} checking geometry {"\u00b7"} verifying no overflow
          </div>
        </div>
      )}

      {!busy && quality && (
        <>
          <p className="mt-2 text-sm text-stevens-gray">
            {builtSlides} slides rebuilt onto the Stevens template and quality-checked.
          </p>
          <div className="mt-6 card p-6">
            <div className="flex items-center gap-4">
              <ScoreBadge score={quality.score} />
              <div>
                <div className="text-lg font-extrabold text-stevens-ink">
                  Brand &amp; layout score
                </div>
                <div className="text-sm text-stevens-gray">
                  {quality.coverage_ok
                    ? "Every source item placed exactly once - nothing lost or invented."
                    : "Content coverage flagged - review before download."}
                </div>
              </div>
            </div>
            <div className="mt-4 grid grid-cols-3 gap-3 text-center">
              <Stat value={quality.coverage_ok ? "100%" : "check"} label="Content kept" />
              <Stat value={String(quality.diagrams_reconstructed)} label="Diagrams rebuilt" />
              <Stat value={String(quality.unresolved)} label="Layout flags" />
            </div>
          </div>
          <div className="mt-6 flex gap-3">
            <button className="btn-red" onClick={onContinue}>
              Continue to download {"\u2192"}
            </button>
            <button className="btn-ghost" onClick={onBack}>
              {"\u2190"} Back to review
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div className="rounded-lg border border-stevens-lightgray bg-stevens-lightblue/40 px-2 py-3">
      <div className="text-xl font-extrabold text-stevens-blue">{value}</div>
      <div className="mt-0.5 text-[11px] font-semibold text-stevens-gray">{label}</div>
    </div>
  );
}

function ScoreBadge({ score }: { score: number }) {
  const color = score >= 90 ? "#1f8a5b" : score >= 75 ? "#EBC73B" : "#A32638";
  return (
    <div
      className="grid h-20 w-20 place-items-center rounded-full"
      style={{ background: `conic-gradient(${color} ${score}%, #e5e8eb 0)` }}
    >
      <div className="grid h-16 w-16 place-items-center rounded-full bg-white text-xl font-extrabold text-stevens-ink">
        {score}
      </div>
    </div>
  );
}
