import { ProjectSuggestion, TailoredBullet } from "./api";
import { buildLatexResume } from "./latex";
import { isHeadingLine, ParsedResume, parseResumeSections } from "./resumeRender";

/** Substitute each tailored bullet back into the resume text (best-effort verbatim
 * match), and replace the resume's Projects section with the current selection
 * of suggested projects. Bullets that can't be located verbatim are appended as
 * a suggestions section instead of being silently dropped. Selecting projects
 * is opt-in — the Projects section is only touched once at least one is
 * selected (or was previously selected — see replaceProjectsSection). */
export function buildTailoredResumeText(
  resumeText: string,
  bullets: TailoredBullet[],
  selectedProjects: ProjectSuggestion[] = []
): string {
  let text = resumeText;
  const unmatched: TailoredBullet[] = [];

  for (const bullet of bullets) {
    if (text.includes(bullet.original)) {
      text = text.replace(bullet.original, bullet.tailored);
    } else {
      unmatched.push(bullet);
    }
  }

  if (unmatched.length > 0) {
    text +=
      "\n\n--- Suggested additions (could not be placed automatically) ---\n" +
      unmatched.map((b) => `- ${b.tailored}`).join("\n");
  }

  return replaceProjectsSection(text, selectedProjects);
}

function isProjectsHeadingLine(line: string): boolean {
  return isHeadingLine(line) && /project/i.test(line);
}

/** Replace the resume's Projects section (wherever it is, however it's
 * currently titled) with the current set of selected suggested projects —
 * per explicit user choice, this REPLACES the original project entries
 * rather than appending alongside them. If there's no Projects section yet,
 * one is added. If the selection is empty, the section (heading included)
 * is removed. Everything outside the Projects section is left untouched, so
 * hand-edits elsewhere in the draft survive repeated toggling. */
export function replaceProjectsSection(text: string, projects: ProjectSuggestion[]): string {
  const lines = text.split("\n");
  const startIndex = lines.findIndex((l) => isProjectsHeadingLine(l));

  const entryLines = projects.flatMap((p) => [
    p.title,
    p.covers_skills.join(", "),
    ...p.bullets.map((b) => `- ${b}`),
    "",
  ]);
  if (entryLines[entryLines.length - 1] === "") entryLines.pop();
  const newSection = projects.length > 0 ? ["Projects", ...entryLines, ""] : [];

  if (startIndex === -1) {
    if (projects.length === 0) return text;
    const base = text.replace(/\s+$/, "");
    return `${base}\n\n${newSection.join("\n")}`.replace(/\n+$/, "\n");
  }

  let endIndex = lines.length;
  for (let i = startIndex + 1; i < lines.length; i++) {
    if (isHeadingLine(lines[i])) {
      endIndex = i;
      break;
    }
  }

  return [...lines.slice(0, startIndex), ...newSection, ...lines.slice(endIndex)].join("\n");
}

function triggerDownload(filename: string, blob: Blob) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/** Structured PDF layout — centered name/contact, bold uppercase section
 * headers with a rule, bold/italic entry headers, hanging-indent bullets —
 * driven by the shared resumeRender parser instead of dumping raw text. */
