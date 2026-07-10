// Phase 26.1: valuation river adapter.
// Normalizes AnalysisReport.details.rawResult.valuationRiverSnapshot (deep
// camelCase from the API layer; snake_case tolerated for raw payload parity,
// same convention as fourMastersCommentaryAdapter.ts) into a strict view
// model. Commentary/action-free: no field here ever carries a buy/sell
// signal, fair value, or target price — the backend contract itself never
// emits those, and this adapter does not invent them either.

export type ValuationRiverZoneVM = "undervalued" | "neutral" | "overvalued" | "unknown";
// Phase 26.2: an EPS number must always travel with what kind it is — never
// present an "implied" (PER-back-derived) or "reported-annual" EPS as if it
// were actual/reported TTM EPS, and never present a forward/estimate as
// actual.
export type ValuationRiverEpsKindVM = "implied" | "reported" | "unavailable";

export interface ValuationRiverBandVM {
  multiple: number;
  value: number;
}

export interface ValuationRiverEpsStatVM {
  value: number;
  period: string;
  source: string;
}

export interface ValuationRiverPointVM {
  date: string;
  close: number;
  per: number | null;
  impliedEps: number | null;
  bands: ValuationRiverBandVM[];
}

export interface ValuationRiverCurrentVM {
  close: number | null;
  per: number | null;
  pbr: number | null;
  impliedEps: number | null;
  impliedBvps: number | null;
  zone: ValuationRiverZoneVM;
  // Point-in-time reference stats, independent of whichever basis the
  // plotted bands use — null when that concept has no source for this
  // symbol/market rather than being silently omitted.
  epsActual: ValuationRiverEpsStatVM | null;
  epsForward: ValuationRiverEpsStatVM | null;
}

export interface ValuationRiverChartVM {
  enabled: true;
  symbol: string;
  currency: string;
  method: string;
  epsKind: ValuationRiverEpsKindVM;
  startDate: string | null;
  endDate: string | null;
  tradingDays: number;
  bandMultiples: number[];
  neutralMultiple: number | null;
  points: ValuationRiverPointVM[];
  current: ValuationRiverCurrentVM;
  isPartial: boolean;
  warnings: string[];
  codes: string[];
  methodologyNote: string;
}

export interface ValuationRiverUnavailableVM {
  enabled: false;
  market: string | null;
  reason: string;
  // Even when the historical river itself couldn't be built, a real
  // point-in-time EPS/forward-EPS value may still exist (e.g. a US stock
  // with a working yfinance `.info` call but too few annual anchors) — show
  // it rather than hiding real data behind the unavailable state.
  epsActual: ValuationRiverEpsStatVM | null;
  epsForward: ValuationRiverEpsStatVM | null;
}

export type ValuationRiverVM = ValuationRiverChartVM | ValuationRiverUnavailableVM;

const ZONE_VALUES: readonly ValuationRiverZoneVM[] = ["undervalued", "neutral", "overvalued", "unknown"];
const MAX_WARNINGS = 6;
const MAX_TEXT_LEN = 300;

function pick(source: Record<string, unknown>, keys: string[]): unknown {
  for (const key of keys) {
    if (source[key] !== undefined && source[key] !== null) return source[key];
  }
  return undefined;
}

function sanitizeText(value: unknown): string | null {
  if (typeof value !== "string") return null;
  // Backend-authored text only (never LLM output); HTML/bracket stripping
  // is sufficient here.
  const text = value
    .replace(/<[^>]*>/g, "")
    .replace(/[<>]/g, "")
    .replace(/\s+/g, " ")
    .trim();
  if (!text) return null;
  return text.slice(0, MAX_TEXT_LEN);
}

function toFiniteNumber(value: unknown): number | null {
  const n = typeof value === "number" ? value : typeof value === "string" ? Number(value) : NaN;
  return Number.isFinite(n) ? n : null;
}

function coerceZone(value: unknown): ValuationRiverZoneVM {
  const text = typeof value === "string" ? value.trim().toLowerCase() : "";
  return (ZONE_VALUES as readonly string[]).includes(text) ? (text as ValuationRiverZoneVM) : "unknown";
}

function adaptWarnings(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .slice(0, MAX_WARNINGS)
    .map(sanitizeText)
    .filter((item): item is string => Boolean(item));
}

function coerceEpsKind(value: unknown): ValuationRiverEpsKindVM {
  const text = typeof value === "string" ? value.trim().toLowerCase() : "";
  return text === "implied" || text === "reported" ? text : "unavailable";
}

function adaptEpsStat(raw: unknown): ValuationRiverEpsStatVM | null {
  if (typeof raw !== "object" || raw === null) return null;
  const row = raw as Record<string, unknown>;
  const value = toFiniteNumber(row.value);
  if (value === null) return null;
  const period = typeof row.period === "string" ? row.period : "unavailable";
  const source = typeof row.source === "string" ? row.source : "unavailable";
  return { value, period, source };
}

function adaptCodes(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((item): item is string => typeof item === "string")
    .slice(0, MAX_WARNINGS);
}

function adaptBandMultiples(value: unknown): number[] {
  if (!Array.isArray(value)) return [];
  return value
    .map(toFiniteNumber)
    .filter((n): n is number => n !== null)
    .sort((a, b) => a - b);
}

