import type { ReactNode } from "react";
import { Button } from "./Button";

export interface EmptyStateProps {
  /** e.g. an icon element — optional, purely decorative. */
  icon?: ReactNode;
  title: string;
  /** Every list-shaped screen needs a *specific*, written-for-that-context
   * message here (frontend plan §K) — never a generic "No data" passed
   * from a shared default. */
  description?: string;
  action?: {
    label: string;
    onClick: () => void;
  };
  className?: string;
}

export function EmptyState({ icon, title, description, action, className = "" }: EmptyStateProps) {
  return (
    <div
      className={[
        "flex flex-col items-center gap-2 rounded-lg border border-dashed border-slate-300 px-6 py-12 text-center",
        className,
      ].join(" ")}
    >
      {icon ? (
        <div className="mb-1 text-slate-400" aria-hidden="true">
          {icon}
        </div>
      ) : null}
      <p className="text-sm font-medium text-slate-900">{title}</p>
      {description ? <p className="max-w-sm text-sm text-slate-500">{description}</p> : null}
      {action ? (
        <Button variant="primary" size="sm" onClick={action.onClick} className="mt-3">
          {action.label}
        </Button>
      ) : null}
    </div>
  );
}
