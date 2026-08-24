import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { buttonClasses, ErrorBanner, Spinner } from "@/components";
import { toApiError, type ApiError } from "@/lib/errors";
import { useAuthStore } from "../store";
import { AuthPageShell } from "../components/AuthPageShell";

type VerificationState = "loading" | "success" | "error";

export function VerifyEmailPage() {
  const { token } = useParams<{ token: string }>();
  const verifyEmail = useAuthStore((state) => state.verifyEmail);

  const [state, setState] = useState<VerificationState>(token ? "loading" : "error");
  const [error, setError] = useState<ApiError | string | null>(
    token ? null : "This verification link is missing its token.",
  );

  useEffect(() => {
    if (!token) return;

    let cancelled = false;
    verifyEmail(token)
      .then(() => {
        if (!cancelled) setState("success");
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setError(toApiError(caught));
          setState("error");
        }
      });

    return () => {
      cancelled = true;
    };
  }, [token, verifyEmail]);

  return (
    <AuthPageShell title="Email verification">
      {state === "loading" ? (
        <div className="flex flex-col items-center gap-3 py-4">
          <Spinner size="lg" label="Verifying your email" />
        </div>
      ) : state === "success" ? (
        <div className="flex flex-col gap-4 text-center">
          <p className="text-sm text-slate-600">Your email has been verified.</p>
          <Link to="/profile" className={buttonClasses("primary", "md", "w-full")}>
            Continue to your profile
          </Link>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          <ErrorBanner error={error ?? "This verification link is invalid or has expired."} />
          <p className="text-sm text-slate-600">
            Sign in and request a new link from your{" "}
            <Link to="/profile" className="font-medium text-brand-600 hover:underline">
              profile page
            </Link>
            .
          </p>
          <Link to="/login" className={buttonClasses("secondary", "md", "w-full")}>
            Sign in
          </Link>
        </div>
      )}
    </AuthPageShell>
  );
}
