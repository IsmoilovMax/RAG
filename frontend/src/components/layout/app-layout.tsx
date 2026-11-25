import { useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { FileText, LayoutDashboard, Menu, MessageSquare, Monitor, Moon, Settings, Sun } from "lucide-react";
import { HealthDot } from "@/components/common";
import { useTheme, type Theme } from "@/components/theme-provider";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useReadiness } from "@/hooks/queries";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/documents", label: "Documents", icon: FileText },
  { to: "/chat", label: "AI Chat", icon: MessageSquare },
  { to: "/settings", label: "Settings", icon: Settings },
];

function Logo() {
  return (
    <div className="flex items-center gap-2.5 px-2">
      <div className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm">
        <svg viewBox="0 0 32 32" className="size-5" aria-hidden>
          <path d="M10 8h7a7 7 0 0 1 0 14h-7z" fill="none" stroke="currentColor" strokeWidth="2.8" strokeLinejoin="round" />
          <circle cx="21.5" cy="22.5" r="3.5" fill="currentColor" opacity=".6" />
        </svg>
      </div>
      <div className="leading-tight">
        <p className="text-sm font-semibold">DocuMind</p>
        <p className="text-[11px] text-muted-foreground">Private document AI</p>
      </div>
    </div>
  );
}

function NavItems({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav className="flex flex-col gap-0.5">
      {NAV.map(({ to, label, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          onClick={onNavigate}
          className={({ isActive }) =>
            cn(
              "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
              isActive
                ? "bg-sidebar-accent text-foreground"
                : "text-sidebar-foreground/80 hover:bg-sidebar-accent/60 hover:text-foreground",
            )
          }
        >
          <Icon className="size-4" />
          {label}
        </NavLink>
      ))}
    </nav>
  );
}

const THEMES: { value: Theme; icon: typeof Sun; label: string }[] = [
  { value: "light", icon: Sun, label: "Light" },
  { value: "dark", icon: Moon, label: "Dark" },
  { value: "system", icon: Monitor, label: "System" },
];

function ThemeSwitcher() {
  const { theme, setTheme } = useTheme();
  return (
    <div className="flex items-center gap-0.5 rounded-lg border bg-background/60 p-0.5">
      {THEMES.map(({ value, icon: Icon, label }) => (
        <Tooltip key={value}>
          <TooltipTrigger asChild>
            <button
              type="button"
              aria-label={`${label} theme`}
              onClick={() => setTheme(value)}
              className={cn(
                "flex h-7 flex-1 items-center justify-center rounded-md px-2 text-muted-foreground transition-colors",
                theme === value ? "bg-accent text-foreground shadow-xs" : "hover:text-foreground",
              )}
            >
              <Icon className="size-3.5" />
            </button>
          </TooltipTrigger>
          <TooltipContent>{label}</TooltipContent>
        </Tooltip>
      ))}
    </div>
  );
}

function SystemStatus() {
  const { data, isError } = useReadiness();
  const llm = data?.components.llm;
  const status = isError ? "error" : data?.status;
  const label = isError
    ? "Backend unreachable"
    : !data
      ? "Checking…"
      : status === "ok"
        ? "All systems operational"
        : status === "degraded"
          ? "Partially available"
          : "Service error";
  return (
    <NavLink to="/" className="block rounded-lg border bg-background/60 p-3 text-xs transition-colors hover:bg-accent/40">
      <div className="flex items-center gap-2 font-medium">
        <HealthDot status={status} />
        {label}
      </div>
      {llm && (
        <p className="mt-1 truncate text-muted-foreground" title={String(llm.info.model ?? "")}>
          LLM: {String(llm.info.model ?? "—")}
        </p>
      )}
    </NavLink>
  );
}

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <div className="flex h-full flex-col gap-6 p-3">
      <div className="pt-2">
        <Logo />
      </div>
      <NavItems onNavigate={onNavigate} />
      <div className="mt-auto space-y-3">
        <SystemStatus />
        <ThemeSwitcher />
      </div>
    </div>
  );
}

export function AppLayout() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();
  const fullBleed = location.pathname.startsWith("/chat");

  return (
    <div className="flex h-dvh overflow-hidden">
      <aside className="hidden w-60 shrink-0 border-r border-sidebar-border bg-sidebar md:block">
        <SidebarContent />
      </aside>

      <Dialog open={mobileOpen} onOpenChange={setMobileOpen}>
        <DialogContent
          showCloseButton={false}
          className="top-0 left-0 h-dvh max-h-dvh w-64 max-w-64 translate-x-0 translate-y-0 rounded-none border-r bg-sidebar p-0 data-[state=closed]:slide-out-to-left data-[state=open]:slide-in-from-left sm:max-w-64"
        >
          <DialogTitle className="sr-only">Navigation</DialogTitle>
          <SidebarContent onNavigate={() => setMobileOpen(false)} />
        </DialogContent>
      </Dialog>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-3 border-b px-4 md:hidden">
          <Button variant="ghost" size="icon-sm" onClick={() => setMobileOpen(true)} aria-label="Open navigation">
            <Menu />
          </Button>
          <Logo />
        </header>
        <main className={cn("min-h-0 flex-1", fullBleed ? "overflow-hidden" : "overflow-y-auto")}>
          {fullBleed ? (
            <Outlet />
          ) : (
            <div className="mx-auto w-full max-w-6xl space-y-6 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
              <Outlet />
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
