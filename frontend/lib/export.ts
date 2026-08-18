import { TailoredBullet } from "./api";

/** Substitute each tailored bullet back into the resume text (best-effort verbatim
 * match). Anything that can't be located verbatim is appended as a suggestions
 * section instead of being silently dropped. */
export function buildTailoredResumeText(resumeText: string, bullets: TailoredBullet[]): string {
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

  return text;
}

export function downloadPdf(filename: string, text: string) {
  import("jspdf").then(({ default: jsPDF }) => {
    const doc = new jsPDF({ unit: "pt", format: "letter" });
    const marginX = 48;
    const marginY = 56;
    const maxWidth = doc.internal.pageSize.getWidth() - marginX * 2;
    const lineHeight = 14;
    const pageHeight = doc.internal.pageSize.getHeight();

    doc.setFont("helvetica", "normal");
    doc.setFontSize(10);

    const lines = text.split("\n").flatMap((line) =>
      line.length === 0 ? [""] : doc.splitTextToSize(line, maxWidth)
    );

    let y = marginY;
    for (const line of lines) {
      if (y > pageHeight - marginY) {
        doc.addPage();
        y = marginY;
      }
      doc.text(line, marginX, y);
      y += lineHeight;
    }

    doc.save(filename);
  });
}

export function downloadWord(filename: string, text: string) {
  const escaped = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  const html = `<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body><pre style="font-family: Calibri, sans-serif; font-size: 11pt; white-space: pre-wrap;">${escaped}</pre></body></html>`;

  const blob = new Blob([html], { type: "application/msword" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
