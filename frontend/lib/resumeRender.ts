/** Heuristic plain-text resume parser shared by the PDF, Word, and LaTeX
 * exporters, so all three render from one structural understanding of the
 * resume instead of dumping raw text. ponytail: regex/heading-based, not an
 * AI call — deterministic, free, and can't hallucinate content, but a resume
 * with unconventional headings will fall back to plain paragraphs for that
 * section rather than misrendering it as something it's not. */

export interface ResumeEntry {
  headerLines: string[]; // e.g. job title, company/location, dates — rendered bold/italic
  bullets: string[];
}

export interface ResumeSection {
  heading: string;
  kind: "summary" | "skills" | "entries";
  paragraph?: string; // for "summary"
  skillLines?: string[]; // for "skills" — raw "Category: values" lines
  entries?: ResumeEntry[]; // for "entries" (Education/Experience/Projects/etc.)
}

export interface ParsedResume {
  name: string;
  contactLine: string;
  sections: ResumeSection[];
}

const KNOWN_HEADINGS = [
  "summary",
  "objective",
  "profile",
  "education",
  "experience",
  "work experience",
  "professional experience",
  "projects",
  "additional projects",
  "skills",
  "technical skills",
  "core competencies",
  "certifications",
  "awards",
];

function isKnownHeading(line: string): boolean {
  const trimmed = line.trim();
  if (!trimmed || trimmed.length > 40) return false;
  const lower = trimmed.toLowerCase().replace(/[^a-z ]/g, "").trim();
  return KNOWN_HEADINGS.some((h) => lower === h || lower.startsWith(h));
}

export function isHeadingLine(line: string): boolean {
  const trimmed = line.trim();
  if (!trimmed || trimmed.length > 40) return false;
  if (isKnownHeading(trimmed)) return true;
  return trimmed === trimmed.toUpperCase() && /[A-Z]/.test(trimmed) && trimmed.split(/\s+/).length <= 4;
}

function isBulletLine(line: string): boolean {
  return /^\s*[-•*]\s+/.test(line);
}

function stripBullet(line: string): string {
  return line.replace(/^\s*[-•*]\s+/, "").trim();
}

function sectionKind(heading: string): "summary" | "skills" | "entries" {
  const lower = heading.toLowerCase();
  if (/summary|objective|profile/.test(lower)) return "summary";
  if (/skill|competenc/.test(lower)) return "skills";
  return "entries";
}

function groupEntries(lines: string[]): ResumeEntry[] {
  const entries: ResumeEntry[] = [];
  let current: ResumeEntry | null = null;

  for (const raw of lines) {
    const line = raw.trim();
    if (!line) continue;
    if (isBulletLine(line)) {
      if (!current) {
        current = { headerLines: [], bullets: [] };
        entries.push(current);
      }
      current.bullets.push(stripBullet(line));
    } else {
      // A non-bullet line after a run of bullets starts a new entry.
      if (!current || current.bullets.length > 0) {
        current = { headerLines: [], bullets: [] };
        entries.push(current);
      }
      current.headerLines.push(line);
    }
  }
  return entries;
}

export function parseResumeSections(text: string): ParsedResume {
  const lines = text.split("\n");
  const headerLines: string[] = [];
  const rawSections: { heading: string; lines: string[] }[] = [];
  let current: { heading: string; lines: string[] } | null = null;
  let sawFirstHeading = false;

  for (const rawLine of lines) {
    const line = rawLine.replace(/\r$/, "");
    const trimmed = line.trim();

    // The first ~2 non-empty lines are the name + contact line, even if they
    // read as "all caps short line" (e.g. "VIGNESH GOVINDU") — only an
    // explicit known heading keyword can end the header early.
    if (!sawFirstHeading && headerLines.length < 2 && !isKnownHeading(trimmed)) {
      if (trimmed) headerLines.push(trimmed);
      continue;
    }

    if (isHeadingLine(line)) {
      sawFirstHeading = true;
      current = { heading: trimmed, lines: [] };
      rawSections.push(current);
      continue;
    }
    if (!sawFirstHeading) {
      if (trimmed) headerLines.push(trimmed);
    } else if (current) {
      current.lines.push(line);
    }
  }

  const sections: ResumeSection[] = rawSections.map(({ heading, lines: secLines }) => {
    const kind = sectionKind(heading);
    if (kind === "summary") {
      return { heading, kind, paragraph: secLines.map((l) => l.trim()).filter(Boolean).join(" ") };
    }
    if (kind === "skills") {
      return { heading, kind, skillLines: secLines.map((l) => l.trim()).filter(Boolean) };
    }
    return { heading, kind, entries: groupEntries(secLines) };
  });

  return {
    name: headerLines[0] ?? "",
    contactLine: headerLines.slice(1).join(" "),
    sections,
  };
}
