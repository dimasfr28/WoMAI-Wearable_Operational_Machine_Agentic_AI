import Link from "next/link";
import Image from "next/image";
import { ArrowDown, ArrowRight } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const NAV_LINKS = [
  { href: "#cara-kerja", label: "How It Works" },
  { href: "#arsitektur", label: "Architecture" },
  { href: "#kontak", label: "Contact" },
];

const CHIP_ROW = [
  "predict_failure()",
  "explain_prediction()",
  "retrieve_sop()",
  "TWF · Tool Wear",
  "HDF · Heat Dissipation",
  "PWF · Power",
  "OSF · Overstrain",
  "RNF · Random",
  "XGBoost",
  "SHAP",
  "RAG SOP",
];

const STATS = [
  { value: "10,000", label: "AI4I 2020 data points trained the model" },
  { value: "5", label: "rotating-machine failure modes recognized" },
];

const STEPS = [
  {
    number: "1",
    title: "Describe the condition",
    description:
      "No forms, no machine codes. Just a sentence like the one you'd say to a teammate on shift.",
    imageLabel: "Photo: technician typing on a phone near a machine",
    imagePath: "/images/step_describe.webp",
  },
  {
    number: "2",
    title: "Three tools at work",
    description:
      "The ML model predicts the failure, SHAP explains why, and RAG pulls the steps from the maintenance SOP.",
    imageLabel: "Photo: control panel / machine sensors",
    imagePath: "/images/step_convert.webp",
  },
  {
    number: "3",
    title: "Execute the plan",
    description:
      "A prioritized action checklist with time estimates, plus the cost if the repair is delayed.",
    imageLabel: "Photo: technician performing a repair",
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
          WO.M.AI · Production Line 3
        </span>
      </div>
      <div className="flex flex-col gap-3 p-4 text-sm">
        <div
          className="animate-fade-up self-end rounded-2xl rounded-br-sm bg-primary px-4 py-2.5 text-primary-foreground"
          style={{ animationDelay: "0.2s" }}
        >
          line 3 motor process temp is 310K, torque 45 Nm, been running 200
          minutes since the last tool change
        </div>
        <div
          className="animate-fade-up flex w-fit flex-wrap items-center gap-x-2 gap-y-0.5 rounded-lg border border-red-200 bg-red-50 px-3 py-1.5 font-mono text-xs text-red-700"
          style={{ animationDelay: "0.9s" }}
        >
          <span className="font-semibold">87%</span>
          <span className="text-red-300">|</span>
          <span>Heat Dissipation Failure</span>
          <span className="text-red-300">|</span>
          <span>High risk</span>
        </div>
        <div
          className="animate-fade-up rounded-2xl rounded-bl-sm bg-muted px-4 py-2.5"
          style={{ animationDelay: "1.5s" }}
        >
          Heat dissipation is ineffective: the gap between air and process
          temperature is too narrow. Reduce load to 50% and check the
          cooling system. Cost of a 24-hour delay: Rp300,000,000.
        </div>
        <div
          className="animate-fade-up text-muted-foreground flex items-center gap-2 px-1 font-mono text-xs"
          style={{ animationDelay: "2.1s" }}
        >
          <span>Action plan</span>
          <span>·</span>
          <span>5 steps</span>
          <span>·</span>
          <span>±120 min</span>
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
                src="/images/womai_logo.png"
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
            Open App
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
              alt="Factory production line"
              fill
              priority
              className="object-cover opacity-40"
            />
            <div className="absolute inset-0 bg-gradient-to-b from-blue-950/40 via-blue-950/80 to-slate-950" />
          </div>

          <div className="relative flex flex-col gap-12 p-6 sm:p-12">
            <div className="flex max-w-3xl flex-col gap-6 pt-6 sm:pt-10">
              <h1 className="font-heading text-4xl leading-[1.05] font-bold tracking-tight text-balance sm:text-6xl lg:text-7xl">
                Machines always signal before they stop.
              </h1>
              <div className="flex items-start gap-3">
                <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full bg-white/10">
                  <ArrowDown className="size-4" />
                </span>
                <p className="max-w-sm text-sm text-blue-100/90">
                  An AI assistant for factory maintenance teams. Failure
                  prediction, reasoning, and an action plan from one
                  technician&apos;s sentence, for every machine on your
                  production line.
                </p>
              </div>
            </div>

            {/* Floating annotation card */}
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
                    Prediction in seconds
                  </span>
                  <span className="text-muted-foreground block truncate text-xs">
                    Heat Dissipation Failure · High risk · 5 steps
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
                alt="Industrial motor"
                fill
                sizes="(max-width: 768px) 50vw, 33vw"
                className="object-cover transition-transform duration-500 hover:scale-105"
              />
            </div>
            <div className="relative aspect-[4/3] overflow-hidden rounded-2xl border border-blue-200/50 bg-slate-100 shadow-sm">
              <Image
                src="/images/maintenance_team.webp"
                alt="Maintenance team"
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
              Designed alongside field technicians&apos; workflow.
            </p>
          </div>
        </div>
        <p className="font-heading text-2xl leading-snug font-medium text-slate-400 sm:text-3xl lg:text-4xl">
          Unplanned downtime burns through millions of Rupiah every hour.{" "}
          <span className="text-slate-900">
            WO.M.AI turns a technician&apos;s complaint into a calibrated
            failure prediction for every machine in your factory, complete
            with the reasoning and repair steps,
          </span>{" "}
          before the machine actually stops.
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
          Data-driven maintenance work planning.
        </h2>
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <div className="relative aspect-square overflow-hidden rounded-2xl border border-blue-200/50 bg-slate-100 shadow-sm">
            <Image
              src="/images/fb_factory.webp"
              alt="Mid-size F&B factory"
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
              alt="Detail of machine spindle / tool"
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
          How it works
        </p>
        <h2 className="font-heading max-w-md pb-10 text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
          From a technician&apos;s complaint to an action plan.
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
            Behind the answer
          </p>
          <h2 className="font-heading max-w-md text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
            Language can be casual. Decisions must be measured.
          </h2>
          <p className="text-muted-foreground max-w-lg text-sm leading-relaxed">
            The prediction comes from an XGBoost/Random Forest model trained
            on the AI4I 2020 dataset, not a language model&apos;s guess. Its
            probability is calibrated, and every prediction comes with a
            SHAP breakdown. The LLM&apos;s only job is to understand the
            technician&apos;s sentence and compose the answer.
          </p>
          <Link
            href="/mesin"
            className={cn(buttonVariants({ size: "lg" }), "gap-2 rounded-full")}
          >
            Start a Conversation <ArrowRight className="size-4" />
          </Link>
        </div>
      </section>

      {/* Footer gelap */}
      <footer id="kontak" className="p-3 sm:p-5">
        <div className="mx-auto flex max-w-7xl flex-col gap-10 rounded-3xl bg-blue-950 p-8 text-blue-200/80 sm:p-12">
          <div className="flex flex-col justify-between gap-8 sm:flex-row">
            <div className="flex flex-col gap-3">
              <span className="font-mono text-xs tracking-[0.2em] uppercase">
                Ready to try it?
              </span>
              <p className="max-w-sm text-sm">
                Start with your first sentence: &quot;line 2 motor&apos;s
                vibration has been rough since this morning&quot;
              </p>
              <Link
                href="/mesin"
                className={cn(
                  buttonVariants({ variant: "secondary" }),
                  "w-fit gap-2 rounded-full",
                )}
              >
                Open WO.M.AI <ArrowRight className="size-4" />
              </Link>
            </div>
            <div className="flex gap-14 text-sm">
              <div className="flex flex-col gap-2">
                <span className="font-mono text-xs tracking-wide text-blue-300/60 uppercase">
                  App
                </span>
                <Link href="/mesin" className="hover:text-white">
                  Chat
                </Link>
                <Link href="/riwayat" className="hover:text-white">
                  History
                </Link>
              </div>
              <div className="flex flex-col gap-2">
                <span className="font-mono text-xs tracking-wide text-blue-300/60 uppercase">
                  Competition
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
            licensed CC-BY-NC-SA-4.0.
          </p>
        </div>
        <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-2 px-4 pt-5 pb-2 text-xs text-slate-500 sm:flex-row">
          <span>© 2026 WO.M.AI. All rights reserved.</span>
          <div className="flex items-center gap-5">
            <Link href="/mesin" className="hover:text-slate-900">
              Chat
            </Link>
            <Link href="/riwayat" className="hover:text-slate-900">
              History
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
