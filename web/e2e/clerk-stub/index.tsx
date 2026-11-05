"use client";

/* Browser tests only: stands in for @clerk/nextjs. See next.config.ts. */
import type { ReactNode } from "react";

export function ClerkProvider({ children }: { children: ReactNode }) {
  return <>{children}</>;
}

export function UserButton() {
  return <span aria-label="Test account">Test account</span>;
}

function Stub({ title }: { title: string }) {
  return <p>{title} (browser test stand-in)</p>;
}

export function SignIn() {
  return <Stub title="Sign in" />;
}

export function SignUp() {
  return <Stub title="Sign up" />;
}
