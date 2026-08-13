"use client";

import { useActionState } from "react";
import Link from "next/link";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { registerAction, type AuthActionState } from "@/app/actions/auth";

const initialState: AuthActionState = {};

export default function RegisterPage() {
  const [state, formAction, pending] = useActionState(
    registerAction,
    initialState,
  );

  return (
    <div className="flex min-h-svh items-center justify-center p-6">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="font-heading">Buat akun WO.M.AI</CardTitle>
          <CardDescription>
            Daftar untuk mulai memakai WO.M.AI. Registrasi publik hanya
            terbuka sebelum akun pertama dibuat.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form action={formAction} className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="username">Username</Label>
              <Input
                id="username"
                name="username"
                type="text"
                autoComplete="username"
                required
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                placeholder="nama@pabrik.co.id"
                required
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="full_name">Nama lengkap (opsional)</Label>
              <Input id="full_name" name="full_name" type="text" autoComplete="name" />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="password">Kata sandi</Label>
              <Input
                id="password"
                name="password"
                type="password"
                autoComplete="new-password"
                placeholder="Minimal 6 karakter"
                required
                minLength={6}
              />
            </div>
            {state.error && (
              <p className="text-sm text-destructive">{state.error}</p>
            )}
            <Button type="submit" disabled={pending}>
              {pending ? "Memproses…" : "Daftar"}
            </Button>
          </form>
          <Link
            href="/login"
            className="mt-4 block w-full text-center text-sm text-muted-foreground hover:text-foreground"
          >
            Sudah punya akun? Masuk
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}
