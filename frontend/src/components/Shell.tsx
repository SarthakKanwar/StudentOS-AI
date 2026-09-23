import { useEffect, useState, type ReactNode } from "react";
import { initials, useAuth, type Role } from "../lib/auth";
import { navigate, useRoute } from "../lib/router";
import { Wordmark } from "./Logo";
import {
  IconActivity,
  IconAsk,
  IconClose,
  IconDocuments,
  IconHistory,
  IconLogout,
  IconMenu,
  IconOverview,
  IconProfile,
  IconSettings,
  IconSources,
  IconUpload,
} from "./icons";

interface NavEntry {
  route: string;
  label: string;
  icon: (p: { size?: number }) => JSX.Element;
}

const STUDENT_NAV: NavEntry[] = [
  { route: "app", label: "Overview", icon: IconOverview },
  { route: "app/ask", label: "Ask StudentOS", icon: IconAsk },
  { route: "app/sources", label: "Sources", icon: IconSources },
  { route: "app/history", label: "History", icon: IconHistory },
  { route: "app/profile", label: "Profile", icon: IconProfile },
];

const ADMIN_NAV: NavEntry[] = [
  { route: "admin", label: "Overview", icon: IconOverview },
  { route: "admin/documents", label: "Documents", icon: IconDocuments },
  { route: "admin/upload", label: "Upload", icon: IconUpload },
  { route: "admin/activity", label: "Activity", icon: IconActivity },
  { route: "admin/settings", label: "Settings", icon: IconSettings },
];

export function navFor(role: Role): NavEntry[] {
  return role === "admin" ? ADMIN_NAV : STUDENT_NAV;
}

interface ShellProps {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
}

export function Shell({ title, subtitle, actions, children }: ShellProps) {
  const { session, signOut } = useAuth();
  const [route] = useRoute();
  const [navOpen, setNavOpen] = useState(false);

  useEffect(() => {
    setNavOpen(false);
  }, [route]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setNavOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (!session) return null;

  const entries = navFor(session.role);

  return (
    <div className="shell" data-nav={navOpen ? "open" : "closed"}>
      <div className="scrim" onClick={() => setNavOpen(false)} aria-hidden="true" />

      <aside className="sidebar">
        <div className="sidebar-brand spread row">
          <a href="#/app" onClick={(e) => { e.preventDefault(); navigate(session.role === "admin" ? "admin" : "app"); }}>
            <Wordmark tone="inverse" />
          </a>
          <button
            type="button"
            className="btn btn-ghost menu-toggle"
            style={{ color: "rgba(250,248,244,0.7)" }}
            onClick={() => setNavOpen(false)}
            aria-label="Close navigation"
          >
            <IconClose />
          </button>
        </div>

        <div className="sidebar-role">
          <div className="label">{session.role === "admin" ? "Knowledge base" : "Workspace"}</div>
          <div className="sidebar-role-name">
            {session.role === "admin" ? "Admin console" : "Student"}
          </div>
        </div>

        <nav className="sidebar-nav" aria-label="Primary">
          {entries.map((entry) => {
            const Icon = entry.icon;
            const active = route === entry.route;
            return (
              <button
                key={entry.route}
                type="button"
                className="nav-item"
                aria-current={active ? "page" : undefined}
                onClick={() => navigate(entry.route)}
              >
                <Icon size={16} />
                {entry.label}
              </button>
            );
          })}
        </nav>

        <div className="sidebar-foot">
          <div className="sidebar-user">
            <span className="avatar">{initials(session.name)}</span>
            <span className="sidebar-user-meta">
              <span className="sidebar-user-name">{session.name}</span>
              <span className="sidebar-user-email">{session.email}</span>
            </span>
          </div>
          <button
            type="button"
            className="btn btn-ghost sidebar-logout"
            onClick={() => {
              signOut();
              // Explicit destination: the route guard would send a signed-out
              // user here anyway, so say so rather than relying on that race.
              navigate("signin");
            }}
          >
            <IconLogout size={15} />
            Sign out
          </button>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <div className="row row-3" style={{ minWidth: 0 }}>
            <button
              type="button"
              className="btn btn-ghost menu-toggle"
              onClick={() => setNavOpen(true)}
              aria-label="Open navigation"
            >
              <IconMenu />
            </button>
            <div className="topbar-title">
              <h1>{title}</h1>
              {subtitle && <span className="topbar-sub">{subtitle}</span>}
            </div>
          </div>
          {actions && <div className="row row-2">{actions}</div>}
        </header>

        <div className="content">{children}</div>
      </div>
    </div>
  );
}
