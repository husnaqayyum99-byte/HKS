import { useEffect, useRef, useState } from "react";
import Navbar from "./components/Navbar.jsx";
import Footer from "./components/Footer.jsx";
import Home from "./pages/Home.jsx";
import Login from "./pages/Login.jsx";
import ForgotPassword from "./pages/ForgotPassword.jsx";
import ResetPassword from "./pages/ResetPassword.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import PublicAnalysis from "./pages/PublicAnalysis.jsx";
import Alert from "./components/Alert.jsx";
import { useLanguage } from "./i18n/LanguageContext.jsx";
import { useAuth } from "./context/AuthContext.jsx";

export default function App() {
  const { t } = useLanguage();
  const { user, session, loading: authLoading, logout, authError, setAuthError } = useAuth();
  const [pathname, setPathname] = useState(() => window.location.pathname);
  const mainRef = useRef(null);

  useEffect(() => {
    const syncPathname = () => setPathname(window.location.pathname);
    window.addEventListener("popstate", syncPathname);
    return () => window.removeEventListener("popstate", syncPathname);
  }, []);

  function navigate(path, replace = false) {
    if (window.location.pathname !== path) {
      window.history[replace ? "replaceState" : "pushState"]({}, "", path);
      setPathname(path);
    }
  }

  useEffect(() => {
    if (authLoading) return;
    if (user && !pathname.startsWith("/app") && !["/forgot-password", "/reset-password", "/analysis"].includes(pathname)) navigate("/app", true);
    if (!user && pathname.startsWith("/app")) navigate("/login", true);
  }, [authLoading, user, pathname]);

  useEffect(() => {
    window.scrollTo(0, 0);
    mainRef.current?.focus({ preventScroll: true });
  }, [pathname]);

  function goToSection(id) {
    if (window.location.pathname !== "/") navigate("/");
    setTimeout(() => document.getElementById(id)?.scrollIntoView({ behavior: "smooth" }), 50);
  }

  async function handleLogout() {
    setAuthError("");
    try {
      await logout();
      navigate("/", true);
    } catch {
      // Keep the protected view open if the backend session cannot be ended.
    }
  }

  const inApp = pathname.startsWith("/app");
  const onAuthPage = ["/login", "/signup", "/forgot-password", "/reset-password"].includes(pathname);
  const authMode = pathname === "/signup" ? "signup" : "login";

  return (
    <>
      <a className="skip-link" href="#main">{t("skip")}</a>
      {!inApp && (
        <Navbar
          user={user}
          onHome={() => navigate(user ? "/app" : "/")}
          onNavigate={goToSection}
          onStart={() => navigate("/signup")}
          onLogin={() => navigate("/login")}
          onLogout={handleLogout}
          onAccount={() => navigate("/app")}
        />
      )}
      <main id="main" ref={mainRef} tabIndex={-1}>
        {inApp && user && !authLoading ? (
          <Dashboard
            pathname={pathname}
            navigate={navigate}
            user={user}
            accessToken={session?.access_token}
            onLogout={handleLogout}
            authError={authError}
            onDismissAuthError={() => setAuthError("")}
          />
        ) : inApp || authLoading ? (
          <div className="container flow-page">
            <div className="status" role="status">
              <span className="loader" aria-hidden="true" />
              <p>{t("auth.restoringSession")}</p>
            </div>
          </div>
        ) : (
          <div key={pathname} className="page-fade">
            {!user && authError && !onAuthPage && (
              <div className="container flow-page">
                <Alert tone="error" icon="alert" role="alert">{t(`auth.${authError}`)}</Alert>
              </div>
            )}
            {["/login", "/signup"].includes(pathname) && !user && (
              <Login
                initialMode={authMode}
                onAuthenticated={() => navigate("/app", true)}
                onModeChange={(mode) => navigate(mode === "signup" ? "/signup" : "/login")}
                onForgotPassword={() => navigate("/forgot-password")}
              />
            )}
            {pathname === "/forgot-password" && (
              <ForgotPassword onBack={() => navigate("/login")} />
            )}
            {pathname === "/reset-password" && (
              <ResetPassword onComplete={() => navigate("/login", true)} onBack={() => navigate("/login")} />
            )}
            {pathname === "/analysis" && <PublicAnalysis />}
            {!onAuthPage && pathname !== "/analysis" && (
              <Home onStart={() => navigate("/signup")} onAnalyze={() => navigate("/analysis")} />
            )}
          </div>
        )}
      </main>
      {!inApp && <Footer />}
    </>
  );
}
