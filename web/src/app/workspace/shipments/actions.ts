"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { addReview, ApiError, createShipment, startJob, submitForApproval, uploadDocument } from "@/lib/api";
import { apiContext } from "@/lib/server-api";

export type FormState = { error: string | null };

const text = (form: FormData, field: string) => String(form.get(field) ?? "").trim();

export async function createShipmentAction(_: FormState, form: FormData): Promise<FormState> {
  const reference = text(form, "reference");
  const organization = text(form, "organization");
  if (!reference) return { error: "Enter a shipment reference." };
  let id: string;
  try {
    id = (await createShipment(await apiContext(organization), reference)).id;
  } catch (error) {
    if (error instanceof ApiError && error.status === 409) return { error: "A shipment with this reference already exists." };
    return { error: "We couldn't create the shipment. Try again." };
  }
  redirect(`/workspace/shipments/${id}?org=${organization}`);
}

export async function uploadAction(_: FormState, form: FormData): Promise<FormState> {
  const file = form.get("file");
  const shipment = text(form, "shipment");
  if (!(file instanceof File) || file.size === 0) return { error: "Choose a PDF, PNG or JPEG file." };
  try {
    await uploadDocument(await apiContext(text(form, "organization")), shipment, file);
  } catch (error) {
    if (error instanceof ApiError && (error.status === 413 || error.status === 415)) {
      return { error: "Use a PDF, PNG or JPEG file up to 10 MB." };
    }
    return { error: "We couldn't upload this file. Try again." };
  }
  revalidatePath(`/workspace/shipments/${shipment}`);
  return { error: null };
}

export async function startJobAction(_: FormState, form: FormData): Promise<FormState> {
  const shipment = text(form, "shipment");
  try {
    // One click, one job, even if the form is sent twice.
    await startJob(await apiContext(text(form, "organization")), shipment, text(form, "attempt"));
  } catch (error) {
    if (error instanceof ApiError && error.status === 409) return { error: "Upload a document first." };
    return { error: "We can't start this check right now. Try again soon." };
  }
  revalidatePath(`/workspace/shipments/${shipment}`);
  return { error: null };
}

export async function submitAction(_: FormState, form: FormData): Promise<FormState> {
  const reason = text(form, "reason");
  if (!reason) return { error: "Say why this needs approval." };
  try {
    await submitForApproval(await apiContext(text(form, "organization")), text(form, "job"), reason);
  } catch {
    return { error: "We couldn't send this for approval. Try again." };
  }
  revalidatePath("/workspace", "layout");
  return { error: null };
}

export async function reviewAction(_: FormState, form: FormData): Promise<FormState> {
  const reason = text(form, "reason");
  const action = text(form, "action");
  const quantity = text(form, "corrected_quantity");
  if (!reason) return { error: "Say why, so others can follow the decision." };
  if (action !== "resolve" && action !== "follow_up") return { error: "Choose what to do with this case." };
  if (quantity && !/^\d+$/.test(quantity)) return { error: "A corrected quantity must be a whole number." };
  try {
    await addReview(await apiContext(text(form, "organization")), text(form, "job"), {
      action,
      reason,
      corrected_quantity: quantity ? Number(quantity) : null,
    });
  } catch (error) {
    if (error instanceof ApiError && error.status === 403) return { error: "Your role can't approve this step." };
    if (error instanceof ApiError && error.status === 409) {
      return { error: "This can't be saved: the case is resolved, or someone else must approve this step." };
    }
    return { error: "We couldn't save this review. Try again." };
  }
  revalidatePath("/workspace", "layout");
  return { error: null };
}
