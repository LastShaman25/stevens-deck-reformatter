import { previewUrl } from "../api";

export function SlideCompare({
  sessionId,
  index,
  bust,
}: {
  sessionId: string;
  index: number;
  bust: number;
}) {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      <Panel label="Original">
        <img
          src={previewUrl(sessionId, index, "before", bust)}
          alt="Original slide"
          className="block aspect-video w-full rounded-md border border-stevens-lightgray bg-stevens-lightgray/40 object-contain"
        />
      </Panel>
      <Panel label="Stevens (v1 rules)">
        <div className="relative">
          <img
            src={previewUrl(sessionId, index, "after", bust)}
            alt="Rebuilt slide"
            className="block aspect-video w-full rounded-md border border-stevens-lightgray bg-white object-contain"
          />
          <span className="absolute right-2 top-2 inline-flex items-center gap-1 rounded-full bg-[#1f8a5b] px-2 py-0.5 text-[10px] font-extrabold text-white">
            <span aria-hidden>{"\u2713"}</span> On brand
          </span>
        </div>
      </Panel>
    </div>
  );
}

function Panel({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-1.5 text-[10px] font-extrabold uppercase tracking-wide text-stevens-gray">
        {label}
      </div>
      {children}
    </div>
  );
}
