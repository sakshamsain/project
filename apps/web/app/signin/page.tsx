import Link from "next/link";
import { redirect } from "next/navigation";
import SignInForm from "@/components/SignInForm";
import { sessionUser } from "@/lib/profile";

export const dynamic = "force-dynamic";
export const metadata = { title: "Sign in" };

function safeNext(n: string | undefined): string {
  return n && n.startsWith("/") && !n.startsWith("//") ? n : "/settings";
}

export default async function SignIn({ searchParams }: { searchParams: Promise<{ mode?: string; next?: string }> }) {
  const { mode, next } = await searchParams;
  if (await sessionUser()) redirect(safeNext(next));
  return (
    <main className="page">
      <header className="masthead">
        <Link className="wordmark" href="/">
          FINN
        </Link>
      </header>
      <section className="triage">
        <p className="triage-line" style={{ fontSize: "clamp(1.9rem, 8vw, 2.5rem)" }}>
          {mode === "signup" ? "Create your account" : "Welcome back"}
        </p>
        <p className="triage-sub">
          An account keeps your portfolio, alert limits and notifications on every device. The
          portfolio on this device comes with you.
        </p>
      </section>
      <SignInForm initialMode={mode === "signup" ? "signup" : "signin"} next={safeNext(next)} />
    </main>
  );
}
