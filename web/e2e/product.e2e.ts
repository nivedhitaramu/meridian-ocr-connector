import { expect, type Page, test } from "@playwright/test";

import { checkShipment, expectAccessible, expectNoSidewaysScroll, sample, signedIn } from "./helpers";

// One organization and its people carry through the file, in order, as they would in real use.
test.describe.configure({ mode: "serial" });

const SCREENS = ["/workspace", "/workspace/dashboard", "/workspace/intake", "/workspace/shipments", "/workspace/exceptions", "/workspace/observability", "/workspace/settings", "/workspace/api-access"];

let alice: Page;
let bob: Page;
let cara: Page;
let mismatchUrl = "";

test("the landing page leads to sign-in, and the workspace refuses anonymous visitors", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expectAccessible(page);
  await page.goto("/workspace");
  await expect(page).toHaveURL(/\/sign-in/);
});

test("an admin creates an organization and adds their team", async ({ browser }) => {
  alice = await signedIn(browser, "alice");
  bob = await signedIn(browser, "bob");
  cara = await signedIn(browser, "cara");
  await alice.goto("/workspace");
  await alice.getByLabel("Organization name").fill("Meridian Freight");
  await alice.getByRole("button", { name: "Create organization" }).click();
  await expect(alice.getByRole("heading", { name: "Meridian Freight" })).toBeVisible();

  const invite = async (email: string, role: string) => {
    await alice.goto("/workspace/settings");
    await alice.getByLabel("Email").fill(email);
    await alice.getByLabel("Role", { exact: true }).selectOption(role);
    await alice.getByRole("button", { name: "Invite", exact: true }).click();
    await expect(alice.getByRole("cell", { name: email, exact: true })).toBeVisible();
  };

  // A cancelled invitation disappears, and someone invited has no access until they accept.
  await invite("cara@example.com", "clerk");
  await alice.getByRole("button", { name: "Cancel invitation for cara@example.com" }).click();
  await expect(alice.getByRole("cell", { name: "cara@example.com", exact: true })).toHaveCount(0);
  await cara.goto("/workspace");
  await expect(cara.getByLabel("Organization name")).toBeVisible();
  await expect(cara.getByRole("button", { name: /Accept invitation/ })).toHaveCount(0);

  for (const [person, email, role] of [[bob, "bob@example.com", "clerk"], [cara, "cara@example.com", "supervisor"]] as const) {
    await invite(email, role);
    await person.goto("/workspace");
    await expect(person.getByText("sent by alice@example.com")).toBeVisible();
    await expect(person.getByRole("heading", { name: "Meridian Freight" })).toHaveCount(0);
    await expectAccessible(person);
    await person.getByRole("button", { name: "Accept invitation to Meridian Freight" }).click();
    await expect(person.getByRole("heading", { name: "Meridian Freight" })).toBeVisible();
    await expect(person.getByRole("button", { name: /Accept invitation/ })).toHaveCount(0);
  }
});

test("a clerk gets all four statuses, with the reason and both documents side by side", async () => {
  await checkShipment(bob, "E2E-MATCH", ["S02_invoice.pdf", "S02_packing.pdf"]);
  await expect(bob.getByText("Match", { exact: true })).toBeVisible();
  await expect(bob.getByText(/equals packing-list quantity/)).toBeVisible();
  await expect(bob.getByRole("columnheader", { name: "Commercial invoice" })).toBeVisible();
  await expect(bob.getByRole("columnheader", { name: "Packing list" })).toBeVisible();
  await expect(bob.getByRole("cell", { name: "Total quantity" })).toBeVisible();
  await expect(bob.getByRole("cell", { name: "MF-88421" }).first()).toBeVisible();

  await checkShipment(bob, "E2E-MISMATCH", ["S04_invoice.pdf", "S04_packing.pdf"]);
  await expect(bob.getByText("Mismatch", { exact: true })).toBeVisible();
  await expect(bob.getByText(/differs from packing-list quantity/)).toBeVisible();
  mismatchUrl = bob.url();

  await checkShipment(bob, "E2E-ALONE", ["S03_invoice.pdf"]);
  await expect(bob.getByText("Incomplete", { exact: true })).toBeVisible();

  await checkShipment(bob, "E2E-RECEIPT", ["S02_receipt.pdf"]);
  await expect(bob.getByText("Not applicable", { exact: true })).toBeVisible();
});

