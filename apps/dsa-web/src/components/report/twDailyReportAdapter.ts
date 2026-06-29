import type { AnalysisReport } from '../../types/analysis';

export type TwDailyTone =
  | 'tw-gain'
  | 'tw-loss'
  | 'tw-buy'
  | 'tw-sell'
  | 'net-buy'
  | 'net-sell'
  | 'neutral'
  | 'risk'
  | 'missing';

export interface TwDailyMetric {
  label: string;
  value: string;
  tone: TwDailyTone;
}

export interface TwDailyRow {
  label: string;
  code?: string;
  value: string;
  tone: TwDailyTone;
  meta?: string;
  metrics?: TwDailyMetric[];
  notes?: string[];
}

export interface TwDailyReportModel {
  title: string;
  dataDate: string;
  source: string;
  dataStatus: string;
  statusItems?: string[];
  highlights: string[];
  summary: string;
  indices: TwDailyRow[];
  institutional: TwDailyRow[];
  margin: TwDailyRow[];
  representatives: TwDailyRow[];
  risks: string[];
}

type UnknownRecord = Record<string, unknown>;

const asRecord = (value: unknown): UnknownRecord | null => (
  value && typeof value === 'object' && !Array.isArray(value) ? value as UnknownRecord : null
);

const asArray = (value: unknown): UnknownRecord[] => (
  Array.isArray(value) ? value.map(asRecord).filter((item): item is UnknownRecord => Boolean(item)) : []
);

const firstValue = (record: UnknownRecord, keys: string[]): unknown => {
  for (const key of keys) {
    if (record[key] !== undefined && record[key] !== null) return record[key];
  }
  return undefined;
};

const stringValue = (record: UnknownRecord, keys: string[], fallback = ''): string => {
  const value = firstValue(record, keys);
  return value === undefined || value === null ? fallback : String(value);
};

const numberValue = (record: UnknownRecord, keys: string[]): number | null => {
  const value = firstValue(record, keys);
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value.replace(/,/g, ''));
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
};

const normalizeDisplayZero = (value: number, digits = 2): number => (
  Math.abs(value) < 0.5 * (10 ** -digits) ? 0 : value
);

