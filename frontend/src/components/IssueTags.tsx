import type { Revision } from "../types";

const TAGS: { id: string; label: string }[] = [
  { id: "overlap", label: "Overlap" },
  { id: "layout", label: "Layout issue" },
  { id: "dense", label: "Too dense" },
  { id: "emphasis", label: "Wrong emphasis" },
  { id: "split", label: "Split slide" },
  { id: "diagram", label: "Fix diagram" },
];

export function IssueTags({
  value,
  approved,
  busy,
  onChange,
  onApprove,
  onRegenerate,
}: {
  value: Revision;
  approved: boolean;
  busy: boolean;
  onChange: (rev: Revision) => void;
  onApprove: () => void;
  onRegenerate: () => void;
}) {
  const toggle = (id: string) => {
    const has = value.tags.includes(id);
    onChange({
      ...value,
      tags: has ? value.tags.filter((t) => t !== id) : [...value.tags, id],
    });
  };

  return (
    <div className="mt-4">
      <div className="text-[10px] font-extrabold uppercase tracking-wide text-stevens-gray">
        Need a change? Tag it (optional)
      </div>
      <div className="mt-2 flex flex-wrap gap-2">
        {TAGS.map((t) => {
          const on = value.tags.includes(t.id);
          return (
            <button
              key={t.id}
              onClick={() => toggle(t.id)}
              className={`rounded-full border px-3 py-1.5 text-[12px] font-bold transition ${
                on
                  ? "border-stevens-red bg-stevens-red text-white"
                  : "border-stevens-lightgray bg-white text-stevens-gray hover:border-stevens-blue"
              }`}
            >
              {t.label}
            </button>
          );
        })}
      </div>
      <textarea
        value={value.instruction}
        onChange={(e) => onChange({ ...value, instruction: e.target.value })}
        placeholder={'Add an instruction... e.g. "move the citation under the diagram"'}
        rows={2}
        className="mt-3 w-full resize-none rounded-lg border border-stevens-lightgray px-3 py-2 text-sm outline-none focus:border-stevens-blue"
      />
      <p className="mt-1 text-[11px] text-stevens-gray">
        Tip: minor tweaks can also be made directly in PowerPoint after download.
      </p>

      <div className="mt-3 flex gap-2.5">
        <button className="btn-green" onClick={onApprove} disabled={busy}>
          {approved ? "\u2713 Approved" : "\u2713 Approve slide"}
        </button>
        <button
          className="btn-ghost"
          onClick={onRegenerate}
          disabled={busy || (value.tags.length === 0 && !value.instruction.trim())}
        >
          {"\u21bb"} Apply tags
        </button>
      </div>
    </div>
  );
}
