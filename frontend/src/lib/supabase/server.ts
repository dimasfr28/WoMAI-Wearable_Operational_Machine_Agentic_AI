import "server-only";
import { cookies } from "next/headers";
import { createServerClient } from "@supabase/ssr";

/**
 * Supabase client sisi server (Server Components, Route Handlers, Server Actions).
 * Membaca & menulis session lewat cookie request.
 */
export async function createSupabaseServerClient() {
  const cookieStore = await cookies();
  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll();
        },
        setAll(cookiesToSet) {
          try {
            for (const { name, value, options } of cookiesToSet) {
              cookieStore.set(name, value, options);
            }
          } catch {
            // Dipanggil dari Server Component (read-only cookie store) — abaikan;
            // refresh session ditangani middleware.
          }
        },
      },
    },
  );
}

/**
 * Ambil user terautentikasi atau lempar. Dipakai server action/query yang
 * wajib login. `getUser()` memverifikasi JWT ke server Supabase.
 */
export async function requireUser() {
  const supabase = await createSupabaseServerClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) throw new Error("UNAUTHENTICATED");
  return user;
}
