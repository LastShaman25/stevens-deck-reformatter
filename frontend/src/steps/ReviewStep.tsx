import { Filmstrip } from "../components/Filmstrip";
import { SlideCompare } from "../components/SlideCompare";
import { IssueTags } from "../components/IssueTags";
import { AiCheckPanel } from "../components/AiCheckPanel";
import type { AiFlag, ReviseResult, Revision, SessionInfo, SlidePlan } from "../types";

const KIND_LABEL: Record<string, string> = {
  title: "Title slide",
  thankyou: "Closing slide",
  section: "Section divider",
  picture: "Visual slide",
  content: "Content slide",
};

const DOT = " \u00b7 ";

export function ReviewStep({
  session,
  current,
  approved,
  revision,
  bust,
  busy,
  applyResult,
  aiOn,
  aiResult,
  aiBusy,
  onToggleAi,
  onRunAiCheck,
  onClearAiCheck,
  onSelect,
  onRevisionChange,
  onApprove,
  onApplyTags,
}: {
  session: SessionInfo;
  current: number;
  approved: Set<number>;
  revision: Revision;
  bust: number;
  busy: boolean;
  applyResult?: ReviseResult;
  aiOn: boolean;
  aiResult?: AiFlag[];
  aiBusy: boolean;
  onToggleAi: (on: boolean) => void;
  onRunAiCheck: () => void;
  onClearAiCheck: () => void;
  onSelect: (i: number) => void;
  onRevisionChange: (rev: Revision) => void;
  onApprove: () => void;
  onApplyTags: () => void;
}) {
  const slide: SlidePlan =
    session.slides.find((s) => s.index === current) ?? session.slides[0];

  const meta =
    (KIND_LABEL[slide.kind] ?? "Slide") +
    DOT +
    slide.layout +
    (slide.issues.length > 0 ? DOT + slide.issues.join(DOT) : "");

  return (
    <div className="flex min-w-0 flex-1 flex-col overflow-y-auto px-6 py-5">
      <header className="mb-4 flex items-start gap-3">
        <div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-stevens-blue text-sm font-extrabold text-white">
          {slide.index + 1}
        </div>
        <div className="min-w-0">
          <div className="eyebrow">
            REVIEWING SLIDE {slide.index + 1} OF {session.slide_count}
          </div>
          <h2 className="mt-0.5 line-clamp-2 text-lg font-extrabold leading-snug text-stevens-ink">
            {slide.title}
          </h2>
          <div className="mt-1 text-xs text-stevens-gray">{meta}</div>
        </div>
      </header>

      <SlideCompare sessionId={session.session_id} index={slide.index} bust={bust} />

      <div className="mt-4 rounded-lg border-l-4 border-stevens-blue bg-stevens-lightblue px-4 py-3">
        <div className="text-[12px] font-extrabold text-stevens-blue">Why this layout</div>
        <p className="mt-0.5 text-[13px] leading-relaxed text-stevens-ink">
          {slide.rationale}
        </p>
      </div>

      <IssueTags
        value={revision}
        approved={approved.has(slide.index)}
        busy={busy}
        onChange={onRevisionChange}
        onApprove={onApprove}
        onRegenerate={onApplyTags}
      />

      {applyResult && (
        <div
          className={`mt-3 flex items-start gap-2 rounded-lg border-l-4 px-4 py-3 text-[13px] leading-relaxed ${
            applyResult.changed
              ? "border-[#1f8a5b] bg-[#e8f5ee] text-[#14663f]"
              : "border-stevens-gold bg-[#fdf6dd] text-[#7a5b00]"
          }`}
        >
          <span className="mt-0.5 font-extrabold">
            {applyResult.changed ? "\u2713" : "\u24d8"}
          </span>
          <span>{applyResult.summary}</span>
        </div>
      )}

      <AiCheckPanel
        enabled={aiOn}
        available={!!session.capabilities.gemini}
        busy={aiBusy}
        result={aiResult}
        onToggle={onToggleAi}
        onRun={onRunAiCheck}
        onClear={onClearAiCheck}
      />

      <div className="mt-5">
        <Filmstrip
          sessionId={session.session_id}
          slides={session.slides}
          current={current}
          approved={approved}
          onSelect={onSelect}
        />
      </div>
    </div>
  );
}
