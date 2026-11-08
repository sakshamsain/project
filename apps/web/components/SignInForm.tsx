"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { authClient } from "@/lib/auth-client";

export default function SignInForm({ initialMode, next }: { initialMode: "signin" | "signup"; next: string }) {
  const router = useRouter();
  const [mode, setMode] = useState(initialMode);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const res =
      mode === "signup"
        ? await authClient.signUp.email({ name: name.trim() || email.split("@")[0], email: email.trim(), password })
        : await authClient.signIn.email({ email: email.trim(), password });
    setBusy(false);
    if (res.error) {
      const msg = res.error.message ?? "";
      setError(
        res.error.status === 429
          ? "Too many attempts. Wait a minute and try again."
          : /exist/i.test(msg)
            ? "There is already an account with this email. Sign in instead."
            : /invalid|incorrect|not found/i.test(msg)
              ? "That email and password do not match."
              : msg || "Could not sign in. Try again.",
      );
      return;
    }
    router.replace(next);
    router.refresh();
  }

  return (
    <form className="panel auth" onSubmit={submit} noValidate={false}>
      <div className="seg auth-tabs" role="tablist" aria-label="Sign in or create an account">
        <button type="button" role="tab" aria-selected={mode === "signin"} aria-pressed={mode === "signin"} onClick={() => setMode("signin")}>
          Sign in
        </button>
        <button type="button" role="tab" aria-selected={mode === "signup"} aria-pressed={mode === "signup"} onClick={() => setMode("signup")}>
          Create account
        </button>
      </div>
      {mode === "signup" && (
        <div className="field">
          <label htmlFor="name">Name</label>
          <input id="name" type="text" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} />
        </div>
      )}
      <div className="field">
        <label htmlFor="email">Email</label>
        <input
          id="email"
          type="text"
          inputMode="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor="password">Password</label>
        <div className="row-form">
          <input
            id="password"
            type={show ? "text" : "password"}
            autoComplete={mode === "signup" ? "new-password" : "current-password"}
            minLength={8}
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <button type="button" className="button ghost small" onClick={() => setShow(!show)} aria-pressed={show}>
            {show ? "Hide" : "Show"}
          </button>
        </div>
        {mode === "signup" && <span className="help">At least 8 characters.</span>}
      </div>
      {error && (
        <p className="notice" role="alert">
          {error}
        </p>
      )}
      <button className="button" type="submit" disabled={busy}>
        {busy ? "One moment" : mode === "signup" ? "Create account" : "Sign in"}
      </button>
    </form>
  );
}
