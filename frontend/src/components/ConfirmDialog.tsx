import { useEffect, useId, useRef } from "react";
import { Button } from "./Button";

export interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  /** Shows a spinner on the confirm button and disables both buttons —
   * for a confirm action that's a real network request in flight. */
  isConfirming?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * Destructive-action confirmation (frontend plan §D) — first needed by
 * Stage 3's resume delete, kept in the shared design system rather than
 * feature-local since any later destructive action (removing a roadmap
 * item, abandoning an interview, ...) should reuse this, not reinvent it.
 *
 * A plain conditionally-rendered `role="alertdialog"` overlay rather than
 * the native `<dialog>` element — `alertdialog` is the correct ARIA role
 * for an "are you sure?" prompt specifically (as opposed to plain
 * `dialog`), and avoids depending on `showModal()`/`close()` support in
 * every test/browser target this project runs against.
 */
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  isConfirming = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const titleId = useId();
  const descriptionId = useId();
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open) containerRef.current?.focus();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onCancel();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, onCancel]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4">
      <div
        ref={containerRef}
        tabIndex={-1}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        className="w-full max-w-sm rounded-lg border border-slate-200 bg-white p-5 shadow-lg outline-none"
      >
        <h2 id={titleId} className="text-base font-semibold text-slate-900">
          {title}
        </h2>
        {description ? (
          <p id={descriptionId} className="mt-1 text-sm text-slate-600">
            {description}
          </p>
        ) : null}
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={onCancel} disabled={isConfirming}>
            {cancelLabel}
          </Button>
          <Button variant="danger" size="sm" onClick={onConfirm} isLoading={isConfirming}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
