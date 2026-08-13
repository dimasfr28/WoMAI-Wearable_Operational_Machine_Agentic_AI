import Link from "next/link";
import { History, MessageSquarePlus, WifiOff } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export const metadata = {
  title: "Offline · WO.M.AI",
};

export default function OfflinePage() {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-6 px-6 text-center">
      <div className="bg-muted flex size-14 items-center justify-center rounded-full">
        <WifiOff className="text-muted-foreground size-6" />
      </div>
      <div className="flex flex-col gap-2">
        <h1 className="font-heading text-2xl font-bold">Kamu sedang offline</h1>
        <p className="text-muted-foreground max-w-sm text-sm">
          Halaman yang diminta belum tersimpan di perangkat ini. Riwayat dan
          checklist yang sudah pernah dibuka tetap bisa diakses tanpa koneksi.
        </p>
      </div>
      <div className="flex flex-wrap items-center justify-center gap-3">
        <Link href="/chat" className={cn(buttonVariants(), "gap-2")}>
          <MessageSquarePlus className="size-4" /> Buka Chat
        </Link>
        <Link
          href="/riwayat"
          className={cn(buttonVariants({ variant: "outline" }), "gap-2")}
        >
          <History className="size-4" /> Lihat Riwayat
        </Link>
      </div>
    </div>
  );
}
