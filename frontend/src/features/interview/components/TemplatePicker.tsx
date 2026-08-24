import { Badge, Button, Card, ErrorBanner, EmptyState, Spinner } from "@/components";
import type { ApiError } from "@/lib/errors";
import type { TemplateSummaryOut } from "../api";

export interface TemplatePickerProps {
  templates: TemplateSummaryOut[];
  status: "idle" | "loading" | "success" | "error";
  error: ApiError | null;
  onSelect: (template: TemplateSummaryOut) => void;
  onRetry: () => void;
  onBack: () => void;
}

const MODE_LABELS: Record<string, string> = {
  full_mock: "Full mock",
  technical_only: "Technical only",
  coding_only: "Coding only",
  behavioral_only: "Behavioral only",
  resume_deep_dive: "Resume deep dive",
};

export function TemplatePicker({
  templates,
  status,
  error,
  onSelect,
  onRetry,
  onBack,
}: TemplatePickerProps) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">Choose an interview template</h2>
          <p className="mt-1 text-sm text-slate-600">
            Each template is a fixed round plan — you&apos;ll see exactly what rounds it
            includes before confirming.
          </p>
        </div>
        <Button type="button" variant="ghost" size="sm" onClick={onBack}>
          ← Back
        </Button>
      </div>

      {status === "loading" ? (
        <div className="flex justify-center py-8">
          <Spinner size="lg" />
        </div>
      ) : status === "error" ? (
        <ErrorBanner error={error ?? "Something went wrong."} onRetry={onRetry} />
      ) : templates.length === 0 ? (
        <EmptyState
          title="No templates available"
          description="This role doesn't have any active interview templates yet."
        />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {templates.map((template) => (
            <Card key={template.id} className="flex flex-col gap-2">
              <div className="flex items-start justify-between gap-2">
                <p className="text-sm font-medium text-slate-900">{template.name}</p>
                <Badge variant="brand">{MODE_LABELS[template.mode] ?? template.mode}</Badge>
              </div>
              {template.description ? (
                <p className="text-xs text-slate-500">{template.description}</p>
              ) : null}
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="mt-1 self-start"
                onClick={() => onSelect(template)}
              >
                Select {template.name}
              </Button>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
