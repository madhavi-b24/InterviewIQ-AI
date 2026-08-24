import { type FormEvent, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Button, buttonClasses, ErrorBanner, Input } from "@/components";
import { toApiError, type ApiError } from "@/lib/errors";
import { useAuthStore } from "../store";
import { AuthPageShell } from "../components/AuthPageShell";

const PASSWORD_HINT = "At least 8 characters, with a letter and a number.";

export function ResetPasswordPage() {
  const { token } = useParams<{ token: string }>();
  const confirmPasswordReset = useAuthStore((state) => state.confirmPasswordReset);

  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<ApiError | string | null>(null);
  const [success, setSuccess] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    if (!token) {
      setError("This reset link is missing its token.");
      return;
    }

    setIsSubmitting(true);
    try {
      await confirmPasswordReset(token, password);
      setSuccess(true);
    } catch (caught) {
      setError(toApiError(caught));
    } finally {
      setIsSubmitting(false);
    }
  }

  if (success) {
    return (
      <AuthPageShell title="Password updated">
        <p className="text-sm text-slate-600">
          Your password has been reset. You can now sign in with your new password.
        </p>
        <Link to="/login" className={buttonClasses("primary", "md", "mt-6 w-full")}>
          Go to sign in
        </Link>
      </AuthPageShell>
    );
  }

  // The backend returns 401 for a missing/invalid/expired/already-used
  // reset token (AuthService.confirm_password_reset) — every one of
  // those cases gets the same "request a new link" recovery, since none
  // of them are recoverable by retrying the same token.
  const isDeadTokenError = error !== null && typeof error !== "string" && error.status === 401;

  return (
    <AuthPageShell title="Set a new password">
      {isDeadTokenError ? (
        <div className="flex flex-col gap-4">
          <ErrorBanner error="This reset link is invalid or has expired." />
          <Link to="/forgot-password" className={buttonClasses("primary", "md", "w-full")}>
            Request a new link
          </Link>
        </div>
      ) : (
        <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
          <Input
            label="New password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
            minLength={8}
            autoComplete="new-password"
            hint={PASSWORD_HINT}
          />
          <Input
            label="Confirm new password"
            type="password"
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
            required
            minLength={8}
            autoComplete="new-password"
          />
          {error ? <ErrorBanner error={error} /> : null}
          <Button type="submit" isLoading={isSubmitting} className="mt-2 w-full">
            Update password
          </Button>
        </form>
      )}
    </AuthPageShell>
  );
}
