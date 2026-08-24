import type { HTMLAttributes, ReactNode } from "react";

export interface PageContainerProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
}

/** Consistent max-width + horizontal padding wrapper for page content —
 * every page's top-level content goes inside one of these rather than
 * each page picking its own width/padding. Responsive by default:
 * padding tightens on narrow viewports instead of the content touching
 * the screen edge. */
export function PageContainer({ className = "", children, ...rest }: PageContainerProps) {
  return (
    <div className={["mx-auto w-full max-w-5xl px-4 py-8 sm:px-6 lg:px-8", className].join(" ")} {...rest}>
      {children}
    </div>
  );
}
