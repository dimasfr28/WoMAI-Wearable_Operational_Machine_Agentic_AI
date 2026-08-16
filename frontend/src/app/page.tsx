import Link from "next/link";
import Image from "next/image";
import { ArrowDown, ArrowRight } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const NAV_LINKS = [
  { href: "#cara-kerja", label: "Cara Kerja" },
  { href: "#arsitektur", label: "Arsitektur" },
  { href: "#kontak", label: "Kontak" },
];

const CHIP_ROW = [
  "predict_failure()",
  "explain_prediction()",
  "retrieve_sop()",
  "TWF · Keausan tool",
  "HDF · Pembuangan panas",
  "PWF · Daya",
  "OSF · Beban berlebih",
  "RNF · Acak",
  "XGBoost",
  "SHAP",
  "RAG SOP",
];

const STATS = [
  { value: "10.000", label: "titik data AI4I 2020 melatih model" },
  { value: "5", label: "mode kegagalan mesin berputar dikenali" },
];

const STEPS = [
  {
    number: "1",
    title: "Ceritakan kondisinya",
    description:
      "Tanpa form, tanpa kode mesin. Cukup kalimat seperti yang kamu ucapkan ke rekan satu shift.",
    imageLabel: "Foto: teknisi mengetik di ponsel dekat mesin",
    imagePath: "/images/step_describe.webp",
  },
  {
    number: "2",
    title: "Tiga tool bekerja",
    description:
      "Model ML memprediksi kegagalan, SHAP menjelaskan alasannya, RAG mengambil langkah dari SOP maintenance.",
    imageLabel: "Foto: panel kontrol / sensor mesin",
    imagePath: "/images/step_convert.webp",
  },
  {
    number: "3",
    title: "Eksekusi rencananya",
    description:
      "Checklist tindakan berprioritas dengan estimasi waktu, plus hitungan Rupiah bila perbaikan ditunda.",
    imageLabel: "Foto: teknisi melakukan perbaikan",
    imagePath: "/images/step_execute.webp",
  },
];



function ChatDemo() {
  return (
    <div className="bg-card w-full max-w-md rounded-2xl border shadow-sm">
      <div className="flex items-center gap-2 border-b px-4 py-3">
        <span className="relative flex size-2">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
          <span className="relative inline-flex size-2 rounded-full bg-emerald-500" />
        </span>
        <span className="font-mono text-xs tracking-wider uppercase">
          WO.M.AI · Line Produksi 3
        </span>
      </div>
      <div className="flex flex-col gap-3 p-4 text-sm">
        <div
          className="animate-fade-up self-end rounded-2xl rounded-br-sm bg-primary px-4 py-2.5 text-primary-foreground"
          style={{ animationDelay: "0.2s" }}
        >
          motor line 3 suhu prosesnya 310K, torsi 45 Nm, sudah dipakai 200
          menit sejak ganti tool
        </div>
        <div
          className="animate-fade-up flex w-fit flex-wrap items-center gap-x-2 gap-y-0.5 rounded-lg border border-red-200 bg-red-50 px-3 py-1.5 font-mono text-xs text-red-700"
          style={{ animationDelay: "0.9s" }}
        >
          <span className="font-semibold">87%</span>
          <span className="text-red-300">|</span>
          <span>Heat Dissipation Failure</span>
          <span className="text-red-300">|</span>
          <span>Risiko tinggi</span>
        </div>
        <div
          className="animate-fade-up rounded-2xl rounded-bl-sm bg-muted px-4 py-2.5"
          style={{ animationDelay: "1.5s" }}
        >
          Pembuangan panas tidak efektif: selisih suhu udara dan proses terlalu
          sempit. Turunkan beban ke 50% dan periksa sistem pendingin. Kerugian
          bila ditunda 24 jam: Rp300.000.000.
        </div>
        <div
          className="animate-fade-up text-muted-foreground flex items-center gap-2 px-1 font-mono text-xs"
          style={{ animationDelay: "2.1s" }}
        >
          <span>Rencana tindakan</span>
          <span>·</span>
          <span>5 langkah</span>
          <span>·</span>
          <span>±120 menit</span>
        </div>
      </div>
    </div>
  );
}

