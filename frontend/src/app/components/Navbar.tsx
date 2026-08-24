import { Link, useNavigate } from "react-router-dom";
import { useAuthStore } from "@/features/auth/store";
import { useResumeStore } from "@/features/resume/store";
import { useInterviewStore } from "@/features/interview/store";
import { Button, buttonClasses } from "@/components";

/**
 * Auth-aware nav shell (frontend plan §H/Stage 2, extended in Stage 3/4).
 * Coding/dashboard nav items still wait for their own later stages
 * (linking to a route that doesn't exist yet would be worse than no link
 * at all) — Resumes/Plan Interview are added now because those routes
 * genuinely exist as of this stage.
 */
export function Navbar() {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const logout = useAuthStore((state) => state.logout);
  const resetResumeState = useResumeStore((state) => state.reset);
  const resetInterviewState = useInterviewStore((state) => state.reset);
  const navigate = useNavigate();

  function handleLogout() {
    // Every other feature store gets the same treatment as it lands —
    // a later candidate on a shared device must never see a previous
    // session's cached data (frontend plan §C.30).
    void logout().then(() => {
      resetResumeState();
      resetInterviewState();
      navigate("/", { replace: true });
    });
  }

  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex h-14 w-full max-w-5xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <Link to="/" className="text-base font-semibold text-slate-900">
          InterviewIQ <span className="text-brand-600">AI</span>
        </Link>
        <nav aria-label="Account" className="flex items-center gap-2">
          {isAuthenticated ? (
            <>
              <Link to="/resumes" className={buttonClasses("ghost", "sm")}>
                Resumes
              </Link>
              <Link to="/interviews/new" className={buttonClasses("ghost", "sm")}>
                Plan Interview
              </Link>
              <Link to="/profile" className={buttonClasses("ghost", "sm")}>
                Profile
              </Link>
              <Button variant="secondary" size="sm" onClick={handleLogout}>
                Log out
              </Button>
            </>
          ) : (
            <>
              <Link to="/login" className={buttonClasses("ghost", "sm")}>
                Log in
              </Link>
              <Link to="/register" className={buttonClasses("primary", "sm")}>
                Sign up
              </Link>
            </>
          )}
        </nav>
      </div>
    </header>
  );
}
