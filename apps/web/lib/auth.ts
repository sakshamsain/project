// Accounts: email and password, sessions in Postgres (tables from migration 0006).
// Signing in is optional; without an account a device keeps an anonymous profile.
import { betterAuth } from "better-auth";
import { nextCookies } from "better-auth/next-js";
import { Pool } from "pg";

const holder = globalThis as unknown as { __finnAuthPool?: Pool };

function pool(): Pool {
  if (!holder.__finnAuthPool) {
    const raw = process.env.DATABASE_URL ?? "";
    let connectionString = raw;
    try {
      const u = new URL(raw);
      u.searchParams.delete("channel_binding"); // node-postgres negotiates this itself
      connectionString = u.toString();
    } catch {
      // leave as is; the pool reports a bad URL on first use
    }
    holder.__finnAuthPool = new Pool({ connectionString, max: 3, idleTimeoutMillis: 10_000 });
  }
  return holder.__finnAuthPool;
}

export const auth = betterAuth({
  appName: "FINN",
  database: pool(),
  secret: process.env.BETTER_AUTH_SECRET,
  baseURL: process.env.BETTER_AUTH_URL,
  trustedOrigins: process.env.BETTER_AUTH_URL ? [process.env.BETTER_AUTH_URL] : [],
  emailAndPassword: {
    enabled: true,
    minPasswordLength: 8,
    maxPasswordLength: 128,
    autoSignIn: true,
  },
  session: { expiresIn: 60 * 60 * 24 * 30, updateAge: 60 * 60 * 24 },
  rateLimit: { enabled: true, window: 60, max: 20 },
  plugins: [nextCookies()],
});

export type SessionUser = { id: string; email: string; name: string };
