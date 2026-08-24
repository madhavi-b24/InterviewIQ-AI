import { Badge, Button, Card, ErrorBanner, EmptyState, Spinner } from "@/components";
import type { ApiError } from "@/lib/errors";
import type { RoleOut } from "../api";

export interface RolePickerProps {
  roles: RoleOut[];
  status: "idle" | "loading" | "success" | "error";
  error: ApiError | null;
  onSelect: (role: RoleOut) => void;
  onRetry: () => void;
  onBack: () => void;
}

const LEVEL_LABELS: Record<string, string> = {
  intern: "Intern",
  junior: "Junior",
  mid: "Mid-level",
  senior: "Senior",
  staff: "Staff",
};

export function RolePicker({ roles, status, error, onSelect, onRetry, onBack }: RolePickerProps) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">Choose a role</h2>
          <p className="mt-1 text-sm text-slate-600">Which role are you preparing for?</p>
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
      ) : roles.length === 0 ? (
        <EmptyState
          title="No roles available"
          description="This company doesn't have any active roles to plan against yet."
        />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {roles.map((role) => (
            <Card key={role.id} className="flex flex-col gap-2">
              <div className="flex items-start justify-between gap-2">
                <p className="text-sm font-medium text-slate-900">{role.title}</p>
                <Badge variant="neutral">{LEVEL_LABELS[role.level] ?? role.level}</Badge>
              </div>
              {role.description ? <p className="text-xs text-slate-500">{role.description}</p> : null}
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="mt-1 self-start"
                onClick={() => onSelect(role)}
              >
                Select {role.title}
              </Button>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
