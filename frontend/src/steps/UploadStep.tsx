import { useRef, useState } from "react";

export function UploadStep({
  onFile,
  busy,
  error,
}: {
  onFile: (f: File) => void;
  busy: boolean;
  error?: string;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);

  const pick = (files?: FileList | null) => {
    const f = files?.[0];
    if (f && !busy) onFile(f);
  };

  return (
    <div className="mx-auto flex max-w-3xl flex-col px-8 py-10">
      <div className="eyebrow">NEW PRESENTATION</div>
      <h1 className="mt-1 text-3xl font-extrabold text-stevens-ink">Build a better deck</h1>
      <p className="mt-2 max-w-xl text-sm text-stevens-gray">
        Upload a PowerPoint to preserve its content on the Stevens template.
        Review a generated candidate and its verification findings before downloading
        a verified final deck. Unsupported content and unfinished checks are reported.
      </p>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          pick(e.dataTransfer.files);
        }}
        onClick={() => inputRef.current?.click()}
        className={`mt-8 grid cursor-pointer place-items-center rounded-xl2 border-2 border-dashed px-6 py-16 text-center transition ${
          drag
            ? "border-stevens-red bg-stevens-red/5"
            : "border-stevens-blue bg-stevens-lightblue"
        }`}
      >
        {busy ? (
          <div className="text-stevens-blue">
            <Spinner />
            <div className="mt-3 text-sm font-bold">Analyzing your slides...</div>
          </div>
        ) : (
          <>
            <div className="grid h-14 w-14 place-items-center rounded-full bg-white text-2xl font-bold text-stevens-blue shadow-card">
              {"\u2191"}
            </div>
            <div className="mt-4 text-base font-extrabold text-stevens-blue">
              Drop your PowerPoint here
            </div>
            <div className="mt-1 text-xs text-stevens-gray">or</div>
            <button className="btn-red mt-3">Choose .pptx file</button>
            <div className="mt-3 text-[11px] text-stevens-gray">
              Session files expire after one idle hour. Explicitly saved benchmarks are retained.
            </div>
          </>
        )}
        <input
          ref={inputRef}
          type="file"
          accept=".pptx"
          hidden
          onChange={(e) => pick(e.target.files)}
        />
      </div>

      {error && (
        <div className="mt-4 rounded-lg border border-stevens-red bg-stevens-red/5 px-4 py-3 text-sm font-semibold text-stevens-red">
          {error}
        </div>
      )}
    </div>
  );
}

export function Spinner() {
  return (
    <div className="mx-auto h-8 w-8 animate-spin rounded-full border-[3px] border-stevens-lightgray border-t-stevens-red" />
  );
}
