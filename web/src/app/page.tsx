import { ArrowRight, Check, EyeOff, FileSearch, Scale, ShieldCheck, X } from "lucide-react";
import Link from "next/link";

import { buttonVariants } from "@/components/ui/button";

const STEPS = [
  { title: "Read", text: "Documents are read on our own servers with local OCR. Nothing leaves at this stage." },
  { title: "Mask", text: "Names, phones, emails, IDs and signatures become placeholders before any model call." },
  { title: "Extract", text: "A model classifies the masked document and fills six shipping fields." },
  { title: "Check", text: "Plain code compares the quantities. The model never makes the decision." },
];

const STATUSES = [
  { name: "Match", text: "Both documents are present and the quantities are equal." },
  { name: "Mismatch", text: "The quantities differ, the units differ, or a total can't be read." },
  { name: "Incomplete", text: "The invoice or the packing list is missing." },
  { name: "Not applicable", text: "Only a delivery receipt was uploaded." },
];

const PRIVACY = [
  { icon: EyeOff, title: "Masked first", text: "Personal data is replaced before any network call." },
  { icon: ShieldCheck, title: "Fails closed", text: "If masking can't be confirmed, the document goes to manual review." },
  { icon: FileSearch, title: "Clean traces", text: "Logs hold counts and timings. Never document text or names." },
];

/** A fixed illustration of one result, drawn with synthetic values. */
function SampleResult() {
  return (
    <figure className="bg-card rounded-xl border p-5 shadow-sm">
      <figcaption className="text-muted-foreground mb-4 text-xs">Example result, using synthetic documents</figcaption>
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div className="rounded-lg border p-3">
          <p className="text-muted-foreground text-xs">Commercial invoice</p>
          <p className="mt-1 text-2xl font-semibold tabular-nums">120</p>
          <p className="text-muted-foreground text-xs">cartons</p>
        </div>
        <div className="rounded-lg border p-3">
          <p className="text-muted-foreground text-xs">Packing list</p>
          <p className="mt-1 text-2xl font-semibold tabular-nums">118</p>
          <p className="text-muted-foreground text-xs">cartons</p>
        </div>
      </div>
      <div className="border-destructive/40 text-destructive mt-3 flex items-center gap-2 rounded-lg border p-3 text-sm font-medium">
        <X aria-hidden className="size-4 shrink-0" />
        Mismatch: 120 differs from 118 cartons
      </div>
      <p className="text-muted-foreground mt-4 flex items-center gap-2 text-xs">
        <Check aria-hidden className="size-3.5 shrink-0" />
        Contact name, phone and email masked before the model call
      </p>
    </figure>
  );
}

export default function Home() {
  return (
    <div className="min-h-dvh">
      <header className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-5 md:px-8">
        <Link href="/" className="font-semibold tracking-tight">
          Meridian Intelligence
        </Link>
        <nav aria-label="Account" className="flex items-center gap-2">
          <Link href="/sign-in" className={buttonVariants({ variant: "ghost" })}>
            Sign in
          </Link>
          <Link href="/sign-up" className={buttonVariants()}>
            Create account
          </Link>
        </nav>
      </header>

      <main className="mx-auto max-w-6xl space-y-20 px-4 pt-10 pb-20 md:px-8 md:pt-16">
        <section className="grid items-center gap-10 md:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
          <div className="space-y-6">
            <h1 className="text-4xl font-semibold tracking-tight text-balance md:text-5xl">
              Catch the wrong quantity before the cartons are put away
            </h1>
            <p className="text-muted-foreground max-w-prose text-lg">
              Upload a commercial invoice and a packing list. Meridian Intelligence reads both, keeps personal data away
              from the model, and tells the receiving clerk whether the quantities match.
            </p>
            <Link href="/sign-up" className={buttonVariants({ size: "lg" })}>
              Create your organization
              <ArrowRight aria-hidden className="size-4" />
            </Link>
          </div>
          <SampleResult />
        </section>

        <section aria-labelledby="how" className="space-y-6">
          <h2 id="how" className="text-2xl font-semibold tracking-tight">
            How a check runs
          </h2>
          <ol className="grid gap-px overflow-hidden rounded-xl border bg-border sm:grid-cols-2 lg:grid-cols-4">
            {STEPS.map((step, index) => (
              <li key={step.title} className="bg-background space-y-2 p-5">
                <p className="text-muted-foreground font-mono text-xs">Step {index + 1}</p>
                <h3 className="font-semibold">{step.title}</h3>
                <p className="text-muted-foreground text-sm">{step.text}</p>
              </li>
            ))}
          </ol>
        </section>

        <section aria-labelledby="answers" className="grid gap-8 md:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
          <div className="space-y-3">
            <Scale aria-hidden className="text-primary size-6" />
            <h2 id="answers" className="text-2xl font-semibold tracking-tight">
              Four clear answers
            </h2>
            <p className="text-muted-foreground text-sm">Weight is shown to the clerk, but never changes the answer.</p>
          </div>
          <dl className="divide-y rounded-xl border">
            {STATUSES.map((status) => (
              <div key={status.name} className="grid gap-1 p-4 sm:grid-cols-[9rem_minmax(0,1fr)] sm:gap-4">
                <dt className="font-medium">{status.name}</dt>
                <dd className="text-muted-foreground text-sm">{status.text}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section aria-labelledby="privacy" className="space-y-6">
          <h2 id="privacy" className="text-2xl font-semibold tracking-tight">
            Built around privacy
          </h2>
          <ul className="grid gap-6 md:grid-cols-3">
            {PRIVACY.map(({ icon: Icon, title, text }) => (
              <li key={title} className="space-y-2">
                <Icon aria-hidden className="text-primary size-5" />
                <h3 className="font-semibold">{title}</h3>
                <p className="text-muted-foreground text-sm">{text}</p>
              </li>
            ))}
          </ul>
        </section>
      </main>

      <footer className="text-muted-foreground mx-auto max-w-6xl border-t px-4 py-6 text-xs md:px-8">
        A Team Delta project. Meridian Freight is a fictional company, and this demo uses synthetic documents only.
      </footer>
    </div>
  );
}
