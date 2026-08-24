import { Button, Card, ErrorBanner, Spinner } from "@/components";
import type { ApiError } from "@/lib/errors";
import type { CompanyOut } from "../api";

export interface CompanyPickerProps {
  companies: CompanyOut[];
  status: "idle" | "loading" | "success" | "error";
  error: ApiError | null;
  onSelect: (company: CompanyOut | null) => void;
  onRetry: () => void;
}

/** Step 1 of the planning wizard (frontend plan §C.9). "Any company" is
 * its own first-class action, not just another card — a company-agnostic
 * plan is a fully supported path, not an edge case (module §8; also
 * necessary in practice: the seeded "general" company has zero roles
 * actually attached to it, so picking it as if it were a normal company
 * would always dead-end into an empty role list). */
export function CompanyPicker({ companies, status, error, onSelect, onRetry }: CompanyPickerProps) {
  return (
    <div className="flex flex-col gap-4">
      <div>
        <h2 className="text-sm font-semibold text-slate-900">Choose a company</h2>
        <p className="mt-1 text-sm text-slate-600">
          Practice against a specific company&apos;s interview style, or a balanced,
          company-agnostic loop.
        </p>
      </div>

      <Button type="button" variant="secondary" className="self-start" onClick={() => onSelect(null)}>
        Any company — balanced loop
      </Button>

      {status === "loading" ? (
        <div className="flex justify-center py-8">
          <Spinner size="lg" />
        </div>
      ) : status === "error" ? (
        <ErrorBanner error={error ?? "Something went wrong."} onRetry={onRetry} />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {companies.map((company) => (
            <Card key={company.id} className="flex flex-col gap-2">
              <p className="text-sm font-medium text-slate-900">{company.name}</p>
              {company.interview_style_notes ? (
                <p className="text-xs text-slate-500">{company.interview_style_notes}</p>
              ) : null}
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="mt-1 self-start"
                onClick={() => onSelect(company)}
              >
                Select {company.name}
              </Button>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
