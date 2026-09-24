import type { Step } from "../types";

const STEPS: { id: Step; label: string }[] = [
  { id: "upload", label: "Upload" },
  { id: "review", label: "Review" },
  { id: "generate", label: "Generate" },
  { id: "download", label: "Download" },
];

export function StepRail({
  current,
  slideCount,
  approved,
  onJump,
}: {
  current: Step;
  slideCount?: number;
  approved?: number;
  onJump?: (s: Step) => void;
}) {
  const currentIdx = STEPS.findIndex((s) => s.id === current);
  return (
    <nav className="flex w-[190px] shrink-0 flex-col border-r border-stevens-lightgray bg-[#fafbfc] p-4">
      <div className="mb-3 text-[10px] font-extrabold tracking-[0.14em] text-stevens-gray">
        WORKFLOW
      </div>
      {STEPS.map((s, i) => {
        const done = i < currentIdx;
        const active = s.id === current;
        const clickable = onJump && i <= currentIdx;
        return (
          <button
            key={s.id}
            disabled={!clickable}
            onClick={() => clickable && onJump?.(s.id)}
            className={`mb-1.5 flex items-center gap-2.5 rounded-lg px-2.5 py-2.5 text-left text-[13px] font-bold transition ${
              active
                ? "bg-stevens-lightblue text-stevens-blue"
                : "text-stevens-gray hover:bg-stevens-lightgray/50"
            } ${clickable ? "cursor-pointer" : "cursor-default"}`}
          >
            <span
              className={`grid h-[22px] w-[22px] place-items-center rounded-full text-[11px] text-white ${
                done ? "bg-[#1f8a5b]" : active ? "bg-stevens-red" : "bg-[#cfd4d8]"
              }`}
            >
              {done ? "?" : i + 1}
            </span>
            {s.label}
          </button>
        );
      })}

      {typeof slideCount === "number" && (
        <>
          <div className="mb-2 mt-6 text-[10px] font-extrabold tracking-[0.14em] text-stevens-gray">
            DECK
          </div>
          <RailStat n={slideCount} label="slides" color="bg-stevens-blue" />
          {typeof approved === "number" && (
            <RailStat n={approved} label="approved" color="bg-[#1f8a5b]" />
          )}
        </>
      )}
    </nav>
  );
}

function RailStat({ n, label, color }: { n: number; label: string; color: string }) {
  return (
    <div className="mb-1.5 flex items-center gap-2.5 px-2.5 py-1.5 text-[13px] font-bold text-stevens-ink">
      <span className={`grid h-[22px] min-w-[22px] place-items-center rounded-full px-1 text-[11px] text-white ${color}`}>
        {n}
      </span>
      {label}
    </div>
  );
}
