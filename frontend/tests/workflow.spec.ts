import { test, expect } from "@playwright/test";
import fs from "node:fs/promises";
test("upload, review, preserve ambiguous dates, clean, download and delete", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Good data starts here." }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/landing-desktop.png",
    fullPage: true,
    caret: "initial",
  });
  await page
    .getByLabel("Choose spreadsheet")
    .setInputFiles("../sample_data/messy_customers.csv");
  await expect(
    page.getByRole("heading", { name: "Meet your data." }),
  ).toBeVisible();
  await expect(page.getByText("001", { exact: true }).first()).toBeVisible();
  await expect(
    page.getByText("Day-first evidence: 1 · Month-first: 0"),
  ).toBeVisible();
  await page.getByRole("button", { name: "Review cleaning plan" }).click();
  await expect(
    page.getByLabel("Date interpretation for Birth_Date"),
  ).toHaveValue("preserve");
  const dateOperation = page
    .locator(".operation")
    .filter({ has: page.getByLabel("Date interpretation for Birth_Date") });
  await dateOperation.getByRole("checkbox").check();
  const duplicates = page
    .locator(".operation")
    .filter({ hasText: "Remove Duplicates" });
  await expect(duplicates.getByRole("checkbox")).not.toBeChecked();
  await duplicates.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Preview changes" }).click();
  await expect(
    page.getByRole("heading", { name: "After (preview)" }),
  ).toBeVisible();
  await expect(
    page.locator(".comparison").getByText("05/10/2025", { exact: true }),
  ).toHaveCount(2);
  await page.getByRole("button", { name: "Apply cleaning" }).click();
  await expect(
    page.getByRole("heading", { name: "Cleaning complete", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("6 → 5", { exact: true })).toBeVisible();
  await page.screenshot({
    path: "test-results/results-desktop.png",
    fullPage: true,
    caret: "initial",
  });
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download CSV", exact: true }).click();
  const downloaded = await download;
  const path = await downloaded.path();
  const text = await fs.readFile(path!, "utf8");
  expect(text).toContain("001,Cairo");
  expect(text).toContain("05/10/2025");
  expect(text).toContain("'=SUM(A1:A2)");
  await page.getByRole("button", { name: "Delete file", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Good data starts here." }),
  ).toBeVisible();
});
test("file errors and responsive theme", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByLabel("Choose spreadsheet").setInputFiles({
    name: "bad.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("invalid"),
  });
  await expect(
    page.getByRole("alert").filter({ hasText: "Choose a CSV" }),
  ).toContainText("Choose a CSV or XLSX");
  await page.getByRole("button", { name: "Toggle theme", exact: true }).click();
  await expect(page.locator("html")).toHaveClass("dark");
  await page.screenshot({
    path: "test-results/landing-mobile-dark.png",
    fullPage: true,
    caret: "initial",
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});

test("Excel worksheet selection and explicit date interpretation", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .getByLabel("Choose spreadsheet")
    .setInputFiles("../sample_data/messy_workbook.xlsx");
  await expect(
    page.getByRole("heading", { name: "Meet your data." }),
  ).toBeVisible();
  await page.getByLabel("Worksheet", { exact: true }).selectOption("Inventory");
  await expect(
    page.getByRole("cell", { name: "0007", exact: true }),
  ).toBeVisible();
  await page.getByLabel("Worksheet", { exact: true }).selectOption("Customers");
  await expect(
    page.getByRole("cell", { name: "001", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Review cleaning plan" }).click();
  const dates = page
    .locator(".operation")
    .filter({ has: page.getByLabel("Date interpretation for Birth_Date") });
  await dates.getByRole("checkbox").check();
  await page
    .getByLabel("Date interpretation for Birth_Date")
    .selectOption("month_first");
  await page.getByRole("button", { name: "Apply cleaning" }).click();
  await expect(
    page.getByRole("heading", { name: "Cleaning complete", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "2025-05-10", exact: true }),
  ).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download XLSX", exact: true }).click();
  expect((await download).suggestedFilename()).toBe("dataneat-cleaned.xlsx");
  await page.getByRole("button", { name: "Delete file", exact: true }).click();
});