function adaptPoint(raw: unknown, bandMultiples: number[]): ValuationRiverPointVM | null {
  if (typeof raw !== "object" || raw === null) return null;
  const row = raw as Record<string, unknown>;
  const date = typeof row.date === "string" ? row.date : null;
  const close = toFiniteNumber(row.close);
  if (!date || close === null) return null;

  const bandsRaw = pick(row, ["bands"]);
  const bands: ValuationRiverBandVM[] = [];
  if (typeof bandsRaw === "object" && bandsRaw !== null) {
    const bandsObj = bandsRaw as Record<string, unknown>;
    for (const multiple of bandMultiples) {
      const value = toFiniteNumber(pick(bandsObj, [`per${multiple}`, `per_${multiple}`]));
      if (value !== null) bands.push({ multiple, value });
    }
  }

  return {
    date,
    close,
    per: toFiniteNumber(pick(row, ["per"])),
    impliedEps: toFiniteNumber(pick(row, ["impliedEps", "implied_eps"])),
    bands,
  };
}

/**
 * Adapt a raw valuationRiverSnapshot payload into the chart view model.
 * Returns an explicit `{ enabled: false, reason }` state — never null and
 * never a crash — for missing, malformed, or `enabled: false` payloads, so
 * the component can always render *something* deterministic (a fallback
 * card) rather than needing a separate "missing" branch upstream.
 */
export function adaptValuationRiverSnapshot(rawValue: unknown): ValuationRiverVM {
  const fallback = (
    market: unknown,
    reason: string,
    epsActual: ValuationRiverEpsStatVM | null = null,
    epsForward: ValuationRiverEpsStatVM | null = null,
  ): ValuationRiverUnavailableVM => ({
    enabled: false,
    market: typeof market === "string" ? market : null,
    reason,
    epsActual,
    epsForward,
  });

  if (typeof rawValue !== "object" || rawValue === null || Array.isArray(rawValue)) {
    return fallback(null, "尚無估值河流圖資料");
  }
  const raw = rawValue as Record<string, unknown>;

  const rawCurrent = pick(raw, ["current"]);
  const rawCurrentObj = typeof rawCurrent === "object" && rawCurrent !== null ? (rawCurrent as Record<string, unknown>) : {};
  const fallbackEpsActual = adaptEpsStat(pick(rawCurrentObj, ["epsActual", "eps_actual"]));
  const fallbackEpsForward = adaptEpsStat(pick(rawCurrentObj, ["epsForward", "eps_forward"]));

  if (raw.enabled !== true) {
    const qualityRaw = pick(raw, ["quality"]);
    const quality = typeof qualityRaw === "object" && qualityRaw !== null ? (qualityRaw as Record<string, unknown>) : {};
    const warnings = adaptWarnings(pick(quality, ["warnings"]));
    const reason = warnings[0] || "此標的暫不支援歷史估值河流圖";
    return fallback(pick(raw, ["market"]), reason, fallbackEpsActual, fallbackEpsForward);
  }

  const symbol = typeof raw.symbol === "string" ? raw.symbol : "";
  const currency = typeof raw.currency === "string" ? raw.currency : "TWD";
  const bandMultiples = adaptBandMultiples(pick(raw, ["bandMultiples", "band_multiples"]));
  const neutralMultiple = toFiniteNumber(pick(raw, ["neutralMultiple", "neutral_multiple"]));

  const pointsRaw = pick(raw, ["points"]);
  const points = Array.isArray(pointsRaw)
    ? pointsRaw
        .map((p) => adaptPoint(p, bandMultiples))
        .filter((p): p is ValuationRiverPointVM => p !== null)
    : [];

  if (points.length === 0) {
    return fallback(pick(raw, ["market"]), "河流圖資料筆數不足，暫不顯示", fallbackEpsActual, fallbackEpsForward);
  }

  const rangeRaw = pick(raw, ["range"]);
  const range = typeof rangeRaw === "object" && rangeRaw !== null ? (rangeRaw as Record<string, unknown>) : {};

  const currentRaw = pick(raw, ["current"]);
  const currentObj = typeof currentRaw === "object" && currentRaw !== null ? (currentRaw as Record<string, unknown>) : {};
  const current: ValuationRiverCurrentVM = {
    close: toFiniteNumber(pick(currentObj, ["close"])),
    per: toFiniteNumber(pick(currentObj, ["per"])),
    pbr: toFiniteNumber(pick(currentObj, ["pbr"])),
    impliedEps: toFiniteNumber(pick(currentObj, ["impliedEps", "implied_eps"])),
    impliedBvps: toFiniteNumber(pick(currentObj, ["impliedBvps", "implied_bvps"])),
    zone: coerceZone(pick(currentObj, ["zone"])),
    epsActual: adaptEpsStat(pick(currentObj, ["epsActual", "eps_actual"])),
    epsForward: adaptEpsStat(pick(currentObj, ["epsForward", "eps_forward"])),
  };

  const qualityRaw = pick(raw, ["quality"]);
  const quality = typeof qualityRaw === "object" && qualityRaw !== null ? (qualityRaw as Record<string, unknown>) : {};
  const status = typeof quality.status === "string" ? quality.status : "ok";

  return {
    enabled: true,
    symbol,
    currency,
    method: typeof raw.method === "string" ? raw.method : "unavailable",
    epsKind: coerceEpsKind(pick(raw, ["epsKind", "eps_kind"])),
    startDate: typeof pick(range, ["startDate", "start_date"]) === "string" ? (pick(range, ["startDate", "start_date"]) as string) : null,
    endDate: typeof pick(range, ["endDate", "end_date"]) === "string" ? (pick(range, ["endDate", "end_date"]) as string) : null,
    tradingDays: toFiniteNumber(pick(range, ["tradingDays", "trading_days"])) ?? points.length,
    bandMultiples,
    neutralMultiple,
    points,
    current,
    isPartial: status === "partial",
    warnings: adaptWarnings(pick(quality, ["warnings"])),
    codes: adaptCodes(pick(quality, ["codes"])),
    methodologyNote:
      sanitizeText(pick(quality, ["methodologyNote", "methodology_note"])) ||
      "倍數帶為固定視覺參考基準，非估值結論、目標價或買賣建議。",
  };
}
