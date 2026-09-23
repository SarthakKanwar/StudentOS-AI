import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type Role = "student" | "admin";

export interface Account {
  name: string;
  email: string;
  password: string;
  role: Role;
}

export interface Session {
  name: string;
  email: string;
  role: Role;
}

const ACCOUNTS_KEY = "studentos.accounts";
const SESSION_KEY = "studentos.session";

/* Prototype credentials. Deliberately non-real: the .local TLD is reserved and
   never resolves, and the passwords are printed in the UI. */
export const DEMO_ACCOUNTS: Account[] = [
  {
    name: "Riya Menon",
    email: "student@demo.studentos.local",
    password: "demo-student-2026",
    role: "student",
  },
  {
    name: "Dr. Arun Bose",
    email: "admin@demo.studentos.local",
    password: "demo-admin-2026",
    role: "admin",
  },
];

function readAccounts(): Account[] {
  try {
    const stored = localStorage.getItem(ACCOUNTS_KEY);
    const parsed: Account[] = stored ? JSON.parse(stored) : [];
    const extra = parsed.filter(
      (account) => !DEMO_ACCOUNTS.some((demo) => demo.email === account.email),
    );
    return [...DEMO_ACCOUNTS, ...extra];
  } catch {
    return [...DEMO_ACCOUNTS];
  }
}

function writeAccounts(accounts: Account[]) {
  const custom = accounts.filter(
    (account) => !DEMO_ACCOUNTS.some((demo) => demo.email === account.email),
  );
  localStorage.setItem(ACCOUNTS_KEY, JSON.stringify(custom));
}

/* Session lives in localStorage when "remember me" is on, sessionStorage
   otherwise. Reading both is what makes a refresh preserve the session. */
function readSession(): Session | null {
  for (const store of [localStorage, sessionStorage]) {
    try {
      const raw = store.getItem(SESSION_KEY);
      if (raw) return JSON.parse(raw) as Session;
    } catch {
      /* corrupt entry — fall through and treat as signed out */
    }
  }
  return null;
}

interface AuthValue {
  session: Session | null;
  ready: boolean;
  signIn: (email: string, password: string, remember: boolean) => Session;
  signUp: (input: Omit<Account, "password"> & { password: string }) => Session;
  signOut: () => void;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setSession(readSession());
    setReady(true);
  }, []);

  const persist = useCallback((next: Session, remember: boolean) => {
    const store = remember ? localStorage : sessionStorage;
    const other = remember ? sessionStorage : localStorage;
    store.setItem(SESSION_KEY, JSON.stringify(next));
    other.removeItem(SESSION_KEY);
    setSession(next);
  }, []);

  const signIn = useCallback(
    (email: string, password: string, remember: boolean) => {
      const normalised = email.trim().toLowerCase();
      const account = readAccounts().find((item) => item.email.toLowerCase() === normalised);

      if (!account) {
        throw new Error("No account exists for that email address.");
      }
      if (account.password !== password) {
        throw new Error("That password does not match our records.");
      }

      const next: Session = { name: account.name, email: account.email, role: account.role };
      persist(next, remember);
      return next;
    },
    [persist],
  );

  const signUp = useCallback(
    (input: Account) => {
      const normalised = input.email.trim().toLowerCase();
      const accounts = readAccounts();

      if (accounts.some((item) => item.email.toLowerCase() === normalised)) {
        throw new Error("An account already exists for that email address.");
      }

      const account: Account = { ...input, email: normalised };
      writeAccounts([...accounts, account]);

      const next: Session = { name: account.name, email: account.email, role: account.role };
      persist(next, true);
      return next;
    },
    [persist],
  );

  const signOut = useCallback(() => {
    localStorage.removeItem(SESSION_KEY);
    sessionStorage.removeItem(SESSION_KEY);
    setSession(null);
  }, []);

  const value = useMemo(
    () => ({ session, ready, signIn, signUp, signOut }),
    [session, ready, signIn, signUp, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}
