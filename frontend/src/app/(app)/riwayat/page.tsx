"use client";

import Link from "next/link";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Search, Trash2 } from "lucide-react";
import { toast } from "sonner";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectSeparator,
  SelectTrigger,
} from "@/components/ui/select";
import { useSessions } from "@/hooks/use-sessions";
import { useMachines } from "@/hooks/use-machines";
import { clearSessions, deleteSession } from "@/lib/storage";
import { RISK_BADGE, RISK_LABEL } from "@/lib/risk";
import { cn } from "@/lib/utils";

function RiwayatContent() {
  const searchParams = useSearchParams();
  const { sessions } = useSessions();
  const { machines } = useMachines();
  const [query, setQuery] = useState("");
  const [machineFilter, setMachineFilter] = useState<string>(
    () => searchParams.get("mesin") ?? "all",
  );

  const filtered = sessions.filter((s) => {
    const matchesQuery = s.title.toLowerCase().includes(query.toLowerCase());
    const matchesMachine =
      machineFilter === "all" ||
      (machineFilter === "none" ? !s.machineId : s.machineId === machineFilter);
    return matchesQuery && matchesMachine;
  });

  const filterLabel =
    machineFilter === "all"
      ? "All Machines"
      : machineFilter === "none"
        ? "General"
        : (machines.find((m) => m.id === machineFilter)?.name ??
          "Unknown machine");

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-4 overflow-y-auto p-6">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-xl font-semibold">Conversation History</h1>
        <AlertDialog>
          {/* Base UI uses render prop instead of asChild */}
          <AlertDialogTrigger
            disabled={sessions.length === 0}
            render={
              <Button variant="outline" size="sm" />
            }
          >
            Delete All
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete all history?</AlertDialogTitle>
              <AlertDialogDescription>
                All conversation sessions will be permanently deleted from
                this browser.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction
                onClick={async () => {
                  try {
                    await clearSessions();
                    toast.success("All history deleted.");
                  } catch {
                    toast.error("Failed to delete history.");
                  }
                }}
              >
                Delete All
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>

      <div className="flex flex-col gap-2 sm:flex-row">
        <div className="relative flex-1">
          <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search conversations…"
            className="pl-9"
          />
        </div>
        <Select
          value={machineFilter}
          onValueChange={(v) => {
            if (!v) return;
            setMachineFilter(v);
          }}
        >
          <SelectTrigger className="w-full sm:w-[160px]">
            {/* Base UI SelectValue can't read ItemText when popup is closed;
                display the label directly via data-slot span */}
            <span
              data-slot="select-value"
              className="flex flex-1 truncate text-left text-sm"
            >
              {filterLabel}
            </span>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Machines</SelectItem>
            <SelectItem value="none">General</SelectItem>
            {machines.length > 0 && <SelectSeparator />}
            {machines.map((m) => (
              <SelectItem key={m.id} value={m.id}>
                {m.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {filtered.length === 0 && (
        <p className="py-12 text-center text-sm text-muted-foreground">
          {sessions.length === 0
            ? "No saved conversations yet."
            : "No matching results."}
        </p>
      )}

      <div className="flex flex-col gap-2">
        {filtered.map((s) => (
          <Card key={s.id} className="py-0">
            <CardContent className="flex items-center gap-3 p-4">
              <Link
                href={`/chat/${s.id}`}
                className="flex min-w-0 flex-1 flex-col gap-1"
              >
                <span className="truncate font-medium">{s.title}</span>
                <span className="text-xs text-muted-foreground">
                  {new Date(s.updatedAt).toLocaleString("en-US", {
                    dateStyle: "medium",
                    timeStyle: "short",
                  })}
                </span>
              </Link>
              <Badge variant="outline" className="shrink-0">
                {/* Live name while the machine still exists; snapshot once it's been deleted */}
                {(s.machineId
                  ? (machines.find((m) => m.id === s.machineId)?.name ??
                    s.machineName)
                  : s.machineName) ?? "General"}
              </Badge>
              {s.lastPrediction ? (
                <Badge
                  className={cn(
                    "shrink-0",
                    RISK_BADGE[s.lastPrediction.riskLevel],
                  )}
                >
                  {s.lastPrediction.label
                    ? `Potential failure · ${RISK_LABEL[s.lastPrediction.riskLevel]} risk`
                    : "Normal"}
                </Badge>
              ) : (
                <Badge variant="secondary" className="shrink-0">
                  No prediction yet
                </Badge>
              )}
              <Button
                variant="ghost"
                size="icon"
                onClick={async () => {
                  try {
                    await deleteSession(s.id);
                    toast.success("Session deleted.");
                  } catch {
                    toast.error("Failed to delete session.");
                  }
                }}
              >
                <Trash2 className="size-4" />
                <span className="sr-only">Delete session</span>
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

export default function RiwayatPage() {
  return (
    <Suspense fallback={null}>
      <RiwayatContent />
    </Suspense>
  );
}
