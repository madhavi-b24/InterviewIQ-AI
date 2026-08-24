import { type FormEvent, useState } from "react";
import { Badge, Button, Card, ErrorBanner, Input, PageContainer, Spinner } from "@/components";
import { toApiError, type ApiError } from "@/lib/errors";
import { useAuthStore } from "../store";

/**
 * `avatar_url` is PATCH-able on the backend (UserUpdateRequest) but has
 * no editor here yet — there's no upload flow to pair it with, and
 * accepting a raw pasted URL isn't a meaningful feature on its own. Only
 * `full_name` is exposed, matching what "editable allowed fields"
 * actually needs for Stage 2.
 */
export function ProfilePage() {
  const user = useAuthStore((state) => state.user);
  const updateProfile = useAuthStore((state) => state.updateProfile);
  const resendVerification = useAuthStore((state) => state.resendVerification);

  const [fullName, setFullName] = useState(user?.full_name ?? "");
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<ApiError | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);

  const [isResending, setIsResending] = useState(false);
  const [resendError, setResendError] = useState<ApiError | null>(null);
  const [resendSuccess, setResendSuccess] = useState(false);

  if (!user) {
    // ProtectedRoute guarantees a session exists by the time this route
    // renders — `user` is already populated by login/register/initialize,
    // there's no separate GET /users/me fetch to wait on here. Defensive
    // fallback only, not a real loading state.
    return (
      <PageContainer className="flex justify-center py-16">
        <Spinner size="lg" />
      </PageContainer>
    );
  }

  async function handleSave(event: FormEvent) {
    event.preventDefault();
    setSaveError(null);
    setSaveSuccess(false);
    setIsSaving(true);
    try {
      await updateProfile({ full_name: fullName });
      setSaveSuccess(true);
    } catch (caught) {
      setSaveError(toApiError(caught));
    } finally {
      setIsSaving(false);
    }
  }

  async function handleResend() {
    setResendError(null);
    setResendSuccess(false);
    setIsResending(true);
    try {
      await resendVerification();
      setResendSuccess(true);
    } catch (caught) {
      setResendError(toApiError(caught));
    } finally {
      setIsResending(false);
    }
  }

  return (
    <PageContainer className="flex justify-center py-12">
      <div className="flex w-full max-w-md flex-col gap-6">
        <Card>
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-lg font-semibold text-slate-900">{user.full_name}</h1>
              <p className="text-sm text-slate-600">{user.email}</p>
            </div>
            <Badge variant={user.is_verified ? "success" : "warning"}>
              {user.is_verified ? "Verified" : "Unverified"}
            </Badge>
          </div>
          {!user.is_verified ? (
            <div className="mt-4 flex flex-col gap-2 border-t border-slate-100 pt-4">
              <p className="text-sm text-slate-600">
                Verify your email to unlock the full experience.
              </p>
              {resendSuccess ? (
                <p className="text-sm text-green-700">
                  If your email isn&apos;t verified yet, a new link is on its way.
                </p>
              ) : (
                <Button
                  variant="secondary"
                  size="sm"
                  isLoading={isResending}
                  onClick={() => void handleResend()}
                  className="self-start"
                >
                  Resend verification email
                </Button>
              )}
              {resendError ? <ErrorBanner error={resendError} /> : null}
            </div>
          ) : null}
        </Card>

        <Card>
          <h2 className="mb-4 text-sm font-semibold text-slate-900">Edit profile</h2>
          <form onSubmit={(event) => void handleSave(event)} className="flex flex-col gap-4">
            <Input
              label="Full name"
              value={fullName}
              onChange={(event) => {
                setFullName(event.target.value);
                setSaveSuccess(false);
              }}
              required
            />
            {saveError ? <ErrorBanner error={saveError} /> : null}
            {saveSuccess ? <p className="text-sm text-green-700">Profile updated.</p> : null}
            <Button type="submit" isLoading={isSaving} className="self-start">
              Save changes
            </Button>
          </form>
        </Card>
      </div>
    </PageContainer>
  );
}