const formatNumber = (value: number, digits = 2): string => (
  normalizeDisplayZero(value, digits).toLocaleString('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
);

const formatSignedNumber = (value: number, digits = 2): string => {
  const normalized = normalizeDisplayZero(value, digits);
  const sign = normalized > 0 ? '+' : '';
  return `${sign}${formatNumber(normalized, digits)}`;
};

const formatPercent = (value: number | null): string => (
  value === null ? '—' : `${formatSignedNumber(value, 2)}%`
);

const normalizeUnitValue = (value: number | null, divisor: number | null, unit?: string | null): number | null => {
  if (value === null) return null;
  const epsilon = unit === 'TWD' && divisor === 100000000 ? divisor * 0.05 : 1e-9;
  return Math.abs(value) < epsilon ? 0 : value;
};

const formatUnitValue = (value: number | null, divisor: number | null, unit?: string | null): string => {
  const normalized = normalizeUnitValue(value, divisor, unit);
  if (normalized === null) return '—';
  if (unit === 'TWD' && divisor === 100000000) {
    return `${formatNumber(normalized / divisor, 1)} 億`;
  }
  if (unit === 'shares') {
    return `${formatNumber(normalized, 0)} 股`;
  }
  return formatNumber(normalized, Number.isInteger(normalized) ? 0 : 2);
};

export const getTwPriceTone = (change: number | null | undefined): TwDailyTone => {
  if (typeof change !== 'number' || !Number.isFinite(change)) return 'neutral';
  if (change > 0) return 'tw-gain';
  if (change < 0) return 'tw-loss';
  return 'neutral';
};

export const getTwInstitutionalFieldTone = (field: 'buy' | 'sell', value: number | null | undefined): TwDailyTone => {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 'missing';
  if (value === 0) return 'neutral';
  return field === 'buy' ? 'tw-buy' : 'tw-sell';
};

export const getTwNetFlowTone = (net: number | null | undefined): TwDailyTone => {
  if (typeof net !== 'number' || !Number.isFinite(net)) return 'missing';
  if (net > 0) return 'net-buy';
  if (net < 0) return 'net-sell';
  return 'neutral';
};

export const getTwMarginTone = (row: UnknownRecord): TwDailyTone => (
  stringValue(row, ['semanticType', 'semantic_type']) === 'risk_or_leverage' ? 'risk' : 'neutral'
);

const institutionalLabel = (name: string): string => ({
  Foreign_Investor: '外資',
  Investment_Trust: '投信',
  Dealer: '自營商',
  Dealer_self: '自營商自行買賣',
  Dealer_Self: '自營商自行買賣',
  Foreign_Dealer_Self: '外資自營商',
  Dealer_Hedging: '自營商避險',
  total: '合計',
  Total: '合計',
}[name] || '未知法人類別');

const marginLabel = (name: string): string => ({
  MarginPurchase: '融資',
  ShortSale: '融券',
  MarginPurchaseMoney: '融資餘額',
  ShortSaleMoney: '融券餘額',
  ShortSaleVolume: '融券張數',
}[name] || '融資融券');

const FIELD_LABELS: Record<string, string> = {
  PER: 'PER',
  PBR: 'PBR',
  dividend_yield: '股息殖利率',
};

const SYMBOL_LABELS: Record<string, string> = {
  '0050': '0050',
  '006208': '006208',
  '2330': '2330',
};

const formatDatasetStatus = (datasets: unknown): string | null => {
  if (!Array.isArray(datasets) || !datasets.length) return null;
  if (datasets.every((item) => typeof item === 'string')) {
    return `資料集：${datasets.join('、')}`;
  }
  return `資料集：${datasets.length} 項`;
};

const formatMissingFields = (missing: unknown): string[] => {
  if (!Array.isArray(missing) || !missing.length) return [];
  const byRepresentative = new Map<string, Set<string>>();
  const other: string[] = [];

  for (const item of missing) {
    const text = String(item);
    const match = /^representatives\.([^.]+)\.([^.]+)$/u.exec(text);
    if (!match) {
      other.push(text.replace(/_/g, ' '));
      continue;
    }
    const [, symbol, field] = match;
    const fields = byRepresentative.get(symbol) || new Set<string>();
    fields.add(field);
    byRepresentative.set(symbol, fields);
  }

  const items: string[] = [];
  for (const [symbol, fields] of byRepresentative.entries()) {
    const hasValuationGap = ['PER', 'PBR', 'dividend_yield'].every((field) => fields.has(field));
    if (hasValuationGap && (symbol === '0050' || symbol === '006208')) {
      items.push(`${SYMBOL_LABELS[symbol] || symbol}：ETF 估值資料未提供`);
    } else {
      items.push(`${SYMBOL_LABELS[symbol] || symbol}：${Array.from(fields).map((field) => FIELD_LABELS[field] || field).join('、')} 未提供`);
    }
  }
  return [...items, ...other];
};

const formatPartialFailures = (partial: unknown): string[] => {
  if (!Array.isArray(partial) || !partial.length) return [];
  const perSymbols = partial
    .map((item) => /^per_(.+)$/u.exec(String(item))?.[1])
    .filter((symbol): symbol is string => Boolean(symbol));
  const items: string[] = [];
  if (perSymbols.length) {
    items.push(`PER 資料：${perSymbols.map((symbol) => SYMBOL_LABELS[symbol] || symbol).join('、')} 未提供`);
  }
  const other = partial.filter((item) => !/^per_/u.test(String(item))).map((item) => String(item).replace(/_/g, ' '));
  return [...items, ...other];
};

const statusItemsFromSnapshot = (snapshot: UnknownRecord): string[] => {
  const items: string[] = [];
  const datasets = firstValue(snapshot, ['datasets']);
  const datasetStatus = formatDatasetStatus(datasets);
  if (datasetStatus) items.push(datasetStatus);
  const dataStatus = asRecord(firstValue(snapshot, ['dataStatus', 'data_status'])) || {};
  const missing = firstValue(dataStatus, ['missingFields', 'missing_fields']);
  const stale = firstValue(dataStatus, ['staleFields', 'stale_fields']);
  const partial = firstValue(dataStatus, ['partialFailures', 'partial_failures']);
  items.push(...formatMissingFields(missing));
  if (Array.isArray(stale) && stale.length) items.push(`可能過期：${stale.map(String).join('、')}`);
  items.push(...formatPartialFailures(partial));
  return items;
};

export function buildTwDailyReportFromSnapshot(value: unknown): TwDailyReportModel | null {
  const snapshot = asRecord(value);
  if (!snapshot) return null;
  const dataDate = stringValue(snapshot, ['dataDate', 'data_date']);
  const source = stringValue(snapshot, ['source'], 'finmind').toLowerCase() === 'finmind' ? 'FinMind' : stringValue(snapshot, ['source'], 'FinMind');
  const indices = asArray(firstValue(snapshot, ['indices']));
  const institutionalFlows = asArray(firstValue(snapshot, ['institutionalFlows', 'institutional_flows']));
  const marginShort = asArray(firstValue(snapshot, ['marginShort', 'margin_short']));
  const representatives = asArray(firstValue(snapshot, ['representatives']));

  if (!dataDate || (!indices.length && !institutionalFlows.length && !marginShort.length && !representatives.length)) {
    return null;
  }

  const indexRows = indices.map((row): TwDailyRow => {
    const valueNumber = numberValue(row, ['value', 'close']);
    const change = numberValue(row, ['change']);
    const changePct = numberValue(row, ['changePct', 'change_pct']);
    return {
      label: stringValue(row, ['name'], stringValue(row, ['symbol'], '指數')),
      code: stringValue(row, ['symbol', 'code']),
      value: `${valueNumber === null ? '—' : `${formatNumber(valueNumber, 2)} 點`} ${change === null ? '' : formatSignedNumber(change, 2)}（${formatPercent(changePct)}）`.trim(),
      tone: getTwPriceTone(change),
      meta: stringValue(row, ['dataDate', 'data_date'], dataDate),
    };
  });

  const institutionalRows = institutionalFlows.map((row): TwDailyRow => {
    const buy = numberValue(row, ['buy']);
    const sell = numberValue(row, ['sell']);
    const net = numberValue(row, ['net']);
    const divisor = numberValue(row, ['displayDivisor', 'display_divisor']);
    const unit = stringValue(row, ['unit']);
    const normalizedBuy = normalizeUnitValue(buy, divisor, unit);
    const normalizedSell = normalizeUnitValue(sell, divisor, unit);
    const normalizedNet = normalizeUnitValue(net, divisor, unit);
    const isAllZero = normalizedBuy === 0 && normalizedSell === 0 && normalizedNet === 0;
    const netLabel = normalizedNet === null || normalizedNet === 0 ? '淨額' : normalizedNet > 0 ? '淨買超' : '淨賣超';
    return {
      label: institutionalLabel(stringValue(row, ['name'], '法人')),
      value: `${netLabel} ${formatUnitValue(normalizedNet === null ? null : Math.abs(normalizedNet), divisor, unit)}`,
      tone: getTwNetFlowTone(normalizedNet),
      meta: stringValue(row, ['dataDate', 'data_date'], dataDate),
      metrics: isAllZero ? [] : [
        { label: '買', value: `買 ${formatUnitValue(normalizedBuy, divisor, unit)}`, tone: getTwInstitutionalFieldTone('buy', normalizedBuy) },
        { label: '賣', value: `賣 ${formatUnitValue(normalizedSell, divisor, unit)}`, tone: getTwInstitutionalFieldTone('sell', normalizedSell) },
      ],
    };
  });

  const marginRows = marginShort.map((row): TwDailyRow => {
    const today = numberValue(row, ['todayBalance', 'today_balance']);
    const change = numberValue(row, ['change']);
    const divisor = numberValue(row, ['displayDivisor', 'display_divisor']);
    const unit = stringValue(row, ['unit']);
    return {
      label: marginLabel(stringValue(row, ['name'], '融資融券')),
      value: `餘額 ${formatUnitValue(today, divisor, unit)}，變化 ${formatUnitValue(change, divisor, unit)}`,
      tone: getTwMarginTone(row),
      meta: stringValue(row, ['dataDate', 'data_date'], dataDate),
    };
  });

  const representativeRows = representatives.map((row): TwDailyRow => {
    const close = numberValue(row, ['close']);
    const change = numberValue(row, ['change']);
    const changePct = numberValue(row, ['changePct', 'change_pct']);
    const volume = numberValue(row, ['volume']);
    const turnover = numberValue(row, ['turnover', 'tradingTurnover', 'trading_turnover']);
    const per = numberValue(row, ['PER', 'per']);
    const pbr = numberValue(row, ['PBR', 'pbr']);
    const dividendYield = numberValue(row, ['dividendYield', 'dividend_yield']);
    const valuationAsOf = stringValue(row, ['valuationAsOf', 'valuation_as_of']);
    const valuationAvailable = per !== null || pbr !== null || dividendYield !== null;
    const metaParts = [
      stringValue(row, ['dataDate', 'data_date'], dataDate),
      volume === null ? null : `量 ${formatNumber(volume, 0)}`,
      turnover === null ? null : `成交值 ${formatUnitValue(turnover, 100000000, 'TWD')}`,
      valuationAvailable && per !== null ? `PER ${formatNumber(per, 2)}` : null,
      valuationAvailable && pbr !== null ? `PBR ${formatNumber(pbr, 2)}` : null,
      valuationAvailable && dividendYield !== null ? `殖利率 ${formatNumber(dividendYield, 2)}%` : null,
      valuationAsOf ? `估值日 ${valuationAsOf}` : null,
    ].filter((part): part is string => Boolean(part));
    return {
      label: stringValue(row, ['name'], stringValue(row, ['symbol'], '代表標的')),
      code: stringValue(row, ['symbol', 'code']),
      value: `收盤 ${close === null ? '—' : formatNumber(close, 2)} ${change === null ? '' : formatSignedNumber(change, 2)}（${formatPercent(changePct)}）`.trim(),
      tone: getTwPriceTone(change),
      meta: metaParts.join(' · '),
      notes: valuationAvailable ? [] : ['估值資料未提供'],
    };
  });

  const highlights = [
    indexRows[0] ? `${indexRows[0].label} ${indexRows[0].value}` : null,
    institutionalRows[0] ? `${institutionalRows[0].label} ${institutionalRows[0].value}` : null,
    representativeRows.find((row) => row.code === '006208') ? '代表標的新增 006208 富邦台50 觀察列。' : null,
  ].filter((item): item is string => Boolean(item));

  return {
    title: '台股大盤回顧',
    dataDate,
    source,
    dataStatus: statusItemsFromSnapshot(snapshot).length ? '部分資料需留意' : '結構化快照資料已載入',
    statusItems: statusItemsFromSnapshot(snapshot),
    highlights: highlights.length ? highlights : ['本次台股日報已載入結構化 FinMind 快照。'],
    summary: '主要敘述已整理至今日重點與右側資料表。',
    indices: indexRows,
    institutional: institutionalRows,
    margin: marginRows,
    representatives: representativeRows,
    risks: statusItemsFromSnapshot(snapshot).filter((item) => item.startsWith('缺漏') || item.startsWith('部分失敗')),
  };
}

export const extractTwDailySnapshotFromReport = (report?: AnalysisReport | null): unknown | null => {
  const details = report?.details;
  if (!details) return null;
  const rawResult = asRecord(details.rawResult);
  const contextSnapshot = asRecord(details.contextSnapshot);
  const rawDirect = rawResult ? firstValue(rawResult, ['twDailySnapshot', 'tw_daily_snapshot']) : null;
  if (rawDirect) return rawDirect;
  const rawMarketSnapshots = rawResult ? asRecord(firstValue(rawResult, ['marketLightSnapshots', 'market_light_snapshots'])) : null;
  const contextMarketSnapshots = contextSnapshot ? asRecord(firstValue(contextSnapshot, ['marketLightSnapshots', 'market_light_snapshots'])) : null;
  const marketSnapshots = rawMarketSnapshots || contextMarketSnapshots;
  const twSnapshot = marketSnapshots ? asRecord(firstValue(marketSnapshots, ['tw', 'TW'])) : null;
  return twSnapshot ? firstValue(twSnapshot, ['twDailySnapshot', 'tw_daily_snapshot']) ?? null : null;
};

const LINE_SECTION_MAP: Array<[keyof Pick<TwDailyReportModel, 'indices' | 'institutional' | 'margin' | 'representatives' | 'risks'>, RegExp]> = [
  ['indices', /^-\s+(.+?)（([^）]+)）：(.+)$/u],
  ['institutional', /^-\s+(.+?)：(.+)$/u],
  ['margin', /^-\s+(.+?)：(.+)$/u],
  ['representatives', /^-\s+(.+?)（([^）]+)）：(.+)$/u],
  ['risks', /^-\s+(.+)$/u],
];

const REQUIRED_HEADINGS = ['台股大盤回顧', '指數表現', '法人與資金面', '融資融券觀察'];

const cleanValue = (value: string): string => value.replace(/[🟢🔴]/gu, '').replace(/\s+/g, ' ').trim();

const detectTone = (value: string): TwDailyTone => {
  if (/資料不足|暫不可用|—/.test(value)) return 'missing';
  if (/[▲+]/.test(value) && !/[▼]/.test(value)) return 'tw-gain';
  if (/[▼-]/.test(value)) return 'tw-loss';
  return 'neutral';
};

const extractDate = (markdown: string): string => {
  const match = /資料日期[:：]\s*([0-9]{4}-[0-9]{2}-[0-9]{2})/u.exec(markdown);
  return match?.[1] ?? '—';
};

const extractDataStatus = (markdown: string): string => {
  const statusLine = markdown.split(/\r?\n/).find((line) => /必要指標|資料完整|資料不足/u.test(line));
  return statusLine ? statusLine.replace(/^[-*>\s]+/u, '').trim() : '資料狀態未標示';
};

const pushRow = (target: TwDailyRow[], line: string, pattern: RegExp): void => {
  const match = pattern.exec(line.trim());
  if (!match) return;
  if (pattern.source.includes('（')) {
    target.push({
      label: match[1].trim(),
      code: match[2].trim(),
      value: cleanValue(match[3]),
      tone: detectTone(match[3]),
    });
    return;
  }
  target.push({
    label: match[1].trim(),
    value: cleanValue(match[2]),
    tone: detectTone(match[2]),
  });
};

export function parseTwDailyReportMarkdown(markdown: string): TwDailyReportModel | null {
  if (!markdown || !REQUIRED_HEADINGS.every((heading) => markdown.includes(heading))) {
    return null;
  }

  const report: TwDailyReportModel = {
    title: '台股大盤回顧',
    dataDate: extractDate(markdown),
    source: /finmind/i.test(markdown) ? 'FinMind' : 'FinMind',
    dataStatus: extractDataStatus(markdown),
    highlights: [],
    summary: '主要敘述已整理至今日重點與右側資料表。',
    indices: [],
    institutional: [],
    margin: [],
    representatives: [],
    risks: [],
  };

  let section: keyof Pick<TwDailyReportModel, 'indices' | 'institutional' | 'margin' | 'representatives' | 'risks'> | 'summary' | null = null;

  for (const rawLine of markdown.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line) continue;
    if (/^##\s+今日盤勢摘要/u.test(line)) { section = 'summary'; continue; }
    if (/^##\s+指數表現/u.test(line)) { section = 'indices'; continue; }
    if (/^##\s+法人與資金面/u.test(line)) { section = 'institutional'; continue; }
    if (/^##\s+融資融券觀察/u.test(line)) { section = 'margin'; continue; }
    if (/^##\s+0050\s*\/\s*臺積電參考/u.test(line)) { section = 'representatives'; continue; }
    if (/^##\s+風險/u.test(line)) { section = 'risks'; continue; }

    if (section === 'summary' && !line.startsWith('#') && !line.startsWith('>')) {
      report.highlights.push(line.replace(/^[-*]\s*/u, ''));
      continue;
    }
    if (!section || section === 'summary') continue;

    const target = report[section];
    const config = LINE_SECTION_MAP.find(([name]) => name === section);
    if (!config) continue;
    if (section === 'risks') {
      const match = config[1].exec(line);
      if (match) report.risks.push(match[1].trim());
      continue;
    }
    pushRow(target as TwDailyRow[], line, config[1]);
  }

  if (!report.indices.length || !report.institutional.length || !report.margin.length) {
    return null;
  }

  if (!report.highlights.length) {
    report.highlights = [
      report.indices[0] ? `${report.indices[0].label}：${report.indices[0].value}` : null,
      report.institutional[0] ? `${report.institutional[0].label}：${report.institutional[0].value}` : null,
      report.margin[0] ? `${report.margin[0].label}：${report.margin[0].value}` : null,
    ].filter((item): item is string => Boolean(item));
  }

  return report;
}
