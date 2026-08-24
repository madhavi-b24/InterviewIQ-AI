/**
 * Centralized environment access — the only file that should ever read
 * `import.meta.env` directly. Every other module gets configuration
 * through here, so `localhost` never gets hardcoded elsewhere in the
 * application (see .env.development / .env.production / .env.example).
 */

/**
 * Pure validation, factored out from the `import.meta.env` read itself
 * so it's directly unit-testable without needing to manipulate Vite's
 * module-level env object.
 */
export function requireEnv(key: string, value: string | undefined): string {
  if (!value) {
    throw new Error(
      `Missing required environment variable: ${key}. Copy .env.example to ` +
        `.env.development (or .env.production) and set it.`,
    );
  }
  return value;
}

export const env = {
  apiBaseUrl: requireEnv("VITE_API_BASE_URL", import.meta.env.VITE_API_BASE_URL),
};
