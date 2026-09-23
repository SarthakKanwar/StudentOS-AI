import { useState, type FormEvent } from "react";
import { DEMO_ACCOUNTS, useAuth, type Role } from "../lib/auth";
import { navigate } from "../lib/router";
import { Wordmark } from "../components/Logo";
import { IconAlert, IconArrowRight } from "../components/icons";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function landingFor(role: Role) {
  return role === "admin" ? "admin" : "app";
}

function AuthAside() {
  return (
    <aside className="auth-aside">
      <a href="#/" onClick={(e) => { e.preventDefault(); navigate(""); }}>
        <Wordmark tone="inverse" />
      </a>

      <div className="auth-aside-body">
        <h2>Every answer carries the page it came from.</h2>
        <p>
          StudentOS retrieves from approved university documents, verifies each
          citation in code, and refuses when the evidence is not there.
        </p>

        <div className="auth-quote">
          <p>
            A confidently wrong exam date is worse than no answer at all, because a
            student acts on it.
          </p>
          <cite>Design principle</cite>
        </div>
      </div>

      <small style={{ color: "rgba(250,248,244,0.36)", fontSize: "var(--text-xs)" }}>
        Academic prototype &middot; synthetic data only
      </small>
    </aside>
  );
}

export function SignIn() {
  const { signIn } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(true);
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function submit(event: FormEvent) {
    event.preventDefault();
    setError("");

    if (!EMAIL_PATTERN.test(email.trim())) {
      setError("Enter a valid email address.");
      return;
    }
    if (!password) {
      setError("Enter your password.");
      return;
    }

    setBusy(true);
    try {
      const session = signIn(email, password, remember);
      navigate(landingFor(session.role));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign in failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth">
      <AuthAside />
      <div className="auth-panel">
        <form className="auth-form enter" onSubmit={submit} noValidate>
          <h1>Sign in</h1>
          <p className="auth-form-sub">Continue to your StudentOS workspace.</p>

          <div className="auth-fields">
            {error && (
              <div className="banner banner-error" role="alert">
                <IconAlert size={15} />
                <span>{error}</span>
              </div>
            )}

            <div className="field">
              <label htmlFor="signin-email">Email address</label>
              <input
                id="signin-email"
                className="input"
                type="email"
                autoComplete="username"
                placeholder="you@university.edu"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                aria-invalid={Boolean(error) && !EMAIL_PATTERN.test(email.trim())}
              />
            </div>

            <div className="field">
              <label htmlFor="signin-password">Password</label>
              <div className="input-group">
                <input
                  id="signin-password"
                  className="input"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  placeholder="Your password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
                <button
                  type="button"
                  className="input-affix"
                  onClick={() => setShowPassword((v) => !v)}
                >
                  {showPassword ? "Hide" : "Show"}
                </button>
              </div>
            </div>

            <div className="auth-row">
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={remember}
                  onChange={(e) => setRemember(e.target.checked)}
                />
                Keep me signed in
              </label>
            </div>

            <button type="submit" className="btn btn-primary btn-lg btn-block" disabled={busy}>
              {busy ? "Signing in..." : "Sign in"}
              {!busy && <IconArrowRight size={15} />}
            </button>
          </div>

          <div className="demo-accounts">
            <div className="demo-accounts-head">
              <span className="label">Demo accounts</span>
            </div>
            {DEMO_ACCOUNTS.map((account) => (
              <button
                type="button"
                className="demo-account"
                key={account.email}
                onClick={() => {
                  setEmail(account.email);
                  setPassword(account.password);
                  setError("");
                }}
              >
                <span className="demo-account-meta">
                  <span className="demo-account-role">
                    {account.role === "admin" ? "Administrator" : "Student"}
                  </span>
                  <span className="demo-account-cred">
                    {account.email} &middot; {account.password}
                  </span>
                </span>
                <span className="label">Use</span>
              </button>
            ))}
          </div>

          <p className="auth-alt">
            No account yet?{" "}
            <button type="button" onClick={() => navigate("signup")}>
              Create one
            </button>
          </p>
        </form>
      </div>
    </div>
  );
}

export function SignUp() {
  const { signUp } = useAuth();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("student");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function submit(event: FormEvent) {
    event.preventDefault();
    setError("");

    if (name.trim().length < 2) {
      setError("Enter your full name.");
      return;
    }
    if (!EMAIL_PATTERN.test(email.trim())) {
      setError("Enter a valid email address.");
      return;
    }
    if (password.length < 8) {
      setError("Choose a password of at least 8 characters.");
      return;
    }

    setBusy(true);
    try {
      const session = signUp({ name: name.trim(), email: email.trim(), password, role });
      navigate(landingFor(session.role));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign up failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth">
      <AuthAside />
      <div className="auth-panel">
        <form className="auth-form enter" onSubmit={submit} noValidate>
          <h1>Create an account</h1>
          <p className="auth-form-sub">
            Prototype accounts are stored in this browser only.
          </p>

          <div className="auth-fields">
            {error && (
              <div className="banner banner-error" role="alert">
                <IconAlert size={15} />
                <span>{error}</span>
              </div>
            )}

            <div className="field">
              <label htmlFor="signup-name">Full name</label>
              <input
                id="signup-name"
                className="input"
                autoComplete="name"
                placeholder="Riya Menon"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>

            <div className="field">
              <label htmlFor="signup-email">Email address</label>
              <input
                id="signup-email"
                className="input"
                type="email"
                autoComplete="username"
                placeholder="you@university.edu"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>

            <div className="field">
              <label htmlFor="signup-password">Password</label>
              <div className="input-group">
                <input
                  id="signup-password"
                  className="input"
                  type={showPassword ? "text" : "password"}
                  autoComplete="new-password"
                  placeholder="At least 8 characters"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
                <button
                  type="button"
                  className="input-affix"
                  onClick={() => setShowPassword((v) => !v)}
                >
                  {showPassword ? "Hide" : "Show"}
                </button>
              </div>
            </div>

            <div className="field">
              <label id="role-label">Role</label>
              <div className="role-grid" role="group" aria-labelledby="role-label">
                <button
                  type="button"
                  className="role-option"
                  aria-pressed={role === "student"}
                  onClick={() => setRole("student")}
                >
                  <strong>Student</strong>
                  <span>Ask questions and read cited answers</span>
                </button>
                <button
                  type="button"
                  className="role-option"
                  aria-pressed={role === "admin"}
                  onClick={() => setRole("admin")}
                >
                  <strong>Administrator</strong>
                  <span>Upload and approve source documents</span>
                </button>
              </div>
            </div>

            <button type="submit" className="btn btn-primary btn-lg btn-block" disabled={busy}>
              {busy ? "Creating account..." : "Create account"}
              {!busy && <IconArrowRight size={15} />}
            </button>
          </div>

          <p className="auth-alt">
            Already have an account?{" "}
            <button type="button" onClick={() => navigate("signin")}>
              Sign in
            </button>
          </p>
        </form>
      </div>
    </div>
  );
}
