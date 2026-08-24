import type { HTMLAttributes, ReactNode } from "react";

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
}

/** The one general-purpose surface primitive — report sections, dashboard
 * tiles, resume cards, and every other "boxed content" area in the
 * product should compose this rather than each inventing its own
 * border/shadow/padding combination. */
export function Card({ className = "", children, ...rest }: CardProps) {
  return (
    <div
      className={[
        "rounded-lg border border-slate-200 bg-white p-4 shadow-sm",
        className,
      ].join(" ")}
      {...rest}
    >
      {children}
    </div>
  );
}
