import { type FormEvent, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Button, ErrorBanner, Input } from "@/components";
import { toApiError, type ApiError } from "@/lib/errors";
import type { RedirectLocationState } from "@/lib/routeGuards";
import { useAuthStore } from "../store";
import { AuthPageShell } from "../components/AuthPageShell";

export function LoginPage() {
  const login = useAuthStore((state) => state.login);
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as RedirectLocationState | null)?.from?.pathname ?? "/profile";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await login({ email, password });
      navigate(from, { replace: true });
    } catch (caught) {
      setError(toApiError(caught));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AuthPageShell title="Sign in" subtitle="Welcome back.">
      <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
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
          autoComplete="current-password"
        />
        {/* The backend's own 401 is deliberately generic ("invalid email
            or password") regardless of which was wrong — rendered
            verbatim, never split into "email not found" vs "wrong
            password" on the client either. */}
        {error ? <ErrorBanner error={error} /> : null}
        <Button type="submit" isLoading={isSubmitting} className="mt-2 w-full">
          Sign in
        </Button>
      </form>
      <div className="mt-4 flex flex-col items-center gap-2 text-sm text-slate-600">
        <Link to="/forgot-password" className="font-medium text-brand-600 hover:underline">
          Forgot your password?
        </Link>
        <p>
          No account yet?{" "}
          <Link to="/register" className="font-medium text-brand-600 hover:underline">
            Create one
          </Link>
        </p>
      </div>
    </AuthPageShell>
  );
}
