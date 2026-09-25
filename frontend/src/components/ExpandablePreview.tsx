import {useEffect, useId, useRef, useState} from 'react';

type Props = {src: string; alt: string; className?: string; onError?: () => void};

export function ExpandablePreview(props: Props) {
  // A new slide or candidate must never leave the previous image enlarged.
  return <PreviewImage key={props.src} {...props}/>;
}

function PreviewImage({src, alt, className, onError}: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [open]);

  return <>
    <button type="button" className="block w-full cursor-zoom-in rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-stevens-blue"
      aria-label={`Enlarge ${alt}`} aria-haspopup="dialog" title="Click to enlarge" onClick={() => {setOpen(true); dialog.current!.showModal();}}>
      <img src={src} alt={alt} className={className} onError={onError}/>
    </button>
    <dialog ref={dialog} className="slide-preview-dialog" aria-labelledby={titleId}
      onClose={() => {if (!dialog.current?.open) setOpen(false);}}
      onClick={event => {
        if (event.target !== event.currentTarget) return;
        const bounds = event.currentTarget.getBoundingClientRect();
        if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) dialog.current!.close();
      }}>
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 id={titleId} className="font-bold">{alt}</h2>
        <button type="button" autoFocus className="btn-ghost shrink-0" onClick={() => dialog.current!.close()}>Close preview</button>
      </div>
      {open && <img src={src} alt={`${alt} — enlarged`} className="slide-preview-expanded"/>}
    </dialog>
  </>;
}
