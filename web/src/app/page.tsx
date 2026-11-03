import Link from "next/link";

import { buttonVariants } from "@/components/ui/button";

// A plain entry point. The full landing page comes with #24.
export default function Home() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-2xl flex-col justify-center gap-6 px-4 py-16">
      <h1 className="text-4xl font-semibold tracking-tight text-balance">Meridian Intelligence</h1>
      <p className="text-muted-foreground text-lg">
        Reads shipping documents, keeps personal data away from the model, and checks that the invoice quantity
        matches the packing list.
      </p>
      <div>
        <Link href="/workspace" className={buttonVariants()}>
          Go to your workspace
        </Link>
      </div>
    </main>
  );
}
