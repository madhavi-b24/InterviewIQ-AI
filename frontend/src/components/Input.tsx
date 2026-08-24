import { useId, type InputHTMLAttributes } from "react";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  /** Field-level validation message — e.g. mapped from a 422 response's
   * `details.errors[].msg` in a later stage (frontend plan §K). */
  error?: string;
  hint?: string;
}

export function Input({ label, error, hint, id, className = "", ...rest }: InputProps) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const hintId = hint ? `${inputId}-hint` : undefined;
  const errorId = error ? `${inputId}-error` : undefined;

  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={inputId} className="text-sm font-medium text-slate-700">
        {label}
      </label>
      <input
        id={inputId}
        aria-invalid={Boolean(error) || undefined}
        aria-describedby={[hintId, errorId].filter(Boolean).join(" ") || undefined}
        className={[
          "rounded-md border px-3 py-2 text-sm text-slate-900 shadow-sm outline-none",
          "focus:ring-2 focus:ring-brand-500 focus:border-brand-500",
          "disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-500",
          error ? "border-red-400" : "border-slate-300",
          className,
        ].join(" ")}
        {...rest}
      />
      {hint && !error ? (
        <p id={hintId} className="text-xs text-slate-500">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={errorId} role="alert" className="text-xs text-red-600">
          {error}
        </p>
      ) : null}
    </div>
  );
}
