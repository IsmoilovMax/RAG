import { lazy, Suspense } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { AppLayout } from "@/components/layout/app-layout";
import { ThemeProvider } from "@/components/theme-provider";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ApiError } from "@/lib/api";

const DashboardPage = lazy(() => import("@/pages/dashboard"));
const DocumentsPage = lazy(() => import("@/pages/documents"));
const ChatPage = lazy(() => import("@/pages/chat"));
const SettingsPage = lazy(() => import("@/pages/settings"));

function PageFallback() {
  return (
    <div className="flex h-64 items-center justify-center text-muted-foreground">
      <Loader2 className="size-5 animate-spin" />
    </div>
  );
}

const page = (node: React.ReactNode) => <Suspense fallback={<PageFallback />}>{node}</Suspense>;

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: (count, error) => !(error instanceof ApiError && error.status >= 400 && error.status < 500) && count < 2,
    },
  },
});

export default function App() {
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>
          <BrowserRouter>
            <Routes>
              <Route element={<AppLayout />}>
                <Route index element={page(<DashboardPage />)} />
                <Route path="documents" element={page(<DocumentsPage />)} />
                {/* Single route with an optional segment so starting a new chat
                    (/chat -> /chat/:id) never remounts the page mid-stream. */}
                <Route path="chat/:conversationId?" element={page(<ChatPage />)} />
                <Route path="settings" element={page(<SettingsPage />)} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Route>
            </Routes>
          </BrowserRouter>
          <Toaster />
        </TooltipProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
