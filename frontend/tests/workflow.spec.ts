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
  await expect(
    page.getByRole("cell", { name: "001", exact: true }).first(),
  ).toBeVisible();
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

test("invalid dates and currency issues are grouped by column and can be explicitly resolved", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("Choose spreadsheet").setInputFiles({
    name: "issues.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      "Event,Amount\n88-99-2089,$100\n31/02/2025,200 USD\n05/10/2025,300\n2025-10-05,400\n",
    ),
  });
  await expect(
    page.getByRole("heading", { name: "Meet your data." }),
  ).toBeVisible();
  const analysis = page.getByRole("region", {
    name: "Analysis for column Event",
  });
  await expect(
    analysis.getByRole("heading", { name: "Event", exact: true }),
  ).toBeVisible();
  await expect(
    analysis.getByText("Invalid dates", { exact: true }),
  ).toBeVisible();
  await expect(analysis.getByText("88-99-2089", { exact: true })).toBeVisible();
  const amount = page.getByRole("region", {
    name: "Analysis for column Amount",
  });
  await expect(
    amount.getByText("Mixed currency notation", { exact: true }),
  ).toBeVisible();
  await expect(
    amount.getByText("bare number: 2 rows", { exact: true }),
  ).toBeVisible();
  await expect(
    page.locator(".column-analysis .column-section-heading h3"),
  ).toHaveText(["Amount", "Event"]);
  await page.getByRole("button", { name: "Review cleaning plan" }).click();
  const dateGroup = page.getByRole("region", {
    name: "Cleaning actions for column Event",
  });
  const dates = dateGroup
    .locator(".operation")
    .filter({ has: page.getByLabel("Invalid date action for Event") });
  await expect(dates.getByRole("checkbox").first()).not.toBeChecked();
  await dates.getByRole("checkbox").first().check();
  await page.getByLabel("Corrected date for Event row 2").fill("2025-10-06");
  await page.getByLabel("Empty Event row 3", { exact: true }).check();
  const money = page
    .getByRole("region", { name: "Cleaning actions for column Amount" })
    .locator(".operation")
    .filter({
      has: page.getByLabel("Symbol action for Amount", { exact: true }),
    });
  await money.getByRole("checkbox").first().check();
  await page.getByLabel("Symbol action for Amount").selectOption("legacy");
  await page
    .getByLabel("Currency for Amount", { exact: true })
    .selectOption("USD");
  await page
    .getByLabel("Assume bare amounts are USD in Amount", { exact: true })
    .check();
  await page.getByLabel("Assign $ to USD in Amount", { exact: true }).check();
  await page
    .getByLabel("Currency for Amount", { exact: true })
    .selectOption("EUR");
  await expect(
    page.getByLabel("Assume bare amounts are EUR in Amount", { exact: true }),
  ).not.toBeChecked();
  await page
    .getByLabel("Currency for Amount", { exact: true })
    .selectOption("USD");
  await page
    .getByLabel("Assume bare amounts are USD in Amount", { exact: true })
    .check();
  await page.getByLabel("Assign $ to USD in Amount", { exact: true }).check();

  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/column-cleaning-mobile.png",
    fullPage: true,
    caret: "initial",
  });
  await page.setViewportSize({ width: 1280, height: 720 });

  await page.getByRole("button", { name: "Preview changes" }).click();
  const after = page
    .locator(".comparison .panel")
    .filter({ has: page.getByRole("heading", { name: "After (preview)" }) });
  await expect(
    after.getByRole("cell", { name: "2025-10-06", exact: true }),
  ).toBeVisible();
  await expect(
    after.getByRole("cell", { name: "empty", exact: true }),
  ).toBeVisible();
  await expect(
    after.getByRole("cell", { name: "05/10/2025", exact: true }),
  ).toBeVisible();
  await expect(
    after.getByRole("cell", { name: "USD 300", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Apply cleaning" }).click();
  await expect(
    page.getByRole("heading", { name: "Cleaning complete", exact: true }),
  ).toBeVisible();
  const downloaded = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download CSV", exact: true }).click();
  const result = await downloaded;
  const text = await fs.readFile((await result.path())!, "utf8");
  expect(text).toContain("2025-10-06,USD 100");
  expect(text).toContain(",USD 200");
  expect(text).toContain("05/10/2025,USD 300");
  expect(text).not.toContain("88-99-2089");
  await page.screenshot({
    path: "test-results/column-issue-results.png",
    fullPage: true,
    caret: "initial",
  });
  await page.getByRole("button", { name: "Delete file", exact: true }).click();
});

test("impossible dates can be cleared without changing valid or ambiguous dates", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("Choose spreadsheet").setInputFiles({
    name: "dates.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      "Event\n88-99-2089\n31/02/2025\n05/10/2025\n2025-10-05\n",
    ),
  });
  await page.getByRole("button", { name: "Review cleaning plan" }).click();
  const dates = page
    .locator(".operation")
    .filter({ has: page.getByLabel("Invalid date action for Event") });
  await dates.getByRole("checkbox").first().check();
  await page.getByLabel("Invalid date action for Event").selectOption("empty");
  await page.getByRole("button", { name: "Apply cleaning" }).click();
  await expect(
    page.getByRole("heading", { name: "Cleaning complete", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "empty", exact: true }),
  ).toHaveCount(2);
  await expect(
    page.getByRole("cell", { name: "05/10/2025", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "2025-10-05", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Delete file", exact: true }).click();
});

test("select all reflects partial selection, includes duplicates, and deselects all", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("Choose spreadsheet").setInputFiles({
    name: "bulk.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("City,Rate\n Cairo ,10%\ncairo,20\ncairo,20\n"),
  });
  await page.getByRole("button", { name: "Review cleaning plan" }).click();
  const all = page.getByLabel("Select all cleaning actions");
  await expect(all).toHaveJSProperty("indeterminate", true);
  await all.check();
  const operations = page.locator(
    ".operation > .operation-check input[type=checkbox]",
  );
  for (const checkbox of await operations.all())
    await expect(checkbox).toBeChecked();
  await expect(page.locator(".plan-selection")).toContainText(
    "including 1 action that removes rows",
  );
  await operations.first().uncheck();
  await expect(all).not.toBeChecked();
  await expect(all).toHaveJSProperty("indeterminate", true);
  await all.check();
  await expect(all).toHaveJSProperty("indeterminate", false);
  await page.getByRole("button", { name: "Deselect all", exact: true }).click();
  for (const checkbox of await operations.all())
    await expect(checkbox).not.toBeChecked();
  await expect(all).not.toBeChecked();
  await expect(all).toHaveJSProperty("indeterminate", false);
  await page.getByRole("button", { name: "Delete file", exact: true }).click();
});

test("mixed percentage notation can include or omit sign without corrupting ratios", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("Choose spreadsheet").setInputFiles({
    name: "percent.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("Rate\n10%\n0.2\n30%\n"),
  });
  await expect(
    page
      .getByRole("region", { name: "Analysis for column Rate" })
      .getByText("Mixed percentage notation", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Review cleaning plan" }).click();
  await page.getByLabel("Select all cleaning actions").check();
  await page.getByLabel("Percentage action for Rate").selectOption("legacy");
  await page
    .getByLabel("Bare percentage interpretation for Rate")
    .selectOption("fraction");
  await page.getByRole("button", { name: "Preview changes" }).click();
  let after = page
    .locator(".comparison .panel")
    .filter({ has: page.getByRole("heading", { name: "After (preview)" }) });
  await expect(
    after.getByRole("cell", { name: "20%", exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("Percentage format for Rate")
    .selectOption("without_sign");
  await page.getByRole("button", { name: "Preview changes" }).click();
  after = page
    .locator(".comparison .panel")
    .filter({ has: page.getByRole("heading", { name: "After (preview)" }) });
  await expect(
    after.getByRole("cell", { name: "20", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Apply cleaning" }).click();
  await expect(
    page.getByRole("heading", { name: "Cleaning complete", exact: true }),
  ).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download CSV", exact: true }).click();
  const result = await download;
  expect(await fs.readFile((await result.path())!, "utf8")).toContain(
    "10\n20\n30",
  );
  await page.getByRole("button", { name: "Delete file", exact: true }).click();
});

test("simple add, remove, and no-change choices cover percentages, symbols, and phone prefixes", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .getByLabel("Choose spreadsheet")
    .setInputFiles({
      name: "formats.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(
        "Rate,Amount,Phone,Weight\n10%,$100,+201001234567,10kg\n20,200 EUR,201001234567,20\n0.2,300,01001234567,30 kg\n",
      ),
    });
  await expect(
    page
      .getByRole("region", { name: "Analysis for column Phone" })
      .getByText("Mixed country codes and + notation", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Review cleaning plan" }).click();
  await page.getByLabel("Select all cleaning actions").check();
  // Only these formatting actions should be selected for an exact no-change comparison.
  const whitespace = page
    .locator(".operation")
    .filter({ hasText: "Trim Whitespace" });
  for (const op of await whitespace.all())
    await op.locator(".operation-check input").uncheck();
  await expect(page.getByLabel("Percentage action for Rate")).toHaveValue(
    "preserve",
  );
  await expect(page.getByLabel("Symbol action for Amount")).toHaveValue(
    "preserve",
  );
  await expect(page.getByLabel("Phone action for Phone")).toHaveValue(
    "preserve",
  );
  await page.getByRole("button", { name: "Preview changes" }).click();
  let after = page
    .locator(".comparison .panel")
    .filter({ has: page.getByRole("heading", { name: "After (preview)" }) });
  await expect(
    after.getByRole("cell", { name: "200 EUR", exact: true }),
  ).toBeVisible();
  await expect(
    after.getByRole("cell", { name: "01001234567", exact: true }),
  ).toBeVisible();
  await page.getByLabel("Percentage action for Rate").selectOption("add");
  await page.getByLabel("Symbol action for Amount").selectOption("add");
  await page.getByLabel("Symbol for Amount").fill("$");
  await page.getByLabel("Symbol position for Amount").selectOption("suffix");
  await page.getByLabel("Symbol action for Weight").selectOption("add");
  await page.getByLabel("Symbol for Weight").fill("kg");
  await page.getByLabel("Phone action for Phone").selectOption("international");
  await page
    .getByLabel("Phone country for Phone", { exact: true })
    .selectOption("EG");
  await page.getByRole("button", { name: "Preview changes" }).click();
  after = page
    .locator(".comparison .panel")
    .filter({ has: page.getByRole("heading", { name: "After (preview)" }) });
  await expect(
    after.getByRole("cell", { name: "20%", exact: true }),
  ).toBeVisible();
  await expect(
    after.getByRole("cell", { name: "0.2%", exact: true }),
  ).toBeVisible();
  await expect(
    after.getByRole("cell", { name: "200$", exact: true }),
  ).toBeVisible();
  await expect(
    after.getByRole("cell", { name: "+201001234567", exact: true }),
  ).toHaveCount(3);
  await page.getByLabel("Percentage action for Rate").selectOption("remove");
  await page.getByLabel("Symbol action for Amount").selectOption("remove");
  await page.getByLabel("Symbol action for Weight").selectOption("remove");
  await page.getByLabel("Phone action for Phone").selectOption("national");
  await page.getByRole("button", { name: "Preview changes" }).click();
  after = page
    .locator(".comparison .panel")
    .filter({ has: page.getByRole("heading", { name: "After (preview)" }) });
  await expect(
    after.getByRole("cell", { name: "01001234567", exact: true }),
  ).toHaveCount(3);
  await expect(
    after.getByRole("cell", { name: "200", exact: true }),
  ).toBeVisible();
  await expect(
    after.getByRole("cell", { name: "0.2", exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("Phone action for Phone")
    .selectOption("international_digits");
  await page.getByRole("button", { name: "Preview changes" }).click();
  after = page
    .locator(".comparison .panel")
    .filter({ has: page.getByRole("heading", { name: "After (preview)" }) });
  await expect(
    after.getByRole("cell", { name: "201001234567", exact: true }),
  ).toHaveCount(3);
  await page.getByRole("button", { name: "Apply cleaning" }).click();
  await expect(
    page.getByRole("heading", { name: "Cleaning complete", exact: true }),
  ).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download CSV", exact: true }).click();
  const result = await download;
  const text = await fs.readFile((await result.path())!, "utf8");
  expect(text).toContain("10,100,201001234567,10");
  expect(text).toContain("20,200,201001234567,20");
  await page.getByRole("button", { name: "Delete file", exact: true }).click();
});
