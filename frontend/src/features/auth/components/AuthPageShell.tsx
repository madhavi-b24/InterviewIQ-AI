import type { ReactNode } from "react";
import { Card, PageContainer } from "@/components";

export interface AuthPageShellProps {
  title: string;
  subtitle?: string;
  children: ReactNode;
}

/** The shared centered-card layout for every auth screen (Login,
 * Register, ForgotPassword, ResetPassword, VerifyEmail) — kept as one
 * small component rather than duplicating this wrapper six times. Profile
 * doesn't use this: it's a full-width protected page, not a signed-out
 * form. */
export function AuthPageShell({ title, subtitle, children }: AuthPageShellProps) {
  return (
    <PageContainer className="flex justify-center py-16">
      <Card className="w-full max-w-sm">
        <div className="mb-6 text-center">
          <h1 className="text-xl font-semibold text-slate-900">{title}</h1>
          {subtitle ? <p className="mt-1 text-sm text-slate-600">{subtitle}</p> : null}
        </div>
        {children}
      </Card>
    </PageContainer>
  );
}