test("adding a document after a check starts a new check without refreshing", async () => {
  await bob.goto("/workspace/shipments");
  await bob.getByRole("link", { name: "E2E-ALONE" }).click();
  await bob.waitForLoadState("networkidle"); // links into a shipment are full page loads
  await bob.getByLabel("Document").setInputFiles(sample("S03_packing.pdf"));
  await bob.getByRole("button", { name: "Upload" }).click();
  await expect(bob.getByText("1 document is ready to check.")).toBeVisible();
  await bob.getByRole("button", { name: "Check quantities" }).click();
  await expect(bob.getByText("No documents are waiting.")).toBeVisible({ timeout: 120_000 });
});

test("shipments can be searched and filtered", async () => {
  await bob.goto("/workspace/shipments");
  await bob.getByLabel("Search references").fill("mismatch");
  await bob.getByRole("button", { name: "Apply" }).click();
  await expect(bob.getByRole("link", { name: "E2E-MISMATCH" })).toBeVisible();
  await expect(bob.getByRole("link", { name: "E2E-MATCH" })).toHaveCount(0);
  await bob.getByLabel("Search references").fill("nothing-like-this");
  await bob.getByRole("button", { name: "Apply" }).click();
  await expect(bob.getByText("No shipments match this search")).toBeVisible();
  await bob.getByRole("link", { name: "Clear" }).click();
  await expect(bob.getByRole("link", { name: "E2E-MATCH" })).toBeVisible();
});

test("a mismatch moves from clerk to supervisor to resolved, with each step audited", async () => {
  await bob.goto("/workspace/exceptions");
  await expect(bob.getByRole("link", { name: "E2E-MISMATCH" })).toBeVisible();
  await expect(bob.getByRole("button", { name: "Resolve" })).toHaveCount(0);
  await bob.getByLabel("Why does this need approval?").first().fill("Counted 118 on the dock.");
  await bob.getByRole("button", { name: "Send for approval" }).first().click();
  await expect(bob.getByText("Sent for approval. Someone else needs to act next.").first()).toBeVisible();

  await cara.goto("/workspace/dashboard");
  await expect(cara.getByText("Waiting for your approval")).toBeVisible();
  await cara.goto("/workspace/exceptions");
  await expect(cara.getByText(/waiting for your approval\./)).toBeVisible();
  await expect(cara.getByText("Counted 118 on the dock.")).toBeVisible();
  const card = cara.locator('[data-slot="card"]').filter({ hasText: "E2E-MISMATCH" });
  await card.getByLabel("Reason").fill("Recount confirmed 118.");
  await card.getByLabel("Corrected quantity (optional)").fill("118");
  await card.getByRole("button", { name: "Resolve" }).click();
  await expect(cara.getByRole("link", { name: "E2E-MISMATCH" })).toHaveCount(0);

  await alice.goto("/workspace/settings");
  await expect(alice.getByText("Sent for approval").first()).toBeVisible();
  await expect(alice.getByText("Review recorded").first()).toBeVisible();
});

test("the dashboard's numbers and history come from saved jobs", async () => {
  await cara.goto("/workspace/dashboard");
  await expect(cara.getByText("Open exceptions")).toBeVisible();
  await expect(cara.getByRole("heading", { name: "Processing history" }).or(cara.getByText("Processing history"))).toBeVisible();
  await expect(cara.getByText(/A person corrected 1 of \d+ checks/)).toBeVisible();
  await expect(cara.getByRole("cell", { name: "Kestrel Exports" })).toBeVisible();
  await cara.getByLabel("Search references").fill("E2E-RECEIPT");
  await cara.getByRole("button", { name: "Apply" }).click();
  await expect(cara.getByRole("link", { name: "E2E-RECEIPT" })).toBeVisible();
  await expect(cara.getByRole("link", { name: "E2E-MATCH" })).toHaveCount(0);
});

test("observability shows real timings to supervisors, and nothing to clerks", async () => {
  await cara.goto("/workspace/observability");
  await expect(cara.getByText("Latest trace")).toBeVisible();
  await expect(cara.getByText("Vision fallback")).toBeVisible();
  await expect(cara.getByText("Total time")).toBeVisible();
  const text = await cara.locator("main").innerText();
  expect(text).not.toContain("Kestrel");
  expect(text).not.toContain("E2E-MATCH");
  await bob.goto("/workspace/observability");
  await expect(bob.getByText("Only supervisors and admins can see this")).toBeVisible();
});

test("admins manage settings, and others can't reach those actions", async () => {
  await alice.goto("/workspace/settings");
  await alice.getByLabel("Organization name").fill("Meridian Freight India");
  await alice.getByRole("button", { name: "Save name" }).click();
  await expect(alice.getByText("Saved.").first()).toBeVisible();
  await alice.getByLabel("Keep shipment records for (days)").fill("3");
  await alice.getByRole("button", { name: "Save retention" }).click();
  await expect(alice.getByText(/whole number from 7 to 3650/)).toBeVisible();
  await alice.getByLabel("Who approves an exception?").selectOption("supervisor");
  await alice.getByRole("button", { name: "Save approval steps" }).click();

  await bob.goto("/workspace/settings");
  await expect(bob.getByRole("button", { name: "Save name" })).toHaveCount(0);
  await expect(bob.getByRole("button", { name: "Save retention" })).toHaveCount(0);
  await expect(bob.getByRole("button", { name: /remove/i })).toHaveCount(0);
});

