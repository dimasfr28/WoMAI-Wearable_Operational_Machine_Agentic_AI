"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import {
  FileBarChart,
  FileText,
  History,
  LogOut,
  MessageSquarePlus,
  Stethoscope,
} from "lucide-react";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  useSidebar,
} from "@/components/ui/sidebar";
import { signOutAction } from "@/app/actions/auth";
import { useSessions } from "@/hooks/use-sessions";
import { useActiveMachine } from "@/hooks/use-active-machine";
import { clearActiveMachineId } from "@/lib/active-machine";

export function AppSidebar() {
  const { sessions } = useSessions();
  const { machine } = useActiveMachine();
  const pathname = usePathname();
  const { isMobile, setOpenMobile } = useSidebar();

  function closeOnMobile() {
    if (isMobile) setOpenMobile(false);
  }

  // Sesi ditampilkan di "Machine Copilot" hanya milik mesin aktif — sesi
  // untuk mesin lain tidak relevan begitu satu mesin sedang aktif dipilih.
  const machineSessions = machine
    ? sessions.filter((s) => s.machineId === machine.id)
    : sessions;

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              size="lg"
              render={<Link href="/" onClick={closeOnMobile} />}
            >
              <div className="relative aspect-square size-8 overflow-hidden rounded-lg">
                <Image
                  src="/images/womai_logo.png"
                  alt="WO.M.AI Logo"
                  fill
                  sizes="32px"
                  className="object-cover"
                />
              </div>
              <div className="grid flex-1 text-left text-sm leading-tight">
                <span className="font-heading truncate font-semibold">
                  WO.M.AI
                </span>
                <span className="text-muted-foreground truncate text-xs">
                  Predictive Maintenance
                </span>
              </div>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        {machine && (
          <SidebarGroup className="group-data-[collapsible=icon]:hidden">
            <SidebarGroupContent>
              <Link
                href="/mesin"
                onClick={closeOnMobile}
                className="flex items-center justify-between rounded-md px-2 py-1.5 text-xs text-muted-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
              >
                <span className="truncate">Machine: {machine.name}</span>
                <span className="shrink-0 underline">Change</span>
              </Link>
            </SidebarGroupContent>
          </SidebarGroup>
        )}

        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton
                  tooltip="New Consultation"
                  isActive={pathname === "/chat"}
                  render={<Link href="/chat" onClick={closeOnMobile} />}
                >
                  <MessageSquarePlus />
                  <span>New Consultation</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton
                  tooltip="Machine Diagnosis"
                  isActive={pathname === "/machine-diagnosis"}
                  render={
                    <Link href="/machine-diagnosis" onClick={closeOnMobile} />
                  }
                >
                  <Stethoscope />
                  <span>Machine Diagnosis</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton
                  tooltip="Machine Report"
                  isActive={pathname === "/machine-report"}
                  render={
                    <Link href="/machine-report" onClick={closeOnMobile} />
                  }
                >
                  <FileBarChart />
                  <span>Machine Report</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton
                  tooltip="Knowledge Base"
                  isActive={pathname === "/sop"}
                  render={<Link href="/sop" onClick={closeOnMobile} />}
                >
                  <FileText />
                  <span>Knowledge Base</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton
                  tooltip="Machine Copilot"
                  isActive={pathname === "/riwayat"}
                  render={<Link href="/riwayat" onClick={closeOnMobile} />}
                >
                  <History />
                  <span>Machine Copilot</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarGroup className="group-data-[collapsible=icon]:hidden">
          <SidebarGroupLabel>Conversation History</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {machineSessions.slice(0, 10).map((s) => (
                <SidebarMenuItem key={s.id}>
                  <SidebarMenuButton
                    isActive={pathname === `/chat/${s.id}`}
                    render={
                      <Link href={`/chat/${s.id}`} onClick={closeOnMobile} />
                    }
                  >
                    <span className="truncate">{s.title}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
              {machineSessions.length === 0 && (
                <p className="text-muted-foreground px-2 py-1.5 text-sm">
                  No conversations yet.
                </p>
              )}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <form
              action={signOutAction}
              // Mesin aktif (localStorage, TIDAK ikut terhapus oleh
              // signOutAction() — itu Server Action, tidak punya akses ke
              // localStorage) dibersihkan di sini sebelum form men-submit ke
              // server, supaya user berikutnya yang login di browser/tab yang
              // sama tidak mewarisi mesin aktif dari sesi sebelumnya.
              onSubmit={() => clearActiveMachineId()}
            >
              <SidebarMenuButton
                type="submit"
                tooltip="Log out"
                className="w-full"
              >
                <LogOut />
                <span>Log out</span>
              </SidebarMenuButton>
            </form>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>

      <SidebarRail />
    </Sidebar>
  );
}
