import { useRef, useState } from "react";

export function UploadStep({
  onFile,
  busy,
  error,
}: {
  onFile: (f: File, template: 'cpe' | 'stevens') => void;
  busy: boolean;
  error?: string;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  const [template, setTemplate] = useState<'cpe' | 'stevens' | ''>('');
  const [selectionError, setSelectionError] = useState(false);

  const pick = (files?: FileList | null) => {
    const f = files?.[0];
    if (!template) {setSelectionError(true); return;}
    if (f && !busy) onFile(f, template);
  };

  return (
    <div className="mx-auto flex max-w-3xl flex-col px-8 py-10">
      <div className="eyebrow">NEW PRESENTATION</div>
      <h1 className="mt-1 text-3xl font-extrabold text-stevens-ink">Build a better deck</h1>
      <p className="mt-2 max-w-xl text-sm text-stevens-gray">
        Choose CPE or Stevens format, then upload a PowerPoint or PDF to preserve its content.
        Review a generated candidate and its verification findings before downloading
        the final deck. Complex PDF fonts and equations may be preserved as image regions.
        Unsupported content and unfinished checks are reported.
      </p>
      <fieldset disabled={busy} className="mt-6">
        <legend className="text-sm font-bold">Which presentation format do you want?</legend>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          {([{id:'cpe',name:'CPE',detail:'College of Professional Education · dark slate cover'},
             {id:'stevens',name:'Stevens',detail:'University branding · burgundy cover'}] as const).map(option =>
            <label key={option.id} className={`cursor-pointer rounded-lg border p-4 ${template===option.id?'border-stevens-red bg-red-50':'border-stevens-lightgray bg-white'}`}>
              <input type="radio" name="template" value={option.id} checked={template===option.id}
                onChange={()=>{setTemplate(option.id);setSelectionError(false);}} />
              <span className="ml-2 font-bold">{option.name}</span>
              <span className="mt-1 block text-xs text-stevens-gray">{option.detail}</span>
            </label>)}
        </div>
        {selectionError && <p role="alert" className="mt-2 text-sm text-stevens-red">Choose CPE or Stevens format before uploading.</p>}
      </fieldset>

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
        onClick={() => {if (!template) setSelectionError(true); else if (!busy) inputRef.current?.click();}}
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
              Drop your PowerPoint or PDF here
            </div>
            <div className="mt-1 text-xs text-stevens-gray">or</div>
            <button className="btn-red mt-3" disabled={busy}>Choose .pptx or .pdf file</button>
            <div className="mt-3 text-[11px] text-stevens-gray">
              Files are used only for processing and expire after one idle hour. PDF pages without a text layer are preserved as images; their text is not individually editable.
            </div>
          </>
        )}
        <input
          ref={inputRef}
          type="file"
          accept=".pptx,.pdf"
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
