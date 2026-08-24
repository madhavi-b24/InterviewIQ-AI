import { Card } from "@/components";

export interface EvidenceCardProps {
  title: string;
  subtitle?: string | null;
  meta?: string | null;
  tags?: string[];
  evidence?: string | null;
}

/** One project/experience/education/certification/achievement item —
 * generic on purpose (frontend plan §D) so every resume-analysis section
 * shares one visual shape instead of five bespoke card types. `evidence`
 * is the whole point of this data model (module §16's evidence-tagged
 * extraction) — always shown as a quoted snippet when present, never
 * summarized away. */
export function EvidenceCard({ title, subtitle, meta, tags, evidence }: EvidenceCardProps) {
  return (
    <Card className="flex flex-col gap-2">
      <div>
        <p className="text-sm font-medium text-slate-900">{title}</p>
        {subtitle ? <p className="text-sm text-slate-600">{subtitle}</p> : null}
        {meta ? <p className="text-xs text-slate-500">{meta}</p> : null}
      </div>
      {tags && tags.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {tags.map((tag) => (
            <span key={tag} className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-700">
              {tag}
            </span>
          ))}
        </div>
      ) : null}
      {evidence ? (
        <p className="border-l-2 border-slate-200 pl-3 text-xs italic text-slate-500">
          &ldquo;{evidence}&rdquo;
        </p>
      ) : null}
    </Card>
  );
}
