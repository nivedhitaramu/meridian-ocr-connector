"use server";

import { ApiError, assignIntake, discardIntake, uploadBatch } from "@/lib/api";
import { apiContext } from "@/lib/server-api";

export type IntakeState = { error: string | null; reload?: boolean };

const text = (form: FormData, field: string) => String(form.get(field) ?? "").trim();

// The page loads again, so it shows what the server saved.
const done = (): IntakeState => ({ error: null, reload: true });

export async function uploadBatchAction(_: IntakeState, form: FormData): Promise<IntakeState> {
  const files = form.getAll("files").filter((file): file is File => file instanceof File && file.size > 0);
  if (files.length === 0) return { error: "Choose at least one PDF, PNG or JPEG file." };
  try {
    await uploadBatch(await apiContext(text(form, "organization")), files);
  } catch (error) {
    if (error instanceof ApiError && (error.status === 413 || error.status === 415)) {
      return { error: "Use up to 20 PDF, PNG or JPEG files, each under 10 MB." };
    }
    return { error: "We can't read these documents right now. Try again soon." };
  }
  return done();
}

export async function assignAction(_: IntakeState, form: FormData): Promise<IntakeState> {
  const reference = text(form, "reference");
  if (!reference) return { error: "Enter the shipment reference." };
  try {
    await assignIntake(await apiContext(text(form, "organization")), text(form, "id"), reference);
  } catch (error) {
    if (error instanceof ApiError && error.status === 410) return { error: "This file was removed after waiting too long. Upload it again." };
    if (error instanceof ApiError && error.status === 409) return { error: "This document has already been handled." };
    return { error: "We couldn't save this. Try again." };
  }
  return done();
}

export async function discardAction(_: IntakeState, form: FormData): Promise<IntakeState> {
  try {
    await discardIntake(await apiContext(text(form, "organization")), text(form, "id"));
  } catch {
    return { error: "We couldn't discard this. Try again." };
  }
  return done();
}
