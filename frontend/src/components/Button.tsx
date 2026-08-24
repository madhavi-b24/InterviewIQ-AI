import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Spinner } from "./Spinner";
import { buttonClasses, type ButtonSize, type ButtonVariant } from "./buttonClasses";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Shows a spinner and disables the button — for an in-flight request.
   * Distinct from `disabled`, which a caller can still set independently
   * (e.g. a form that's invalid but not currently submitting). */
  isLoading?: boolean;
  children: ReactNode;
}

export function Button({
  variant = "primary",
  size = "md",
  isLoading = false,
  disabled,
  className = "",
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      className={buttonClasses(variant, size, className)}
      disabled={disabled || isLoading}
      aria-busy={isLoading || undefined}
      {...rest}
    >
      {/* label="" — the button's own text plus aria-busy already convey
          the loading state; Spinner's default aria-label would otherwise
          get folded into the button's *own* accessible name ("Loading" +
          "Save" -> "LoadingSave"), which is wrong. */}
      {isLoading ? <Spinner size="sm" label="" className="shrink-0" /> : null}
      {children}
    </button>
  );
}
