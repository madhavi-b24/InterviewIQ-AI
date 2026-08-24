type SpinnerSize = "sm" | "md" | "lg";

export interface SpinnerProps {
  size?: SpinnerSize;
  className?: string;
  /** Accessible label — a spinner conveys nothing to a screen reader on
   * its own. Defaults to a generic "Loading" but callers embedding a
   * spinner where the surrounding text already says what's loading
   * (e.g. inside a Button) can pass "" to avoid double-announcing. */
  label?: string;
}

const sizeClasses: Record<SpinnerSize, string> = {
  sm: "size-4 border-2",
  md: "size-6 border-2",
  lg: "size-10 border-[3px]",
};

export function Spinner({ size = "md", className = "", label = "Loading" }: SpinnerProps) {
  return (
    <span
      role="status"
      aria-label={label || undefined}
      aria-hidden={label ? undefined : true}
      className={[
        "inline-block animate-spin rounded-full border-current border-t-transparent",
        sizeClasses[size],
        className,
      ].join(" ")}
    />
  );
}
