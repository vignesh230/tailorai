import { ParsedResume, parseResumeSections } from "./resumeRender";

function escapeLatex(s: string): string {
  return s
    .replace(/\\/g, "\\textbackslash{}")
    .replace(/([&%$#_{}])/g, "\\$1")
    .replace(/~/g, "\\textasciitilde{}")
    .replace(/\^/g, "\\textasciicircum{}");
}

function contactToken(token: string): string {
  const t = token.trim();
  if (!t) return "";
  if (/^[\w.+-]+@[\w-]+\.[\w.-]+$/.test(t)) {
    return `\\href{mailto:${t}}{${escapeLatex(t)}}`;
  }
  if (/^(https?:\/\/)?(www\.)?(linkedin\.com|github\.com)\//i.test(t)) {
    const url = t.startsWith("http") ? t : `https://${t}`;
    return `\\href{${url}}{${escapeLatex(t)}}`;
  }
  return escapeLatex(t);
}

function contactLineToLatex(contactLine: string): string {
  return contactLine
    .split("|")
    .map((t) => contactToken(t))
    .filter(Boolean)
    .join(" \\;$|$\\; ");
}

const PREAMBLE = `\\documentclass[letterpaper,10pt]{article}
\\usepackage[left=0.6in, right=0.6in, top=0.4in, bottom=0.3in]{geometry}
\\usepackage[hidelinks]{hyperref}
\\usepackage{enumitem}
\\usepackage{titlesec}
\\usepackage[T1]{fontenc}
\\usepackage[utf8]{inputenc}
\\usepackage{lmodern}
\\usepackage{microtype}
\\titleformat{\\section}{\\large\\bfseries\\uppercase}{}{0em}{}[\\titlerule]
\\titlespacing{\\section}{0pt}{6pt}{4pt}
\\pagestyle{empty}
\\setlength{\\parindent}{0pt}
\\setlist[itemize]{leftmargin=*, topsep=3pt, parsep=1pt, itemsep=0pt}
\\begin{document}`;

function renderSection(section: ParsedResume["sections"][number]): string {
  const lines: string[] = [`\\section{${escapeLatex(section.heading)}}`];

  if (section.kind === "summary") {
    lines.push(escapeLatex(section.paragraph ?? ""));
    return lines.join("\n");
  }

  if (section.kind === "skills") {
    for (const raw of section.skillLines ?? []) {
      const colonIndex = raw.indexOf(":");
      if (colonIndex > -1) {
        const label = raw.slice(0, colonIndex);
        const rest = raw.slice(colonIndex + 1);
        lines.push(`\\textbf{${escapeLatex(label)}:} ${escapeLatex(rest.trim())} \\\\`);
      } else {
        lines.push(`${escapeLatex(raw)} \\\\`);
      }
    }
    return lines.join("\n");
  }

  for (const entry of section.entries ?? []) {
    entry.headerLines.forEach((headerLine, i) => {
      const style = i === 0 ? "\\textbf" : "\\textit";
      lines.push(`${style}{${escapeLatex(headerLine)}} \\\\`);
    });
    if (entry.bullets.length > 0) {
      lines.push("\\begin{itemize}");
      for (const bullet of entry.bullets) {
        lines.push(`  \\item ${escapeLatex(bullet)}`);
      }
      lines.push("\\end{itemize}");
    }
  }
  return lines.join("\n");
}

/** Render a plain-text resume as a compilable LaTeX document, matching the
 * single-column "section header + underline rule" style. Compile with
 * `tectonic file.tex` or upload to Overleaf — no server-side LaTeX toolchain
 * required for this export. */
export function buildLatexResume(resumeText: string): string {
  const parsed = parseResumeSections(resumeText);

  const header = [
    "\\begin{center}",
    `  {\\huge \\textbf{${escapeLatex(parsed.name.toUpperCase())}}} \\\\[5pt]`,
    "  \\small",
    `  ${contactLineToLatex(parsed.contactLine)}`,
    "\\end{center}",
  ].join("\n");

  const body = parsed.sections.map(renderSection).join("\n\n");

  return [PREAMBLE, "", header, "", body, "", "\\end{document}", ""].join("\n");
}
