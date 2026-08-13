"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import {
  Factory,
  FileText,
  History,
  LogOut,
  MessageSquarePlus,
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

export function AppSidebar() {
  const { sessions } = useSessions();
  const pathname = usePathname();
  const { isMobile, setOpenMobile } = useSidebar();

  function closeOnMobile() {
    if (isMobile) setOpenMobile(false);
  }

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
                  src="/images/logo_icon.png"
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
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton
                  tooltip="Chat Baru"
                  isActive={pathname === "/chat"}
                  render={<Link href="/chat" onClick={closeOnMobile} />}
                >
                  <MessageSquarePlus />
                  <span>Chat Baru</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton
                  tooltip="Mesin"
                  isActive={pathname === "/mesin"}
                  render={<Link href="/mesin" onClick={closeOnMobile} />}
                >
                  <Factory />
                  <span>Mesin</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton
                  tooltip="SOP File"
                  isActive={pathname === "/sop"}
                  render={<Link href="/sop" onClick={closeOnMobile} />}
                >
                  <FileText />
                  <span>SOP File</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton
                  tooltip="Riwayat"
                  isActive={pathname === "/riwayat"}
                  render={<Link href="/riwayat" onClick={closeOnMobile} />}
                >
                  <History />
                  <span>Riwayat</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarGroup className="group-data-[collapsible=icon]:hidden">
          <SidebarGroupLabel>Terbaru</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {sessions.slice(0, 10).map((s) => (
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
              {sessions.length === 0 && (
                <p className="text-muted-foreground px-2 py-1.5 text-sm">
                  Belum ada percakapan.
                </p>
              )}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <form action={signOutAction}>
              <SidebarMenuButton
                type="submit"
                tooltip="Keluar"
                className="w-full"
              >
                <LogOut />
                <span>Keluar</span>
              </SidebarMenuButton>
            </form>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>

      <SidebarRail />
    </Sidebar>
  );
}
