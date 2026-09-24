import { previewUrl } from "../api";
import type { SlidePlan } from "../types";

export function Filmstrip({
  sessionId,
  slides,
  current,
  approved,
  onSelect,
}: {
  sessionId: string;
  slides: SlidePlan[];
  current: number;
  approved: Set<number>;
  onSelect: (index: number) => void;
}) {
  return (
    <div className="flex gap-2 overflow-x-auto border-t border-stevens-lightgray pt-3">
      {slides.map((s) => {
        const sel = s.index === current;
        return (
          <button
            key={s.index}
            onClick={() => onSelect(s.index)}
            className={`relative shrink-0 overflow-hidden rounded-md border transition ${
              sel
                ? "border-stevens-red ring-2 ring-stevens-red/25"
                : "border-stevens-lightgray hover:border-stevens-blue"
            }`}
            style={{ width: 104 }}
            title={`Slide ${s.index + 1}: ${s.title}`}
          >
            <img
              src={previewUrl(sessionId, s.index, "after")}
              alt={`Slide ${s.index + 1}`}
              className="block h-[58px] w-full object-cover"
              loading="lazy"
            />
            <span className="absolute left-1 top-1 rounded bg-black/55 px-1 text-[9px] font-bold text-white">
              {s.index + 1}
            </span>
            {approved.has(s.index) && (
              <span className="absolute bottom-1 right-1 grid h-4 w-4 place-items-center rounded-full bg-[#1f8a5b] text-[9px] font-bold text-white">
                ?
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
