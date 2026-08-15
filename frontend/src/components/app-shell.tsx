"use client";

import { AppSidebar } from "@/components/app-sidebar";
import { Separator } from "@/components/ui/separator";
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { Toaster } from "@/components/ui/sonner";
import { useActiveMachine } from "@/hooks/use-active-machine";

/** Sidebar (rancangan.txt Section 2) hanya tampil SETELAH mesin dipilih —
 * sebelum itu (baru login, atau di /mesin sebelum memilih), user hanya
 * melihat konten halaman polos tanpa navigasi sidebar. `loading` dari
 * useActiveMachine dianggap "belum ada mesin" supaya sidebar tidak
 * berkedip muncul sesaat sebelum localStorage sempat dibaca. */
export function AppShell({ children }: { children: React.ReactNode }) {
  const { machine, loading } = useActiveMachine();
  const showSidebar = !loading && machine !== null;

  if (!showSidebar) {
    return (
      <div className="flex h-svh flex-col overflow-hidden">
        <div className="flex min-h-0 flex-1 flex-col">{children}</div>
        <Toaster richColors position="top-center" />
      </div>
    );
  }

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset className="h-svh overflow-hidden">
        <header className="flex h-14 shrink-0 items-center gap-2 border-b px-4">
          <SidebarTrigger className="-ml-1" />
          <Separator
            orientation="vertical"
            className="mr-2 data-vertical:h-4 data-vertical:self-auto"
          />
          <span className="font-heading text-sm font-semibold">WO.M.AI</span>
        </header>
        <div className="flex min-h-0 flex-1 flex-col">{children}</div>
        <Toaster richColors position="top-center" />
      </SidebarInset>
    </SidebarProvider>
  );
}
