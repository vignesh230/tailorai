export interface ExperienceEntry {
  title: string;
  company: string;
  dates: string;
  bullets: string; // one per line
}

export interface EducationEntry {
  degree: string;
  school: string;
  dates: string;
}

export interface ResumeFormData {
  fullName: string;
  contact: string;
  summary: string;
  experience: ExperienceEntry[];
  education: EducationEntry[];
  skills: string; // comma-separated
}

export function emptyExperience(): ExperienceEntry {
  return { title: "", company: "", dates: "", bullets: "" };
}

export function emptyEducation(): EducationEntry {
  return { degree: "", school: "", dates: "" };
}

export function emptyResumeForm(): ResumeFormData {
  return {
    fullName: "",
    contact: "",
    summary: "",
    experience: [emptyExperience()],
    education: [emptyEducation()],
    skills: "",
  };
}

/** Assemble structured fields into plain resume text with standard section
 * headings (Experience/Education/Skills) so the ATS formatting heuristics on
 * the backend recognize the structure. */
export function assembleResumeText(form: ResumeFormData): string {
  const lines: string[] = [];

  if (form.fullName.trim()) lines.push(form.fullName.trim());
  if (form.contact.trim()) lines.push(form.contact.trim());
  lines.push("");

  if (form.summary.trim()) {
    lines.push("Summary");
    lines.push(form.summary.trim());
    lines.push("");
  }

  lines.push("Experience");
  for (const exp of form.experience) {
    if (!exp.title.trim() && !exp.company.trim()) continue;
    const header = [exp.title.trim(), exp.company.trim()].filter(Boolean).join(" — ");
    lines.push(exp.dates.trim() ? `${header} (${exp.dates.trim()})` : header);
    for (const bullet of exp.bullets.split("\n").map((b) => b.trim()).filter(Boolean)) {
      lines.push(`- ${bullet}`);
    }
  }
  lines.push("");

  lines.push("Education");
  for (const edu of form.education) {
    if (!edu.degree.trim() && !edu.school.trim()) continue;
    const header = [edu.degree.trim(), edu.school.trim()].filter(Boolean).join(", ");
    lines.push(edu.dates.trim() ? `${header} (${edu.dates.trim()})` : header);
  }
  lines.push("");

  lines.push("Skills");
  lines.push(form.skills.trim());

  return lines.join("\n").trim() + "\n";
}
