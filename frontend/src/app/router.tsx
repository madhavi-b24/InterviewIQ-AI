import { createBrowserRouter, type RouteObject } from "react-router-dom";
import { RootLayout } from "./layouts/RootLayout";
import { HomePage } from "./pages/HomePage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { ProtectedRoute, PublicOnlyRoute } from "@/lib/routeGuards";
import { LoginPage } from "@/features/auth/pages/LoginPage";
import { RegisterPage } from "@/features/auth/pages/RegisterPage";
import { ForgotPasswordPage } from "@/features/auth/pages/ForgotPasswordPage";
import { ResetPasswordPage } from "@/features/auth/pages/ResetPasswordPage";
import { VerifyEmailPage } from "@/features/auth/pages/VerifyEmailPage";
import { ProfilePage } from "@/features/auth/pages/ProfilePage";

/**
 * The route tree itself, exported separately from the browser-router
 * instance below — lets tests build a `createMemoryRouter(routeConfig, ...)`
 * for controlled navigation testing without needing to manipulate
 * `window.history`/jsdom's location directly.
 *
 * Stage 2 adds the six auth routes from the frontend plan's route map
 * (§B) under this same `RootLayout`. Guarded per the approved Stage 2
 * scope (§A.7) — PublicOnlyRoute wraps only login/register/forgot-
 * password: those three are pure entry points a signed-in candidate has
 * no reason to land on. reset-password/:token and verify-email/:token
 * are deliberately left as plain, ungated public routes: both are token
 * links a candidate can legitimately open while *already* signed in
 * elsewhere in the same browser (most commonly verify-email, right after
 * register auto-signs them in) — PublicOnlyRoute would redirect them away
 * before the page ever got to act on the token. ProtectedRoute wraps
 * profile. Every later stage's routes land the same way, without needing
 * to restructure this file's shape.
 */
export const routeConfig: RouteObject[] = [
  {
    path: "/",
    element: <RootLayout />,
    children: [
      { index: true, element: <HomePage /> },
      {
        element: <PublicOnlyRoute />,
        children: [
          { path: "login", element: <LoginPage /> },
          { path: "register", element: <RegisterPage /> },
          { path: "forgot-password", element: <ForgotPasswordPage /> },
        ],
      },
      { path: "reset-password/:token", element: <ResetPasswordPage /> },
      { path: "verify-email/:token", element: <VerifyEmailPage /> },
      {
        element: <ProtectedRoute />,
        children: [{ path: "profile", element: <ProfilePage /> }],
      },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];

export const router = createBrowserRouter(routeConfig);
