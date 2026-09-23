import { useEffect } from "react";
import { useAuth } from "./lib/auth";
import { navigate, useRoute } from "./lib/router";
import { Landing } from "./pages/Landing";
import { SignIn, SignUp } from "./pages/Auth";
import {
  StudentAsk,
  StudentHistory,
  StudentOverview,
  StudentProfile,
  StudentSources,
} from "./pages/student";
import {
  AdminActivity,
  AdminDocuments,
  AdminOverview,
  AdminSettings,
  AdminUpload,
} from "./pages/admin";

type Page = () => JSX.Element | null;

const STUDENT_ROUTES: Record<string, Page> = {
  app: StudentOverview,
  "app/ask": StudentAsk,
  "app/sources": StudentSources,
  "app/history": StudentHistory,
  "app/profile": StudentProfile,
};

const ADMIN_ROUTES: Record<string, Page> = {
  admin: AdminOverview,
  "admin/documents": AdminDocuments,
  "admin/upload": AdminUpload,
  "admin/activity": AdminActivity,
  "admin/settings": AdminSettings,
};

function homeFor(role: "student" | "admin") {
  return role === "admin" ? "admin" : "app";
}

export default function App() {
  const { session, ready } = useAuth();
  const [route] = useRoute();

  const isStudentRoute = route === "app" || route.startsWith("app/");
  const isAdminRoute = route === "admin" || route.startsWith("admin/");
  const isProtected = isStudentRoute || isAdminRoute;

  /* Guards run as an effect so redirects happen after the session has been read
     from storage — otherwise a refresh on a protected route would bounce the
     user to sign-in before the session is restored. */
  useEffect(() => {
    if (!ready) return;

    if (isProtected && !session) {
      navigate("signin");
      return;
    }
    if (session && isAdminRoute && session.role !== "admin") {
      navigate("app");
      return;
    }
    if (session && isStudentRoute && session.role !== "student") {
      navigate("admin");
      return;
    }
    if (session && (route === "" || route === "signin" || route === "signup")) {
      navigate(homeFor(session.role));
    }
  }, [ready, session, route, isProtected, isAdminRoute, isStudentRoute]);

  if (!ready) {
    return (
      <div style={{ display: "grid", placeItems: "center", minHeight: "100vh" }}>
        <span className="spinner" />
      </div>
    );
  }

  if (isProtected && session) {
    const table = session.role === "admin" ? ADMIN_ROUTES : STUDENT_ROUTES;
    const Page = table[route];
    if (Page) return <Page />;

    const Fallback = session.role === "admin" ? AdminOverview : StudentOverview;
    return <Fallback />;
  }

  if (route === "signin") return <SignIn />;
  if (route === "signup") return <SignUp />;
  if (isProtected) return null; // guard effect is redirecting

  return <Landing />;
}
