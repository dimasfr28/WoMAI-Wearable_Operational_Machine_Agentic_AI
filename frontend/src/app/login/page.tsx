"use client";

import { Suspense, useActionState, useEffect } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { loginAction, type AuthActionState } from "@/app/actions/auth";
import { clearActiveMachineId } from "@/lib/active-machine";

const initialState: AuthActionState = {};

function LoginForm() {
  const searchParams = useSearchParams();
  const next = searchParams.get("next") ?? "/mesin";
  const justRegistered = searchParams.get("registered") === "1";
  const [state, formAction, pending] = useActionState(
    loginAction,
    initialState,
  );

  // Mesin aktif (localStorage) dibersihkan setiap kali halaman ini dimuat —
  // baik karena logout manual, sesi kadaluarsa (401 dari backend, lihat
  // lib/backend-fetch.ts), token invalid setelah backend restart (lihat
  // app/config.py's JWT_SECRET acak per-start), maupun belum pernah login
  // sama sekali. Login ulang harus selalu mulai dari /mesin, tidak boleh
  // mewarisi mesin aktif dari sesi sebelumnya.
  useEffect(() => {
    clearActiveMachineId();
  }, []);

  return (
    <div className="flex min-h-svh items-center justify-center p-6">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="font-heading">Masuk ke WO.M.AI</CardTitle>
          <CardDescription>
            {justRegistered
              ? "Akun dibuat, silakan masuk."
              : "Masuk untuk mengakses mesin & riwayat percakapan."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form action={formAction} className="flex flex-col gap-4">
            <input type="hidden" name="next" value={next} />
            <div className="flex flex-col gap-2">
              <Label htmlFor="username">Username</Label>
              <Input
                id="username"
                name="username"
                type="text"
                autoComplete="username"
                placeholder="nama.pengguna"
                required
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="password">Kata sandi</Label>
              <Input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                placeholder="Kata sandi"
                required
              />
            </div>
            {state.error && (
              <p className="text-sm text-destructive">{state.error}</p>
            )}
            <Button type="submit" disabled={pending}>
              {pending ? "Memproses…" : "Masuk"}
            </Button>
          </form>
          <Link
            href="/register"
            className="mt-4 block w-full text-center text-sm text-muted-foreground hover:text-foreground"
          >
            Belum punya akun? Daftar
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}
