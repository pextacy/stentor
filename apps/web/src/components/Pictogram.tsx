import type { AlertIntent } from "@/lib/api";

/* Language independent card: hazard + action + prohibitions + place/time chips.
   The last resort for anyone who cannot read any of the languages. */

const S = { fill: "none", stroke: "currentColor", strokeWidth: 6, strokeLinecap: "round", strokeLinejoin: "round" } as const;

const HAZARD: Record<string, JSX.Element> = {
  wildfire: <path {...S} d="M50 90c-17 0-28-11-28-26 0-15 12-22 14-38 9 7 12 15 12 22 4-5 6-11 6-18 14 9 24 21 24 36 0 14-11 24-28 24zM50 90c-7 0-12-5-12-12 0-8 7-12 9-19 8 6 15 11 15 19 0 7-5 12-12 12z" />,
  flood: (
    <g {...S}>
      <path d="M28 52V30l22-16 22 16v22" />
      <path d="M10 64c8 0 8-6 16-6s8 6 16 6 8-6 16-6 8 6 16 6 8-6 16-6M10 82c8 0 8-6 16-6s8 6 16 6 8-6 16-6 8 6 16 6 8-6 16-6" />
    </g>
  ),
  earthquake: (
    <g {...S}>
      <path d="M10 60h80" />
      <path d="M50 60l-8 10 10 6-6 14" />
      <path d="M26 46V26h18v20M56 46V18h18v28" />
    </g>
  ),
  tsunami: <path {...S} d="M10 84h80M14 84c0-34 20-60 50-60 12 0 22 6 22 16-10-6-24-2-24 12 0 10 8 16 18 14-6 10-20 18-36 18" />,
  hurricane: (
    <g {...S}>
      <circle cx="50" cy="50" r="10" />
      <path d="M50 40c0-18 14-26 30-24M60 50c18 0 26 14 24 30M50 60c0 18-14 26-30 24M40 50c-18 0-26-14-24-30" />
    </g>
  ),
  tornado: <path {...S} d="M12 18h76M20 34h60M30 50h40M38 66h26M44 82h12" />,
  extreme_heat: (
    <g {...S}>
      <circle cx="40" cy="44" r="14" />
      <path d="M40 14v8M40 66v8M10 44h8M62 44h8M19 23l6 6M55 59l6 6M19 65l6-6M55 29l6-6" />
      <path d="M78 30v38" />
      <circle cx="78" cy="78" r="8" />
    </g>
  ),
  hazmat: (
    <g {...S}>
      <path d="M38 12h24M42 12v24L18 80a6 6 0 0 0 5 9h54a6 6 0 0 0 5-9L58 36V12" />
      <path d="M30 64h40" />
    </g>
  ),
  active_threat: (
    <g {...S}>
      <path d="M34 10h32l24 24v32L66 90H34L10 66V34z" />
      <path d="M50 28v28M50 70v2" />
    </g>
  ),
  boil_water: (
    <g {...S}>
      <path d="M20 44h60v30a12 12 0 0 1-12 12H32a12 12 0 0 1-12-12z" />
      <path d="M12 44h76M38 32c0-6 6-6 6-12M56 32c0-6 6-6 6-12" />
    </g>
  ),
  other: (
    <g {...S}>
      <path d="M50 12l40 72H10z" />
      <path d="M50 40v20M50 72v2" />
    </g>
  ),
};

const ACTION: Record<string, JSX.Element> = {
  evacuate_now: (
    <g {...S}>
      <path d="M14 14h36v72H14z" />
      <path d="M40 50h46M72 36l14 14-14 14" />
    </g>
  ),
  prepare_to_evacuate: (
    <g {...S}>
      <rect x="16" y="34" width="68" height="46" rx="6" />
      <path d="M38 34V22h24v12M16 54h68" />
    </g>
  ),
  shelter_in_place: (
    <g {...S}>
      <path d="M12 46L50 16l38 30M22 40v46h56V40" />
      <circle cx="50" cy="52" r="6" />
      <path d="M50 58v16M40 66h20" />
    </g>
  ),
  move_to_higher_ground: (
    <g {...S}>
      <path d="M10 86l36-44 14 16 30-40" />
      <path d="M74 18h16v16" />
    </g>
  ),
  stay_indoors: (
    <g {...S}>
      <path d="M12 46L50 16l38 30M22 40v46h56V40" />
      <path d="M42 86V62h16v24" />
    </g>
  ),
  avoid_area: (
    <g {...S}>
      <circle cx="50" cy="50" r="36" />
      <path d="M28 50h44" />
    </g>
  ),
  boil_water: (
    <g {...S}>
      <path d="M22 30h56v28a12 12 0 0 1-12 12H34a12 12 0 0 1-12-12z" />
      <path d="M38 88c0-6 6-8 6-14M56 88c0-6 6-8 6-14" />
    </g>
  ),
  monitor: (
    <g {...S}>
      <rect x="18" y="44" width="64" height="40" rx="6" />
      <path d="M30 44l40-24" />
      <circle cx="64" cy="64" r="9" />
      <path d="M28 58h18M28 70h18" />
    </g>
  ),
  all_clear: <path {...S} d="M16 52l22 22 46-48" />,
};

