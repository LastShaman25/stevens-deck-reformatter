import {useId, useRef, useState} from 'react';

export function DownloadButton({disabled, pdfAvailable, onDownload}: {
  disabled: boolean; pdfAvailable: boolean; onDownload: (format: 'pptx' | 'pdf') => Promise<void>;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const title = useId();
  const [format, setFormat] = useState<'pptx' | 'pdf'>('pptx');
  return <>
    <button className="btn-red w-full" disabled={disabled} onClick={() => dialog.current?.showModal()}>Download</button>
    <dialog ref={dialog} aria-labelledby={title} className="w-[min(28rem,90vw)] rounded-xl border p-6 shadow-xl backdrop:bg-black/40">
      <h2 id={title} className="text-lg font-bold">Choose download format</h2>
      <fieldset className="my-5 space-y-3"><legend className="sr-only">File format</legend>
        <label className="flex gap-3"><input type="radio" name={title} checked={format==='pptx'} onChange={() => setFormat('pptx')}/>PowerPoint (.pptx)</label>
        <label className="flex gap-3"><input type="radio" name={title} checked={format==='pdf'} disabled={!pdfAvailable} onChange={() => setFormat('pdf')}/>PDF (.pdf)</label>
        {!pdfAvailable && <p className="text-sm text-stevens-gray">A verified PDF is not available for this candidate.</p>}
      </fieldset>
      <p className="mb-5 text-sm text-stevens-gray">Downloading ends this session and deletes its processing files.</p>
      <div className="flex justify-end gap-3"><button className="btn-ghost" onClick={() => dialog.current?.close()}>Cancel</button>
        <button className="btn-red" disabled={disabled || (format==='pdf' && !pdfAvailable)} onClick={async () => {dialog.current?.close(); await onDownload(format);}}>Download and finish</button></div>
    </dialog>
  </>;
}