export function downloadPdf(filename: string, text: string) {
  import("jspdf").then(({ default: jsPDF }) => {
    const doc = new jsPDF({ unit: "pt", format: "letter" });
    const marginX = 44;
    let marginY = 44;
    const pageWidth = doc.internal.pageSize.getWidth();
    const pageHeight = doc.internal.pageSize.getHeight();
    const maxWidth = pageWidth - marginX * 2;
    let y = marginY;

    function ensureSpace(needed: number) {
      if (y + needed > pageHeight - marginY) {
        doc.addPage();
        y = marginY;
      }
    }

    function writeParagraph(content: string, opts: { size: number; style: string; indent?: number; lineHeight?: number }) {
      doc.setFont("helvetica", opts.style);
      doc.setFontSize(opts.size);
      const indent = opts.indent ?? 0;
      const lineHeight = opts.lineHeight ?? opts.size * 1.25;
      const wrapped: string[] = doc.splitTextToSize(content, maxWidth - indent);
      for (const line of wrapped) {
        ensureSpace(lineHeight);
        doc.text(line, marginX + indent, y);
        y += lineHeight;
      }
    }

    const parsed: ParsedResume = parseResumeSections(text);

    doc.setFont("helvetica", "bold");
    doc.setFontSize(20);
    doc.text(parsed.name.toUpperCase(), pageWidth / 2, y, { align: "center" });
    y += 22;

    if (parsed.contactLine) {
      doc.setFont("helvetica", "normal");
      doc.setFontSize(9);
      const contactWrapped: string[] = doc.splitTextToSize(parsed.contactLine, maxWidth);
      for (const line of contactWrapped) {
        doc.text(line, pageWidth / 2, y, { align: "center" });
        y += 12;
      }
    }
    y += 8;

    for (const section of parsed.sections) {
      ensureSpace(24);
      doc.setFont("helvetica", "bold");
      doc.setFontSize(11);
      doc.text(section.heading.toUpperCase(), marginX, y);
      y += 3;
      doc.setLineWidth(0.75);
      doc.line(marginX, y, pageWidth - marginX, y);
      y += 12;

      if (section.kind === "summary") {
        writeParagraph(section.paragraph ?? "", { size: 9.5, style: "normal" });
      } else if (section.kind === "skills") {
        for (const raw of section.skillLines ?? []) {
          const colonIndex = raw.indexOf(":");
          if (colonIndex > -1) {
            writeParagraph(`${raw.slice(0, colonIndex + 1)} ${raw.slice(colonIndex + 1).trim()}`, {
              size: 9.5,
              style: "normal",
            });
          } else {
            writeParagraph(raw, { size: 9.5, style: "normal" });
          }
        }
      } else {
        for (const entry of section.entries ?? []) {
          entry.headerLines.forEach((headerLine, i) => {
            writeParagraph(headerLine, { size: 9.5, style: i === 0 ? "bold" : "italic" });
          });
          for (const bullet of entry.bullets) {
            writeParagraph(`•  ${bullet}`, { size: 9.5, style: "normal", indent: 10 });
          }
          y += 2;
        }
      }
      y += 6;
    }

    doc.save(filename);
  });
}

/** Structured Word export — same section/entry structure as the PDF, styled
 * with CSS. Still the zero-dependency "HTML served as application/msword"
 * trick (Word opens it natively) rather than pulling in a full OOXML library. */
export function downloadWord(filename: string, text: string) {
  const parsed: ParsedResume = parseResumeSections(text);
  const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

  const sectionsHtml = parsed.sections
    .map((section) => {
      const heading = `<h2>${esc(section.heading.toUpperCase())}</h2>`;
      if (section.kind === "summary") {
        return `${heading}<p>${esc(section.paragraph ?? "")}</p>`;
      }
      if (section.kind === "skills") {
        const rows = (section.skillLines ?? [])
          .map((raw) => {
            const colonIndex = raw.indexOf(":");
            return colonIndex > -1
              ? `<p><b>${esc(raw.slice(0, colonIndex))}:</b> ${esc(raw.slice(colonIndex + 1).trim())}</p>`
              : `<p>${esc(raw)}</p>`;
          })
          .join("");
        return heading + rows;
      }
      const entriesHtml = (section.entries ?? [])
        .map((entry) => {
          const headerHtml = entry.headerLines
            .map((line, i) => (i === 0 ? `<p><b>${esc(line)}</b></p>` : `<p><i>${esc(line)}</i></p>`))
            .join("");
          const bulletsHtml =
            entry.bullets.length > 0
              ? `<ul>${entry.bullets.map((b) => `<li>${esc(b)}</li>`).join("")}</ul>`
              : "";
          return headerHtml + bulletsHtml;
        })
        .join("");
      return heading + entriesHtml;
    })
    .join("");

  const html = `<!DOCTYPE html><html><head><meta charset="utf-8"><style>
body { font-family: Calibri, sans-serif; font-size: 11pt; color: #111; }
h1 { text-align: center; font-size: 20pt; margin-bottom: 2pt; }
.contact { text-align: center; font-size: 9pt; margin-bottom: 10pt; }
h2 { font-size: 12pt; border-bottom: 1px solid #111; padding-bottom: 2pt; margin-top: 12pt; margin-bottom: 4pt; }
p { margin: 2pt 0; }
ul { margin: 2pt 0 6pt 0; padding-left: 18pt; }
li { margin: 1pt 0; }
</style></head>
<body>
<h1>${esc(parsed.name.toUpperCase())}</h1>
<p class="contact">${esc(parsed.contactLine)}</p>
${sectionsHtml}
</body></html>`;

  triggerDownload(filename, new Blob([html], { type: "application/msword" }));
}

export function downloadLatex(filename: string, text: string) {
  const latex = buildLatexResume(text);
  triggerDownload(filename, new Blob([latex], { type: "text/x-tex" }));
}
