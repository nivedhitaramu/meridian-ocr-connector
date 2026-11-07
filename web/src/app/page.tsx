import { ArrowRight, ArrowUpRight, Check, EyeOff, FileText, Globe, Mail, PackageCheck, Scale, ScanLine, ShieldCheck, Truck, X } from "lucide-react";
import Link from "next/link";

import { ContainerArt, DocumentArt, LogoMark } from "@/components/landing/art";

const NAV = [
  { href: "#how", label: "How it works" },
  { href: "#documents", label: "Documents" },
  { href: "#privacy", label: "Privacy" },
  { href: "#results", label: "Results" },
];

const READS = ["Commercial invoice", "Packing list", "Delivery receipt", "Purchase order", "Goods received note", ".eml packet"];

const DOCUMENTS = [
  { title: "Commercial invoice", text: "Reference, shipper, receiver, date and the invoiced total.", tone: "orange" as const },
  { title: "Packing list", text: "The counted cartons, packages or pieces, with the unit printed beside them.", tone: "slate" as const },
  { title: "Delivery receipt", text: "Recognized and kept, with signatures painted out before anything is read.", tone: "stone" as const },
];

const PRIVACY = [
  { icon: EyeOff, text: "Names, phones, emails and IDs masked on our server" },
  { icon: Scale, text: "Plain rules decide the status, never the model" },
  { icon: ScanLine, text: "Every stage traced, with no personal data in the trace" },
];

const STEPS = [
  { title: "Read", text: "Local OCR reads each page. Nothing leaves yet." },
  { title: "Mask", text: "Personal data becomes placeholders like <PERSON_1>." },
  { title: "Extract", text: "The model fills six shipping fields from masked text." },
  { title: "Check", text: "Code compares the quantities and gives the answer." },
];

const STATUSES = [
  { name: "Match", text: "Both present, quantities equal", icon: Check, tone: "bg-emerald-100 text-emerald-900" },
  { name: "Mismatch", text: "Quantities or units differ", icon: X, tone: "bg-red-100 text-red-900" },
  { name: "Incomplete", text: "Invoice or packing list missing", icon: FileText, tone: "bg-amber-100 text-amber-900" },
  { name: "Not applicable", text: "Only a delivery receipt", icon: Truck, tone: "bg-neutral-200 text-neutral-900" },
];

const RESULTS = [
  { value: "97.9%", label: "of fields correct" },
  { value: "16/16", label: "document types" },
  { value: "10/10", label: "status decisions" },
];

const pillShape = "items-center justify-center gap-2 rounded-full px-5 py-2.5 text-sm font-semibold whitespace-nowrap transition-colors";
const pill = `inline-flex ${pillShape}`;
const primary = `${pill} bg-orange-700 text-white hover:bg-orange-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-orange-700`;

function SectionTitle({ id, children }: { id: string; children: React.ReactNode }) {
  return (
    <h2 id={id} className="font-display text-center text-3xl font-semibold tracking-tight text-balance md:text-4xl">
      {children}
    </h2>
  );
}