export default function LandingPage() {
  return (
    <div className="min-h-dvh bg-white">
      {/* Navbar sticky rounded */}
      <header className="sticky top-3 z-50 px-3 sm:px-5">
        <nav className="mx-auto flex max-w-7xl items-center justify-between gap-4 rounded-full border border-slate-200 bg-white/80 px-3 py-2 shadow-sm backdrop-blur-md sm:px-4">
          <Link href="/" className="flex items-center gap-2 pl-1">
            <div className="relative size-8 overflow-hidden rounded-lg shadow-sm">
              <Image
                src="/images/logo_womai_1x1.png"
                alt="WO.M.AI Logo"
                fill
                sizes="32px"
                className="object-cover"
              />
            </div>
            <span className="font-heading text-lg font-semibold text-slate-900">
              WO.M.AI
            </span>
          </Link>
          <div className="hidden items-center gap-6 text-sm text-slate-600 md:flex">
            {NAV_LINKS.map((link) => (
              <a
                key={link.href}
                href={link.href}
                className="hover:text-slate-950 transition-colors"
              >
                {link.label}
              </a>
            ))}
          </div>
          <Link
            href="/mesin"
            className={cn(buttonVariants({ size: "sm" }), "rounded-full")}
          >
            Buka Aplikasi
          </Link>
        </nav>
      </header>

      {/* Hero card */}
      <section className="px-3 pt-8 pb-3 sm:px-5 sm:pt-12 sm:pb-5">
        <div className="relative mx-auto max-w-7xl overflow-hidden rounded-3xl bg-blue-950 text-white">
          {/* Background Image with Dark Blue Overlay */}
          <div className="absolute inset-0">
            <Image
              src="/images/hero_factory.webp"
              alt="Lini produksi pabrik"
              fill
              priority
              className="object-cover opacity-40"
            />
            <div className="absolute inset-0 bg-gradient-to-b from-blue-950/40 via-blue-950/80 to-slate-950" />
          </div>

          <div className="relative flex flex-col gap-12 p-6 sm:p-12">
            <div className="flex max-w-3xl flex-col gap-6 pt-6 sm:pt-10">
              <h1 className="font-heading text-4xl leading-[1.05] font-bold tracking-tight text-balance sm:text-6xl lg:text-7xl">
                Mesin selalu memberi tanda sebelum berhenti.
              </h1>
              <div className="flex items-start gap-3">
                <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full bg-white/10">
                  <ArrowDown className="size-4" />
                </span>
                <p className="max-w-sm text-sm text-blue-100/90">
                  Asisten AI untuk tim maintenance pabrik. Prediksi kegagalan,
                  alasan, dan rencana tindakan dari satu kalimat teknisi, untuk
                  setiap mesin di lini produksimu.
                </p>
              </div>
            </div>

            {/* Kartu anotasi mengambang */}
            <div className="flex justify-end">
              <Link
                href="/mesin"
                className="group flex w-full max-w-sm items-center gap-3 rounded-2xl bg-white p-3 text-slate-900 shadow-lg transition-transform hover:-translate-y-0.5"
              >
                <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-red-50 font-mono text-xs font-semibold text-red-700">
                  87%
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-semibold">
                    Prediksi dalam hitungan detik
                  </span>
                  <span className="text-muted-foreground block truncate text-xs">
                    Heat Dissipation Failure · Risiko tinggi · 5 langkah
                  </span>
                </span>
                <ArrowRight className="text-muted-foreground size-4 shrink-0 transition-transform group-hover:translate-x-0.5" />
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* Statement */}
      <section className="mx-auto grid max-w-7xl gap-10 px-6 py-16 lg:grid-cols-[1fr_1.6fr] lg:py-24">
        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="relative aspect-[4/3] overflow-hidden rounded-2xl border border-blue-200/50 bg-slate-100 shadow-sm">
              <Image
                src="/images/industrial_motor.webp"
                alt="Motor industri"
                fill
                sizes="(max-width: 768px) 50vw, 33vw"
                className="object-cover transition-transform duration-500 hover:scale-105"
              />
            </div>
            <div className="relative aspect-[4/3] overflow-hidden rounded-2xl border border-blue-200/50 bg-slate-100 shadow-sm">
              <Image
                src="/images/maintenance_team.webp"
                alt="Tim maintenance"
                fill
                sizes="(max-width: 768px) 50vw, 33vw"
                className="object-cover transition-transform duration-500 hover:scale-105"
              />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex -space-x-2">
              {["T1", "T2", "T3"].map((t) => (
                <span
                  key={t}
                  className="flex size-8 items-center justify-center rounded-full border-2 border-white bg-blue-200 font-mono text-[10px] font-semibold text-blue-800"
                >
                  {t}
                </span>
              ))}
            </div>
            <p className="text-muted-foreground text-xs">
              Dirancang bersama alur kerja teknisi lapangan.
            </p>
          </div>
        </div>
        <p className="font-heading text-2xl leading-snug font-medium text-slate-400 sm:text-3xl lg:text-4xl">
          Downtime tak terencana menggerus jutaan Rupiah per jam.{" "}
          <span className="text-slate-900">
            WO.M.AI menerjemahkan keluhan teknisi menjadi prediksi kegagalan
            terkalibrasi untuk seluruh mesin di pabrikmu, lengkap dengan alasan
            dan langkah perbaikan,
          </span>{" "}
          sebelum mesin benar-benar berhenti.
        </p>
      </section>

      {/* Chip marquee */}
      <section className="overflow-hidden py-2" aria-hidden>
        <div className="animate-marquee flex w-max gap-3">
          {[...CHIP_ROW, ...CHIP_ROW].map((chip, i) => (
            <span
              key={i}
              className="shrink-0 rounded-full border border-slate-200 bg-white px-4 py-2 font-mono text-xs text-slate-600"
            >
              {chip}
            </span>
          ))}
        </div>
      </section>

      {/* Stats + foto */}
      <section className="mx-auto max-w-7xl px-6 py-16 lg:py-24">
        <h2 className="font-heading mx-auto max-w-lg pb-12 text-center text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
          Perencanaan kerja maintenance yang berbasis data.
        </h2>
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <div className="relative aspect-square overflow-hidden rounded-2xl border border-blue-200/50 bg-slate-100 shadow-sm">
            <Image
              src="/images/fb_factory.webp"
              alt="Pabrik F&B skala menengah"
              fill
              sizes="(max-width: 768px) 50vw, 25vw"
              className="object-cover transition-transform duration-500 hover:scale-105"
            />
          </div>
          {STATS.slice(0, 1).map((stat) => (
            <div
              key={stat.value}
              className="flex aspect-square flex-col justify-between rounded-2xl border border-slate-200 bg-white p-6"
            >
              <span className="font-heading text-primary text-4xl font-bold sm:text-6xl">
                {stat.value}
              </span>
              <span className="text-muted-foreground text-sm">
                {stat.label}
              </span>
            </div>
          ))}
          <div className="relative aspect-square overflow-hidden rounded-2xl border border-blue-200/50 bg-slate-100 shadow-sm">
            <Image
              src="/images/machine_spindle.webp"
              alt="Detail spindle / tool mesin"
              fill
              sizes="(max-width: 768px) 50vw, 25vw"
              className="object-cover transition-transform duration-500 hover:scale-105"
            />
          </div>
          {STATS.slice(1).map((stat) => (
            <div
              key={stat.value}
              className="flex aspect-square flex-col justify-between rounded-2xl border border-slate-200 bg-white p-6"
            >
              <span className="font-heading text-primary text-4xl font-bold sm:text-6xl">
                {stat.value}
              </span>
              <span className="text-muted-foreground text-sm">
                {stat.label}
              </span>
            </div>
          ))}
        </div>
      </section>

      {/* Cara kerja */}
      <section id="cara-kerja" className="mx-auto max-w-7xl scroll-mt-24 px-6 py-16">
        <p className="text-muted-foreground pb-3 font-mono text-xs tracking-[0.2em] uppercase">
          Cara kerja
        </p>
        <h2 className="font-heading max-w-md pb-10 text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
          Dari keluhan teknisi ke rencana tindakan.
        </h2>
        <ol className="grid gap-4 sm:grid-cols-3">
          {STEPS.map((step) => (
            <li
              key={step.number}
              className="flex flex-col gap-4 rounded-2xl border border-slate-200 bg-white p-4"
            >
              <div className="relative aspect-[4/3] overflow-hidden rounded-2xl border border-blue-200/50 bg-slate-100 shadow-sm">
                <Image
                  src={step.imagePath}
                  alt={step.imageLabel}
                  fill
                  sizes="(max-width: 768px) 100vw, 33vw"
                  className="object-cover transition-transform duration-500 hover:scale-105"
                />
              </div>
              <div className="flex flex-col gap-2 px-1 pb-2">
                <span className="text-primary font-mono text-sm">
                  {step.number}
                </span>
                <h3 className="font-heading font-semibold text-slate-900">
                  {step.title}
                </h3>
                <p className="text-muted-foreground text-sm leading-relaxed">
                  {step.description}
                </p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      {/* Arsitektur: demo + copy */}
      <section
        id="arsitektur"
        className="mx-auto grid max-w-7xl scroll-mt-24 items-center gap-10 px-6 py-16 lg:grid-cols-2 lg:py-24"
      >
        <div className="flex justify-center lg:order-2 lg:justify-end">
          <ChatDemo />
        </div>
        <div className="flex flex-col items-start gap-5 lg:order-1">
          <p className="text-muted-foreground font-mono text-xs tracking-[0.2em] uppercase">
            Di balik jawaban
          </p>
          <h2 className="font-heading max-w-md text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
            Bahasa boleh luwes. Keputusan harus terukur.
          </h2>
          <p className="text-muted-foreground max-w-lg text-sm leading-relaxed">
            Prediksi datang dari model XGBoost/Random Forest yang dilatih pada
            dataset AI4I 2020, bukan dari tebakan model bahasa. Probabilitasnya
            terkalibrasi dan setiap prediksi disertai dekomposisi SHAP. LLM
            hanya bertugas memahami kalimat teknisi dan menyusun jawaban.
          </p>
          <Link
            href="/mesin"
            className={cn(buttonVariants({ size: "lg" }), "gap-2 rounded-full")}
          >
            Mulai Percakapan <ArrowRight className="size-4" />
          </Link>
        </div>
      </section>

      {/* Footer gelap */}
      <footer id="kontak" className="p-3 sm:p-5">
        <div className="mx-auto flex max-w-7xl flex-col gap-10 rounded-3xl bg-blue-950 p-8 text-blue-200/80 sm:p-12">
          <div className="flex flex-col justify-between gap-8 sm:flex-row">
            <div className="flex flex-col gap-3">
              <span className="font-mono text-xs tracking-[0.2em] uppercase">
                Siap mencoba?
              </span>
              <p className="max-w-sm text-sm">
                Mulai dari kalimat pertamamu: &quot;motor line 2 getarannya
                kasar sejak pagi&quot;
              </p>
              <Link
                href="/mesin"
                className={cn(
                  buttonVariants({ variant: "secondary" }),
                  "w-fit gap-2 rounded-full",
                )}
              >
                Buka WO.M.AI <ArrowRight className="size-4" />
              </Link>
            </div>
            <div className="flex gap-14 text-sm">
              <div className="flex flex-col gap-2">
                <span className="font-mono text-xs tracking-wide text-blue-300/60 uppercase">
                  Aplikasi
                </span>
                <Link href="/mesin" className="hover:text-white">
                  Chat
                </Link>
                <Link href="/riwayat" className="hover:text-white">
                  Riwayat
                </Link>
              </div>
              <div className="flex flex-col gap-2">
                <span className="font-mono text-xs tracking-wide text-blue-300/60 uppercase">
                  Kompetisi
                </span>
                <span>COMPFEST 18</span>
                <span>AI Innovation Challenge</span>
              </div>
            </div>
          </div>
          <div className="font-heading text-[18vw] leading-none font-bold tracking-tight text-white select-none sm:text-[9rem] lg:text-[13rem]">
            WO.M.AI
          </div>
          <p className="border-t border-blue-900 pt-6 text-xs">
            Dataset: AI4I 2020 Predictive Maintenance Dataset (Stephan Matzka),
            lisensi CC-BY-NC-SA-4.0.
          </p>
        </div>
        <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-2 px-4 pt-5 pb-2 text-xs text-slate-500 sm:flex-row">
          <span>© 2026 WO.M.AI. Seluruh hak cipta.</span>
          <div className="flex items-center gap-5">
            <Link href="/mesin" className="hover:text-slate-900">
              Chat
            </Link>
            <Link href="/riwayat" className="hover:text-slate-900">
              Riwayat
            </Link>
            <a
              href="https://github.com/ArielSulton/womai-ai"
              target="_blank"
              rel="noreferrer"
              className="hover:text-slate-900"
            >
              GitHub
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
