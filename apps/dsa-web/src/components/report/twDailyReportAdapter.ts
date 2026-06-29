export type TwDailyTone = 'gain' | 'loss' | 'neutral' | 'missing';

export type TwDailyRow = {
  label: string;
  code?: string;
  value: string;
  tone: TwDailyTone;
};

export type TwDailyReportModel = {
  title: string;
  dataDate: string | null;
  source: string;
  dataStatus: string | null;
  highlights: string[];
  summary: string[];
  indices: TwDailyRow[];
  institutional: TwDailyRow[];
  margin: TwDailyRow[];
  representatives: TwDailyRow[];
  risks: string[];
};

const SECTION_HEADING_PATTERN = /^#{1,3}\s+(.+?)\s*$/u;
const BULLET_PATTERN = /^\s*[-*]\s+/u;
const MARKET_REVIEW_TITLE_PATTERN = /台股大盤回顧/u;
const PIPELINE_STATUS_PATTERN = /(?:必要指標|資料完整|資料缺失|分析資料不完整)/u;

const stripMarkdown = (value: string): string => value
  .replace(/\*\*/g, '')
  .replace(/`/g, '')
  .replace(/[🟢🔴]/gu, '')
  .replace(/\s+/g, ' ')
  .trim();

const normalizeLine = (line: string): string => stripMarkdown(
  line
    .replace(BULLET_PATTERN, '')
    .replace(/^>\s*/u, '')
);

const detectTone = (text: string): TwDailyTone => {
  if (/資料暫不可用|缺失|不完整|略過|N\/A/u.test(text)) return 'missing';
  if (/(🔴|▼|\s-\d|\(-\d|\s-\d+\.\d)/u.test(text)) return 'loss';
  if (/(🟢|▲|\+\d|\(\+\d)/u.test(text)) return 'gain';
  return 'neutral';
};

const splitSections = (markdown: string): Array<{ title: string; body: string }> => {
  const sections: Array<{ title: string; body: string }> = [];
  let currentTitle = '';
  let currentBody: string[] = [];

  for (const line of markdown.split(/\r?\n/)) {
    const heading = SECTION_HEADING_PATTERN.exec(line.trim());
    if (heading) {
      if (currentTitle || currentBody.some((item) => item.trim())) {
        sections.push({ title: currentTitle, body: currentBody.join('\n').trim() });
      }
      currentTitle = stripMarkdown(heading[1]);
      currentBody = [];
      continue;
    }
    currentBody.push(line);
  }

  if (currentTitle || currentBody.some((item) => item.trim())) {
    sections.push({ title: currentTitle, body: currentBody.join('\n').trim() });
  }

  return sections;
};

const sectionBody = (sections: Array<{ title: string; body: string }>, title: string): string => (
  sections.find((section) => section.title.includes(title))?.body ?? ''
);

const textLines = (body: string): string[] => body
  .split(/\r?\n/)
  .map(normalizeLine)
  .filter(Boolean);

const bulletLines = (body: string): string[] => body
  .split(/\r?\n/)
  .filter((line) => BULLET_PATTERN.test(line))
  .map(normalizeLine)
  .filter(Boolean);

const parseRows = (body: string): TwDailyRow[] => bulletLines(body).map((line) => {
  const [rawLabel, ...rest] = line.split(/[:：]/u);
  const labelText = stripMarkdown(rawLabel || line);
  const valueText = stripMarkdown(rest.join('：') || line);
  const codeMatch = /（(.+?)）/u.exec(labelText);
  return {
    label: labelText.replace(/（.+?）/u, '').trim(),
    code: codeMatch?.[1],
    value: valueText,
    tone: detectTone(line),
  };
});

const firstUseful = (...groups: string[][]): string[] => {
  const output: string[] = [];
  for (const group of groups) {
    for (const item of group) {
      if (!item || PIPELINE_STATUS_PATTERN.test(item)) continue;
      output.push(item);
      if (output.length >= 5) return output;
    }
  }
  return output;
};

const rowHighlights = (rows: TwDailyRow[]): string[] => rows.map((row) => (
  row.code ? `${row.label}（${row.code}）：${row.value}` : `${row.label}：${row.value}`
));

export const parseTwDailyReportMarkdown = (markdown: string): TwDailyReportModel | null => {
  if (!MARKET_REVIEW_TITLE_PATTERN.test(markdown)) return null;

  const sections = splitSections(markdown);
  const summaryBody = sectionBody(sections, '今日盤勢摘要');
  const indexBody = sectionBody(sections, '指數表現');
  const institutionalBody = sectionBody(sections, '法人與資金面');
  const marginBody = sectionBody(sections, '融資融券');
  const representativeBody = sectionBody(sections, '0050');
  const riskBody = sectionBody(sections, '風險');

  const indices = parseRows(indexBody);
  const institutional = parseRows(institutionalBody);
  const margin = parseRows(marginBody);
  const representatives = parseRows(representativeBody);

  if (!indices.length || !institutional.length || !margin.length) return null;

  const dataDate = /資料日期[:：]\s*([0-9]{4}-[0-9]{2}-[0-9]{2})/u.exec(markdown)?.[1] ?? null;
  const summaryLines = textLines(summaryBody);
  const dataStatus = summaryLines.find((line) => PIPELINE_STATUS_PATTERN.test(line)) ?? null;
  const summary = summaryLines.filter((line) => !PIPELINE_STATUS_PATTERN.test(line));
  const risks = bulletLines(riskBody);
  const highlights = firstUseful(
    summary,
    rowHighlights(indices),
    rowHighlights(institutional),
    rowHighlights(margin),
    risks,
  );

  return {
    title: '台股大盤回顧',
    dataDate,
    source: 'FinMind',
    dataStatus,
    highlights,
    summary,
    indices,
    institutional,
    margin,
    representatives,
    risks,
  };
};