export default function Home() {
  return (
    <div className="min-h-dvh overflow-x-clip bg-white text-neutral-950">
      <header className="mx-auto max-w-6xl px-4 md:px-8">
        <div className="flex items-center justify-between gap-4 border-b border-neutral-300 py-5">
          <Link href="/" className="font-display flex items-center gap-2 text-xl font-extrabold tracking-tight">
            <LogoMark />
            <span>
              MERIDIAN<span className="text-orange-600">.</span>
            </span>
          </Link>
          <nav aria-label="Main" className="hidden items-center gap-7 text-sm font-medium md:flex">
            {NAV.map((item) => (
              <a key={item.href} href={item.href} className="hover:text-orange-700">
                {item.label}
              </a>
            ))}
          </nav>
          <div className="flex items-center gap-2">
            <Link href="/sign-in" className={`${pillShape} hidden text-neutral-900 hover:bg-neutral-100 sm:inline-flex`}>
              Sign in
            </Link>
            <Link href="/sign-up" className={primary}>
              Get started
            </Link>
          </div>
        </div>
      </header>

      <main>
        {/* Hero */}
        <section className="mx-auto max-w-6xl px-4 pt-14 text-center md:px-8 md:pt-20">
          <h1 className="font-display text-4xl font-semibold tracking-tight text-balance sm:text-5xl md:text-7xl">
            Checking Your Cargo
            <span className="mt-2 flex items-center justify-center gap-3 text-orange-600">
              <span className="grid size-10 place-items-center rounded-full bg-orange-100 md:size-14">
                <Globe aria-hidden className="size-5 text-orange-600 md:size-7" />
              </span>
              Before Put-Away
            </span>
          </h1>
          <p className="mx-auto mt-6 max-w-xl text-base text-neutral-600 md:text-lg">
            Upload a commercial invoice and a packing list. Meridian reads both, keeps personal data away from the AI, and tells
            the receiving clerk whether the quantities match.
          </p>
          <div className="mx-auto mt-8 flex max-w-xl flex-wrap items-center justify-center gap-3">
            <span className="flex items-center gap-2 rounded-xl border border-neutral-300 px-4 py-2.5 text-sm text-neutral-700">
              <FileText aria-hidden className="size-4 text-orange-600" />
              Commercial invoice
            </span>
            <span className="flex items-center gap-2 rounded-xl border border-neutral-300 px-4 py-2.5 text-sm text-neutral-700">
              <PackageCheck aria-hidden className="size-4 text-orange-600" />
              Packing list
            </span>
            <Link
              href="/sign-up"
              aria-label="Start a check"
              className="grid size-11 place-items-center rounded-xl bg-neutral-950 text-white hover:bg-neutral-800"
            >
              <ArrowRight aria-hidden className="size-5" />
            </Link>
          </div>

          <div className="relative mx-auto mt-6 max-w-3xl">
            <svg viewBox="0 0 640 160" className="pointer-events-none absolute inset-x-0 top-6 hidden md:block" aria-hidden>
              <path d="M20 120 C 120 120, 150 40, 260 30" fill="none" stroke="#f97316" strokeWidth="2" />
              <circle cx="20" cy="120" r="7" fill="#fff" stroke="#f97316" strokeWidth="2" />
              <path d="M400 60 C 470 30, 560 20, 625 60" fill="none" stroke="#d4d4d4" strokeWidth="2" />
              <circle cx="625" cy="60" r="7" fill="#fff" stroke="#f97316" strokeWidth="2" />
            </svg>
            <span className="absolute top-[38%] left-[6%] z-10 grid size-16 place-items-center rounded-full bg-orange-500 text-center text-xs leading-tight font-bold text-neutral-950 shadow-lg md:size-20 md:text-sm">
              6<br />fields
            </span>
            <span className="absolute top-8 right-[4%] z-10 hidden rounded-full border border-neutral-200 bg-white px-3 py-1.5 text-xs font-medium shadow-sm sm:block">
              <ShieldCheck aria-hidden className="mr-1 inline size-3.5 text-orange-600" />
              Masked before the AI
            </span>
            <ContainerArt className="relative z-0 mx-auto w-full max-w-2xl" />
          </div>
        </section>

        {/* Dark band */}
        <section aria-labelledby="one-check" className="mx-auto -mt-16 max-w-6xl px-4 md:-mt-24 md:px-8">
          <div className="rounded-[2rem] bg-neutral-950 px-6 pt-24 pb-10 text-white md:px-12 md:pt-32 md:pb-14">
            <p className="text-center text-xs font-semibold tracking-widest text-neutral-400 uppercase">Reads</p>
            <ul className="font-display mt-4 flex flex-wrap items-center justify-center gap-x-8 gap-y-3 text-base font-bold tracking-tight text-neutral-200 md:text-lg">
              {READS.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>

            <div className="mt-14 grid items-center gap-10 md:grid-cols-2">
              <figure className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-neutral-800 to-neutral-900 p-6">
                <figcaption className="text-xs text-neutral-400">Example result, with synthetic documents</figcaption>
                <div className="mt-4 grid grid-cols-2 gap-3">
                  <div className="rounded-2xl bg-neutral-950/70 p-4">
                    <p className="text-xs text-neutral-400">Commercial invoice</p>
                    <p className="font-display mt-1 text-4xl font-bold tabular-nums">120</p>
                    <p className="text-xs text-neutral-400">cartons</p>
                  </div>
                  <div className="rounded-2xl bg-neutral-950/70 p-4">
                    <p className="text-xs text-neutral-400">Packing list</p>
                    <p className="font-display mt-1 text-4xl font-bold tabular-nums">118</p>
                    <p className="text-xs text-neutral-400">cartons</p>
                  </div>
                </div>
                <p className="mt-3 flex items-center gap-2 rounded-2xl bg-orange-500 px-4 py-3 text-sm font-semibold text-neutral-950">
                  <X aria-hidden className="size-4 shrink-0" />
                  Mismatch: 120 differs from 118 cartons
                </p>
                <p className="mt-3 flex items-center gap-2 text-xs text-neutral-400">
                  <EyeOff aria-hidden className="size-3.5 shrink-0" />
                  4 names, 2 phones and 2 emails masked before the model call
                </p>
              </figure>

              <div>
                <h2 id="one-check" className="font-display text-3xl leading-tight font-semibold tracking-tight md:text-5xl">
                  <span className="text-orange-400">One</span> Check for Every Delivery
                </h2>
                <p className="mt-5 max-w-md text-sm text-neutral-300 md:text-base">
                  The invoice says what was billed. The packing list says what was packed. Meridian compares their totals, in
                  the same unit, so the wrong quantity is caught at the dock instead of at month end.
                </p>
                <div className="mt-8 flex flex-wrap gap-3">
                  <Link href="/sign-up" className={primary}>
                    Start a check
                  </Link>
                  <a href="#how" className={`${pill} border border-neutral-600 text-white hover:bg-neutral-800`}>
                    How it works
                  </a>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Documents */}
        <section id="documents" aria-labelledby="documents-title" className="mx-auto max-w-6xl scroll-mt-6 px-4 pt-24 md:px-8">
          <SectionTitle id="documents-title">
            Shipping Documents
            <br />
            It Understands
          </SectionTitle>
          <ul className="mt-10 grid gap-4 md:grid-cols-3">
            {DOCUMENTS.map((doc) => (
              <li
                key={doc.title}
                className={`relative flex min-h-80 flex-col overflow-hidden rounded-3xl p-5 text-white ${
                  doc.tone === "orange"
                    ? "bg-gradient-to-br from-orange-700 to-orange-900"
                    : doc.tone === "slate"
                      ? "bg-gradient-to-br from-slate-700 to-slate-900"
                      : "bg-gradient-to-br from-stone-600 to-stone-800"
                }`}
              >
                <div className="flex-1">
                  <DocumentArt tone={doc.tone} />
                </div>
                <div className="flex items-end justify-between gap-3">
                  <div>
                    <h3 className="font-display text-lg font-semibold">{doc.title}</h3>
                    <p className="mt-1 text-sm text-white/90">{doc.text}</p>
                  </div>
                  <span className="grid size-9 shrink-0 place-items-center rounded-full border border-white/60">
                    <ArrowUpRight aria-hidden className="size-4" />
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </section>

        {/* Privacy */}
        <section id="privacy" aria-labelledby="privacy-title" className="mx-auto max-w-6xl scroll-mt-6 px-4 pt-24 md:px-8">
          <div className="grid items-center gap-10 md:grid-cols-[minmax(0,1fr)_minmax(0,0.8fr)]">
            <div>
              <h2 id="privacy-title" className="font-display text-3xl font-semibold tracking-tight md:text-4xl">
                Privacy Built Into
                <br />
                Every Step
              </h2>
              <p className="mt-4 max-w-md text-sm text-neutral-600">
                Shipping documents carry names, phone numbers and signatures. Meridian removes them on its own server before the
                AI sees a single word, and stops if it can&apos;t be sure.
              </p>
              <ul className="mt-6 max-w-md divide-y divide-neutral-200 border-y border-neutral-200">
                {PRIVACY.map(({ icon: Icon, text }) => (
                  <li key={text} className="flex items-center gap-3 py-3.5 text-sm font-medium">
                    <span className="grid size-8 place-items-center rounded-lg bg-orange-100">
                      <Icon aria-hidden className="size-4 text-orange-700" />
                    </span>
                    {text}
                  </li>
                ))}
              </ul>
            </div>
            <figure className="rounded-3xl bg-gradient-to-b from-orange-500 to-orange-700 p-6 text-neutral-950">
              <figcaption className="text-xs font-semibold tracking-widest uppercase">Trace of one check</figcaption>
              <dl className="mt-5 space-y-2.5">
                {[
                  ["OCR", "11.1 s"],
                  ["Masking", "0.1 s"],
                  ["AI extraction", "3.8 s"],
                  ["Rules", "0.0 s"],
                ].map(([stage, time]) => (
                  <div key={stage} className="flex items-center justify-between rounded-xl bg-white/90 px-4 py-2.5 text-sm">
                    <dt className="font-medium">{stage}</dt>
                    <dd className="font-display font-bold tabular-nums">{time}</dd>
                  </div>
                ))}
              </dl>
              <p className="mt-4 rounded-xl bg-neutral-950 px-4 py-3 font-mono text-xs text-orange-300">
                masked_before_llm = true · PERSON 4 · PHONE 2 · EMAIL 2
              </p>
            </figure>
          </div>
        </section>

        {/* How it works */}
        <section id="how" aria-labelledby="how-title" className="mx-auto max-w-6xl scroll-mt-6 px-4 pt-24 md:px-8">
          <SectionTitle id="how-title">
            Four Steps.
            <br />
            Four Clear Answers.
          </SectionTitle>
          <ol className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {STEPS.map((step, index) => (
              <li key={step.title} className="rounded-3xl border border-neutral-200 p-5">
                <span className="font-display grid size-9 place-items-center rounded-full bg-neutral-950 text-sm font-bold text-white">
                  {index + 1}
                </span>
                <h3 className="font-display mt-4 text-lg font-semibold">{step.title}</h3>
                <p className="mt-1 text-sm text-neutral-600">{step.text}</p>
              </li>
            ))}
          </ol>
          <ul className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4" aria-label="The four statuses">
            {STATUSES.map(({ name, text, icon: Icon, tone }) => (
              <li key={name} className="flex items-center gap-3 rounded-2xl bg-neutral-100 p-3">
                <span className={`grid size-10 shrink-0 place-items-center rounded-xl ${tone}`}>
                  <Icon aria-hidden className="size-5" />
                </span>
                <span>
                  <span className="block text-sm font-semibold">{name}</span>
                  <span className="block text-xs text-neutral-600">{text}</span>
                </span>
              </li>
            ))}
          </ul>
        </section>

        {/* Results */}
        <section id="results" aria-labelledby="results-title" className="mx-auto max-w-6xl scroll-mt-6 px-4 pt-24 pb-20 md:px-8">
          <div className="relative overflow-hidden rounded-[2rem] bg-neutral-900 p-6 text-white md:p-10">
            <svg viewBox="0 0 400 200" className="absolute -right-10 -bottom-10 w-[30rem] opacity-30" aria-hidden>
              {Array.from({ length: 6 }, (_, row) =>
                Array.from({ length: 10 }, (_, col) => (
                  <rect key={`${row}-${col}`} x={col * 42} y={row * 34} width="36" height="28" rx="3" fill={(row + col) % 4 === 0 ? "#f97316" : "#525252"} />
                )),
              )}
            </svg>
            <div className="relative grid items-center gap-8 md:grid-cols-2">
              <div>
                <h2 id="results-title" className="font-display text-3xl font-semibold tracking-tight md:text-4xl">
                  Measured, Not Promised
                </h2>
                <p className="mt-4 max-w-sm text-sm text-neutral-300">
                  Scored with the real model on 16 synthetic documents made after the prompt was frozen. Our own team wrote
                  them, so treat this as a sanity check, not an independent benchmark.
                </p>
              </div>
              <div className="rounded-3xl bg-white p-5 text-neutral-950">
                <p className="font-display text-sm font-semibold">Final test set</p>
                <dl className="mt-4 grid grid-cols-3 gap-3">
                  {RESULTS.map((result) => (
                    <div key={result.label} className="rounded-2xl bg-neutral-100 p-3">
                      <dt className="text-xs text-neutral-600">{result.label}</dt>
                      <dd className="font-display mt-1 text-2xl font-bold text-orange-700 tabular-nums">{result.value}</dd>
                    </div>
                  ))}
                </dl>
                <Link href="/sign-up" className={`${primary} mt-5 w-full`}>
                  Try it with your team
                </Link>
                <p className="mt-3 flex items-center justify-center gap-1.5 text-xs text-neutral-600">
                  <Mail aria-hidden className="size-3.5" />
                  Packets can arrive as .eml email files too
                </p>
              </div>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-neutral-200">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-6 text-xs text-neutral-600 md:px-8">
          <span className="font-display flex items-center gap-2 font-bold text-neutral-950">
            <LogoMark className="size-5" />
            MERIDIAN INTELLIGENCE
          </span>
          <span>A Team Delta project. Meridian Freight is fictional, and this demo uses synthetic documents only.</span>
        </div>
      </footer>
    </div>
  );
}
