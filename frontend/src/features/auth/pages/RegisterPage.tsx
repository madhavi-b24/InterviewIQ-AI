import { type FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Button, ErrorBanner, Input } from "@/components";
import { toApiError, type ApiError } from "@/lib/errors";
import { useAuthStore } from "../store";
import { AuthPageShell } from "../components/AuthPageShell";

const PASSWORD_HINT = "At least 8 characters, with a letter and a number.";

export function RegisterPage() {
  const register = useAuthStore((state) => state.register);
  const navigate = useNavigate();

  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<ApiError | string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setIsSubmitting(true);
    try {
      await register({ email, password, first_name: firstName, last_name: lastName });
      // No dashboard yet (later stage) — /profile is the only protected
      // page today, and its unverified badge naturally communicates the
      // "check your email to verify" state without a separate screen.
      navigate("/profile", { replace: true });
    } catch (caught) {
      setError(toApiError(caught));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AuthPageShell
      title="Create your account"
      subtitle="Start practicing with adaptive mock interviews."
    >
      <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
        <div className="grid grid-cols-2 gap-3">
          <Input
            label="First name"
            value={firstName}
            onChange={(event) => setFirstName(event.target.value)}
            required
            autoComplete="given-name"
          />
          <Input
            label="Last name"
            value={lastName}
            onChange={(event) => setLastName(event.target.value)}
            required
            autoComplete="family-name"
          />
        </div>
        <Input
          label="Email"
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
          autoComplete="email"
        />
        <Input
          label="Password"
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          required
          minLength={8}
          autoComplete="new-password"
          hint={PASSWORD_HINT}
        />
        <Input
          label="Confirm password"
          type="password"
          value={confirmPassword}
          onChange={(event) => setConfirmPassword(event.target.value)}
          required
          minLength={8}
          autoComplete="new-password"
        />
        {error ? <ErrorBanner error={error} /> : null}
        <Button type="submit" isLoading={isSubmitting} className="mt-2 w-full">
          Create account
        </Button>
      </form>
      <p className="mt-4 text-center text-sm text-slate-600">
        Already have an account?{" "}
        <Link to="/login" className="font-medium text-brand-600 hover:underline">
          Sign in
        </Link>
      </p>
    </AuthPageShell>
  );
}
