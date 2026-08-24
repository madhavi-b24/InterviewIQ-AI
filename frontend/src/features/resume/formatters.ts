/** Resume-specific date formatting — backend/app/schemas/resume.py's
 * date fields serialize as plain ISO date strings ("YYYY-MM-DD"). */

export function formatMonthYear(dateStr: string | null): string | null {
  if (!dateStr) return null;
  const date = new Date(dateStr);
  if (Number.isNaN(date.getTime())) return dateStr;
  return date.toLocaleDateString(undefined, { year: "numeric", month: "short" });
}

/** No end date but a real start date means "ongoing" — renders as
 * "Jan 2022 – Present", matching how a resume itself would describe a
 * current role/project. No start date at all means there's nothing
 * meaningful to anchor a range to, so this returns null rather than a
 * one-sided range. */
export function formatDateRange(start: string | null, end: string | null): string | null {
  const startLabel = formatMonthYear(start);
  if (!startLabel) return null;
  const endLabel = end ? formatMonthYear(end) : "Present";
  return `${startLabel} – ${endLabel}`;
}
