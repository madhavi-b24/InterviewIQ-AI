export type ButtonVariant = "primary" | "secondary" | "danger" | "ghost";
export type ButtonSize = "sm" | "md" | "lg";

const variantClasses: Record<ButtonVariant, string> = {
  primary: "bg-brand-600 text-white hover:bg-brand-700 focus-visible:outline-brand-600",
  secondary:
    "bg-white text-slate-900 border border-slate-300 hover:bg-slate-50 focus-visible:outline-brand-600",
  danger: "bg-red-600 text-white hover:bg-red-700 focus-visible:outline-red-600",
  ghost: "bg-transparent text-slate-700 hover:bg-slate-100 focus-visible:outline-brand-600",
};

const sizeClasses: Record<ButtonSize, string> = {
  sm: "px-3 py-1.5 text-sm",
  md: "px-4 py-2 text-sm",
  lg: "px-5 py-2.5 text-base",
};

/**
 * The button's visual classes, factored out of Button.tsx into its own
 * module (a file that only exports a component breaks React Fast Refresh
 * for anything else it also exports — oxlint's `only-export-components`
 * rule catches exactly this) — for the common case of a button-*styled*
 * navigation link (e.g. `<Link className={buttonClasses()}>`). A `<Link>`
 * renders an `<a>`, and nesting an `<a>` inside a real `<button>` element
 * is invalid HTML — so a "link that looks like a button" must be a
 * styled `<a>`/`<Link>` directly, never `<Button>` wrapping a `<Link>`.
 */
export function buttonClasses(
  variant: ButtonVariant = "primary",
  size: ButtonSize = "md",
  className = "",
): string {
  return [
    "inline-flex items-center justify-center gap-2 rounded-md font-medium transition-colors",
    "disabled:cursor-not-allowed disabled:opacity-60",
    "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2",
    variantClasses[variant],
    sizeClasses[size],
    className,
  ].join(" ");
}
