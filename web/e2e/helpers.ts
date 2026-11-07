import path from "node:path";

import AxeBuilder from "@axe-core/playwright";
import { type Browser, expect, type Page } from "@playwright/test";

export const SAMPLES = path.resolve("..", "samples");
export const sample = (name: string) => path.join(SAMPLES, name);

/** A signed-in page for one test person. The API checks a real signed token for them on every request. */
export async function signedIn(browser: Browser, user: string, viewport = { width: 1280, height: 900 }): Promise<Page> {
  const context = await browser.newContext({ viewport, baseURL: "http://127.0.0.1:3199" });
  await context.addCookies([{ name: "e2e-user", value: user, url: "http://127.0.0.1:3199" }]);
  return context.newPage();
}

export async function expectAccessible(page: Page) {
  const results = await new AxeBuilder({ page: page as never }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  const problems = results.violations.map((v) => `${v.id}: ${v.help} [${v.nodes.map((n) => n.target.join(" ")).slice(0, 3).join(" | ")}]`);
  expect(problems, `accessibility problems on ${page.url()}`).toEqual([]);
}

export async function expectNoSidewaysScroll(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow, `sideways scroll on ${page.url()}`).toBeLessThanOrEqual(0);
}

/** Create a shipment, upload its files, start the check and wait for the result. */
export async function checkShipment(page: Page, reference: string, files: string[]) {
  await page.goto("/workspace/shipments");
  await page.getByLabel("Reference", { exact: true }).fill(reference);
  await page.getByRole("button", { name: "Create shipment" }).click();
  await expect(page.getByRole("heading", { name: reference })).toBeVisible();
  let uploaded = 0;
  for (const file of files) {
    await page.getByLabel("Document").setInputFiles(sample(file));
    await page.getByRole("button", { name: "Upload" }).click();
    uploaded += 1;
    await expect(page.getByText(uploaded === 1 ? "1 document is ready to check." : `${uploaded} documents are ready to check.`)).toBeVisible();
  }
  await page.getByRole("button", { name: "Check quantities" }).click();
  await expect(page.getByText(/Rules version: meridian-\d+\./)).toBeVisible({ timeout: 120_000 });
}
