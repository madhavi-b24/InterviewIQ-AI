import type { HTMLAttributes, ReactNode } from "react";

type BadgeVariant = "neutral" | "brand" | "success" | "warning" | "danger" | "info";

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
  children: ReactNode;
}

const variantClasses: Record<BadgeVariant, string> = {
  neutral: "bg-slate-100 text-slate-700",
  brand: "bg-brand-100 text-brand-700",
  success: "bg-green-100 text-green-700",
  warning: "bg-amber-100 text-amber-700",
  danger: "bg-red-100 text-red-700",
  info: "bg-sky-100 text-sky-700",
};

/**
 * A generic color-variant pill — deliberately domain-agnostic. Later
 * stages map their own domain values onto one of these six variants
 * (e.g. difficulty=hard -> "danger", CodeExecutionStatus=success ->
 * "success", ProgressTrend=declining -> "danger") rather than Badge
 * itself knowing about difficulty/status/severity/trend/resourceType —
 * that domain mapping belongs in each feature, not in the shared
 * component (frontend plan §D).
 */
export function Badge({ variant = "neutral", className = "", children, ...rest }: BadgeProps) {
  return (
    <span
      className={[
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        variantClasses[variant],
        className,
      ].join(" ")}
      {...rest}
    >
      {children}
    </span>
  );
}
