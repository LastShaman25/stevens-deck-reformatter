import type { Capabilities } from "../types";

export function StevensMark({ size = 30 }: { size?: number }) {
  // Stevens brand motif: a red diamond inside a white ring.
  return (
    <div
      className="relative grid place-items-center rounded-lg bg-white/10 ring-1 ring-white/25"
      style={{ width: size, height: size }}
      aria-hidden
    >
      <span
        className="diamond bg-gradient-to-br from-stevens-red to-stevens-reddark shadow"
        style={{ width: size * 0.42, height: size * 0.42 }}
      />
    </div>
  );
}

export function AppBar({
  name,
  caps,
  right,
}: {
  name?: string;
  caps?: Capabilities;
  right?: React.ReactNode;
}) {
  return (
    <header className="flex h-14 items-center gap-3 bg-gradient-to-r from-stevens-bluedark via-stevens-blue to-stevens-blue px-5 text-white shadow-md">
      <StevensMark />
      <div className="text-[15px] font-extrabold tracking-wide">
        STEVENS{" "}
        <span className="font-normal text-white/75">Slide Studio</span>
      </div>
      {name && (
        <div className="ml-3 hidden max-w-[280px] items-center gap-1.5 truncate rounded-md bg-white/10 px-3 py-1 text-xs font-semibold ring-1 ring-white/15 md:flex">
          <span className="diamond h-1.5 w-1.5 bg-stevens-gold" />
          {name}
        </div>
      )}
      <div className="flex-1" />
      {caps && (
        <div className="hidden items-center gap-2 text-[11px] font-semibold sm:flex">
          <CapBadge on={!!caps.claude} label="AI layout: Claude" />
          <CapBadge on={caps.libreoffice} label="Pixel preview" />
          <CapBadge on={caps.gemini} label="AI visual check" />
        </div>
      )}
      {right}
    </header>
  );
}

function CapBadge({ on, label }: { on: boolean; label: string }) {
  return (
    <span
      className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 ${
        on ? "bg-white/20 text-white" : "bg-white/5 text-white/55"
      }`}
      title={on ? `${label}: available` : `${label}: off`}
    >
      <span
        className={`inline-block h-2 w-2 rounded-full ${
          on ? "bg-white" : "border border-white/60 bg-transparent"
        }`}
      />
      {label}
    </span>
  );
}
