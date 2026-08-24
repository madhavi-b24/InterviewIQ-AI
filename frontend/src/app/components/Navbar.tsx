import { Link, useNavigate } from "react-router-dom";
import { useAuthStore } from "@/features/auth/store";
import { Button, buttonClasses } from "@/components";

/**
 * Auth-aware nav shell (frontend plan §H, Stage 2). Deliberately still
 * just Login/Register/Profile/Logout — dashboard/interview/coding nav
 * items are added in their own later stages, once those routes exist
 * (linking to a route that doesn't exist yet would be worse than no link
 * at all, same reasoning Stage 1 left this whole area empty for).
 */
export function Navbar() {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const logout = useAuthStore((state) => state.logout);
  const navigate = useNavigate();

  function handleLogout() {
    void logout().then(() => navigate("/", { replace: true }));
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
