import { type FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { Button, buttonClasses, ErrorBanner, Input } from "@/components";
import { toApiError, type ApiError } from "@/lib/errors";
import { useAuthStore } from "../store";
import { AuthPageShell } from "../components/AuthPageShell";

export function ForgotPasswordPage() {
  const requestPasswordReset = useAuthStore((state) => state.requestPasswordReset);

  const [email, setEmail] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [submitted, setSubmitted] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await requestPasswordReset(email);
      // The backend responds 202 identically whether or not the email
      // exists (see AuthService.request_password_reset) — this success
      // state must never branch on anything the response could reveal.
      setSubmitted(true);
    } catch (caught) {
      setError(toApiError(caught));
    } finally {
      setIsSubmitting(false);
    }
  }

  if (submitted) {
    return (
      <AuthPageShell title="Check your email">
        <p className="text-sm text-slate-600">
          If an account exists for <strong>{email}</strong>, we&apos;ve sent a link to reset your
          password.
        </p>
        <Link to="/login" className={buttonClasses("secondary", "md", "mt-6 w-full")}>
          Back to sign in
        </Link>
      </AuthPageShell>
    );
  }

  return (
    <AuthPageShell title="Reset your password" subtitle="We'll email you a link to set a new one.">
      <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
        <Input
          label="Email"
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
          autoComplete="email"
        />
        {error ? <ErrorBanner error={error} /> : null}
        <Button type="submit" isLoading={isSubmitting} className="mt-2 w-full">
          Send reset link
        </Button>
      </form>
      <p className="mt-4 text-center text-sm text-slate-600">
        <Link to="/login" className="font-medium text-brand-600 hover:underline">
          Back to sign in
        </Link>
      </p>
    </AuthPageShell>
  );
}