const PROHIBIT: Record<string, JSX.Element> = {
  "use:elevators": <g {...S}><rect x="28" y="16" width="44" height="68" rx="4" /><path d="M50 16v68M40 40l-6 8h12zM60 56l-6-8h12z" /></g>,
  "drive:flood_water": <g {...S}><path d="M20 56l8-18h44l8 18v12H20zM30 68v6M70 68v6" /><path d="M12 84c8 0 8-6 16-6s8 6 16 6 8-6 16-6 8 6 16 6" /></g>,
  "return": <g {...S}><path d="M60 24L34 50l26 26" /><path d="M34 50h44" /></g>,
  "go:outside": <g {...S}><path d="M22 14h34v72H22z" /><path d="M48 50h38M72 36l14 14-14 14" /></g>,
  "drink:tap_water": <g {...S}><path d="M20 30h34v14H40v8" /><path d="M66 60c0 8-6 14-12 14s-12-6-12-14 12-22 12-22 12 14 12 22z" /></g>,
  "light:fires": <path {...S} d="M50 86c-14 0-22-9-22-21 0-12 10-18 12-30 7 6 9 12 9 18 4-4 5-9 5-14 11 7 18 17 18 28 0 11-8 19-22 19z" />,
  "touch:power_lines": <path {...S} d="M56 10L30 54h20L42 90l28-48H50z" />,
  "open:door": <g {...S}><path d="M26 12h48v76H26z" /><circle cx="64" cy="52" r="3" /></g>,
  "return:until_cleared": <g {...S}><path d="M60 24L34 50l26 26" /><path d="M34 50h44" /></g>,
  "go:beach": <g {...S}><path d="M10 70c8 0 8-6 16-6s8 6 16 6 8-6 16-6 8 6 16 6 8-6 16-6" /><circle cx="70" cy="30" r="10" /><path d="M10 84h80" /></g>,
  "enter:damaged_buildings": <g {...S}><path d="M20 88V30l30-18 30 18v58" /><path d="M46 30l8 14-10 10 8 14" /></g>,
  "go_near:windows": <g {...S}><rect x="22" y="18" width="56" height="64" rx="3" /><path d="M50 18v64M22 50h56" /></g>,
  wait: <g {...S}><circle cx="50" cy="52" r="32" /><path d="M50 32v20l12 10" /></g>,
};

function Tile({ children, label, tone = "ink", prohibited = false }: { children: React.ReactNode; label: string; tone?: string; prohibited?: boolean }) {
  return (
    <figure className="flex flex-col items-center gap-1">
      <div className={`relative grid h-24 w-24 place-items-center rounded-xl border-4 bg-white ${prohibited ? "border-blocked text-ink" : tone === "tape" ? "border-ink bg-tape text-ink" : "border-ink text-ink"}`}>
        <svg viewBox="0 0 100 100" className="h-16 w-16" aria-hidden="true">
          {children}
          {prohibited && <g stroke="#A3221B" strokeWidth="9" fill="none"><circle cx="50" cy="50" r="44" /><path d="M19 81L81 19" /></g>}
        </svg>
      </div>
      <figcaption className="max-w-24 text-center text-xs font-medium text-slate-mute">{label}</figcaption>
    </figure>
  );
}

export function Pictogram({ intent, places, times }: { intent: AlertIntent; places: string[]; times: string[] }) {
  const prohibitions = intent.instructions
    .filter((i) => i.negated)
    .map((i) => ({ key: i.verb + (i.object ? `:${i.object}` : ""), i }))
    .filter(({ key }) => PROHIBIT[key]);
  return (
    <div role="img" aria-label={`Pictogram: ${intent.hazard.replace("_", " ")}, ${intent.action.replace(/_/g, " ")}${prohibitions.length ? ", do not " + prohibitions.map(({ i }) => `${i.verb} ${i.object ?? ""}`.trim()).join(", ") : ""}`}
      className="rounded-2xl border-2 border-ink bg-white p-4">
      <div className="flex flex-wrap items-start justify-center gap-3">
        <Tile label={intent.hazard.replace("_", " ")} tone="tape">{HAZARD[intent.hazard] ?? HAZARD.other}</Tile>
        <svg viewBox="0 0 24 24" className="mt-9 h-6 w-6 text-ink" aria-hidden="true"><path d="M4 12h14M13 6l6 6-6 6" fill="none" stroke="currentColor" strokeWidth="3" /></svg>
        <Tile label={intent.action.replace(/_/g, " ")}>{ACTION[intent.action] ?? ACTION.monitor}</Tile>
        {prohibitions.map(({ key }) => (
          <Tile key={key} label={`not: ${key.replace(":", " ").replace("_", " ")}`} prohibited>{PROHIBIT[key]}</Tile>
        ))}
      </div>
      {(places.length > 0 || times.length > 0) && (
        <div className="mt-3 flex flex-wrap justify-center gap-2 text-sm">
          {places.map((p) => <span key={p} className="rounded-full border-2 border-ink px-3 py-0.5 font-medium">⌖ {p}</span>)}
          {times.map((t) => <span key={t} className="rounded-full border-2 border-ink px-3 py-0.5 font-mono">◷ {t}</span>)}
        </div>
      )}
    </div>
  );
}
