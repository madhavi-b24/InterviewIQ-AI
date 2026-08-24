import { Link } from "react-router-dom";
import { PageContainer, buttonClasses } from "@/components";

export function NotFoundPage() {
  return (
    <PageContainer className="flex flex-col items-center gap-3 py-24 text-center">
      <p className="text-sm font-semibold text-brand-600">404</p>
      <h1 className="text-2xl font-semibold text-slate-900">Page not found</h1>
      <p className="max-w-sm text-slate-600">
        The page you&apos;re looking for doesn&apos;t exist or may have been moved.
      </p>
      <Link to="/" className={buttonClasses("primary", "md", "mt-2")}>
        Back to home
      </Link>
    </PageContainer>
  );
}