test("an admin creates and revokes an API key, shown once, and clerks can't", async () => {
  await alice.goto("/workspace/api-access");
  await alice.getByLabel("Key name").fill("Warehouse system");
  await alice.getByRole("button", { name: "Create key" }).click();
  const shown = alice.getByRole("status").getByText(/^mk_/);
  await expect(shown).toBeVisible();
  const key = await shown.innerText();
  await alice.reload();
  await expect(alice.getByText(key)).toHaveCount(0);
  await expect(alice.getByRole("cell", { name: "Warehouse system", exact: true })).toBeVisible();
  await alice.getByLabel("HTTPS address").fill("http://127.0.0.1/hook");
  await alice.getByRole("button", { name: "Add webhook" }).click();
  await expect(alice.getByText("Use a public HTTPS address.")).toBeVisible();
  await alice.getByRole("button", { name: "Revoke Warehouse system" }).click();
  await expect(alice.getByText("No active keys.")).toBeVisible();
  await bob.goto("/workspace/api-access");
  await expect(bob.getByText("Only admins can manage API access")).toBeVisible();
});

test("intake groups a clear pair, and sends a lone document to a person", async () => {
  await bob.goto("/workspace/intake");
  await bob.getByLabel("Documents").setInputFiles([sample("S06_invoice.pdf"), sample("S06_packing.pdf")]);
  await bob.getByRole("button", { name: "Upload and group" }).click();
  await expect(bob.getByText("Grouped automatically").first()).toBeVisible({ timeout: 120_000 });
  await expect(bob.getByText("Grouped automatically")).toHaveCount(2);

  await bob.getByLabel("Documents").setInputFiles(sample("S07_invoice.pdf"));
  await bob.getByRole("button", { name: "Upload and group" }).click();
  await expect(bob.getByText("No other document or shipment confirms this reference.")).toBeVisible({ timeout: 120_000 });
  await bob.getByLabel("Shipment reference").fill("E2E-ASSIGNED");
  await bob.getByRole("button", { name: "Assign" }).click();
  await expect(bob.getByText("Assigned by a person")).toBeVisible();
  await bob.goto("/workspace/shipments");
  await expect(bob.getByRole("link", { name: "E2E-ASSIGNED" })).toBeVisible();
});

test("pages can't be framed by another site", async () => {
  const headers = (await alice.request.get("/workspace")).headers();
  expect(headers["x-frame-options"]).toBe("DENY");
  expect(headers["x-content-type-options"]).toBe("nosniff");
  expect(headers["x-powered-by"]).toBeUndefined();
});

test("every main screen passes automated accessibility checks", async () => {
  for (const screen of SCREENS) {
    await alice.goto(screen);
    await expect(alice.locator("main h1").first()).toBeVisible();
    await expectAccessible(alice);
  }
  await alice.goto(mismatchUrl);
  await expectAccessible(alice);
});

test("every main screen fits a phone without sideways scrolling", async ({ browser }) => {
  const phone = await signedIn(browser, "alice", { width: 360, height: 780 });
  for (const screen of [...SCREENS, mismatchUrl]) {
    await phone.goto(screen);
    await expect(phone.locator("main h1").first()).toBeVisible();
    await expectNoSidewaysScroll(phone);
  }
  await phone.context().close();
});

test("the main flow works with the keyboard alone", async () => {
  await alice.goto("/workspace");
  await alice.getByRole("link", { name: "Shipments" }).focus();
  await alice.keyboard.press("Enter");
  await expect(alice).toHaveURL(/\/workspace\/shipments/);
  await expect(alice.getByRole("heading", { name: "Shipments", exact: true })).toBeVisible();
  await alice.getByLabel("Reference", { exact: true }).focus();
  await alice.keyboard.type("E2E-KEYBOARD");
  await alice.keyboard.press("Enter");
  await expect(alice.getByRole("heading", { name: "E2E-KEYBOARD" })).toBeVisible();
  await alice.getByLabel("Document").focus();
  const focused = await alice.evaluate(() => document.activeElement?.getAttribute("type"));
  expect(focused).toBe("file");
  await alice.keyboard.press("Tab");
  await expect(alice.getByRole("button", { name: "Upload" })).toBeFocused();
});
