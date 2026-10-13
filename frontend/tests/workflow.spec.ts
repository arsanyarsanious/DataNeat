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
  await page.getByLabel("Choose spreadsheet").setInputFiles({
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

test("analysis sorting, privacy policy, and currency comma options", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Privacy policy" }),
  ).toBeVisible();
  await page.getByLabel("Choose spreadsheet").setInputFiles({
    name: "sorting.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      'Zulu,Amount,Alpha\n bad ,"$1,234.50", a \n good ,1234.50, b \n',
    ),
  });
  await expect(
    page.getByRole("heading", { name: "Meet your data." }),
  ).toBeVisible();
  const headings = page.locator(".column-analysis > .column-card h3");
  await expect(headings).toHaveText(["Alpha", "Amount", "Zulu"]);
  await page.getByLabel("Sort analysis columns").selectOption("position");
  await expect(headings).toHaveText(["Zulu", "Amount", "Alpha"]);
  await page.getByLabel("Sort analysis columns").selectOption("reverse");
  await expect(headings).toHaveText(["Alpha", "Amount", "Zulu"]);
  await page.getByRole("button", { name: "Review cleaning plan" }).click();
  await page.getByLabel("Symbol action for Amount").selectOption("add");
  await page.getByLabel("Symbol for Amount").fill("$");
  await page.getByLabel("Currency commas for Amount").selectOption("add");
  const operation = page
    .locator(".operation")
    .filter({ has: page.getByLabel("Symbol action for Amount") });
  await operation.getByRole("checkbox").first().check();
  await page.getByRole("button", { name: "Preview changes" }).click();
  await expect(
    page.getByRole("heading", { name: "After (preview)" }),
  ).toBeVisible();
  const after = page
    .locator(".comparison .panel")
    .filter({ has: page.getByRole("heading", { name: "After (preview)" }) });
  await expect(
    after.getByRole("cell", { name: "$1,234.50", exact: true }),
  ).toHaveCount(2);
});

test("imputation selection, preview, per-column approval, validation and download", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("Choose spreadsheet").setInputFiles({
    name: "missing.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("Amount,Category\n10,red\nNA,\n20,red\n"),
  });
  await page.getByRole("button", { name: "Review cleaning plan" }).click();
  const amount = page
    .locator(".operation")
    .filter({ has: page.getByLabel("Imputation method for Amount") });
  const category = page
    .locator(".operation")
    .filter({ has: page.getByLabel("Imputation method for Category") });
  await expect(
    amount.getByText("Suggested: Mean", { exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("Imputation method for Amount")).toHaveValue(
    "preserve",
  );
  await amount.locator(".operation-check input").check();
  await category.locator(".operation-check input").check();
  await page.getByLabel("Imputation method for Amount").selectOption("mean");
  await page.getByLabel("Imputation method for Category").selectOption("mode");
  await expect(
    page.getByRole("button", { name: "Apply cleaning" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Preview changes" }).click();
  const audit = page.getByRole("region", { name: "Imputation audit" });
  await expect(audit).toContainText("1 cells imputed");
  await expect(audit).toContainText("Remaining missing: 0");
  await expect(
    page.locator(".comparison td[data-is-imputed=true]"),
  ).toHaveCount(2);
  await page.getByLabel("Confirm imputation for Amount").check();
  await expect(
    page.getByRole("button", { name: "Apply cleaning" }),
  ).toBeDisabled();
  await page.getByLabel("Confirm imputation for Category").check();
  await expect(
    page.getByRole("button", { name: "Apply cleaning" }),
  ).toBeEnabled();
  // Changing a method invalidates the preview and both approvals.
  await page.getByLabel("Imputation method for Amount").selectOption("median");
  await expect(
    page.getByRole("button", { name: "Apply cleaning" }),
  ).toBeDisabled();
  await expect(page.locator(".comparison")).toHaveCount(0);
  await page.getByRole("button", { name: "Preview changes" }).click();
  await expect(
    page.getByLabel("Confirm imputation for Amount"),
  ).not.toBeChecked();
  await expect(
    page.getByLabel("Confirm imputation for Category"),
  ).not.toBeChecked();
  await page.getByLabel("Confirm imputation for Amount").check();
  await page.getByLabel("Confirm imputation for Category").check();
  await page.getByRole("button", { name: "Apply cleaning" }).click();
  await expect(
    page.getByRole("heading", { name: "Cleaning complete", exact: true }),
  ).toBeVisible();
  await expect(page.locator("td[data-is-imputed=true]")).toHaveCount(2);
  await expect(
    page.getByRole("region", { name: "Imputation audit" }),
  ).toContainText("median");
  const csvDownload = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download CSV", exact: true }).click();
  const csv = await csvDownload;
  expect(await fs.readFile((await csv.path())!, "utf8")).toContain("15.0,red");
  const reportDownload = page.waitForEvent("download");
  await page.getByRole("link", { name: /report/i }).click();
  const report = await reportDownload;
  const data = JSON.parse(await fs.readFile((await report.path())!, "utf8"));
  expect(data.validation.imputed_cells).toBe(2);
  expect(
    data.operations.find((o: { method?: string }) => o.method === "median")
      .imputed_cells[0],
  ).toMatchObject({ spreadsheet_row: 3, is_imputed: true });
  await page.getByRole("button", { name: "Delete file", exact: true }).click();
});

test("grouped ordered imputation requires dependencies and stays within entities", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .getByLabel("Choose spreadsheet")
    .setInputFiles("../sample_data/missing_measurements.csv");
  await page.getByRole("button", { name: "Review cleaning plan" }).click();
  await page
    .getByLabel("Imputation method for Reading")
    .selectOption("group_forward_fill");
  const operation = page
    .locator(".operation")
    .filter({ has: page.getByLabel("Imputation method for Reading") });
  await operation.locator(".operation-check input").check();
  await page.getByRole("button", { name: "Preview changes" }).click();
  await expect(page.locator(".error[role=alert]")).toContainText(
    "grouped method requires grouping columns",
  );
  await page.getByLabel("Group Reading by Entity").check();
  await page.getByLabel("Imputation order for Reading").selectOption("Time");
  await page.getByRole("button", { name: "Preview changes" }).click();
  await expect(
    page.getByRole("region", { name: "Imputation audit" }),
  ).toContainText("Grouping: Entity · Ordering: Time");
  await expect(page.locator(".comparison td[data-is-imputed=true]")).toHaveText(
    ["Estimated10", "Estimated100"],
  );
  await expect(
    page.getByRole("button", { name: "Apply cleaning" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Delete file", exact: true }).click();
});

test("currency salary offers mean and median after approved numeric formatting", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("Choose spreadsheet").setInputFiles({
    name: "salary.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("Salary\n$1000\nNA\n$3000\n"),
  });
  await page.getByRole("button", { name: "Review cleaning plan" }).click();
  const method = page.getByLabel("Imputation method for Salary");
  await expect(method.locator('option[value="mean"]')).toHaveCount(1);
  await expect(method.locator('option[value="median"]')).toHaveCount(1);
  await method.selectOption("mean");
  await page
    .locator(".operation")
    .filter({ has: method })
    .locator(".operation-check input")
    .check();
  await page.getByLabel("Symbol action for Salary").selectOption("remove");
  await page
    .locator(".operation")
    .filter({ has: page.getByLabel("Symbol action for Salary") })
    .locator(".operation-check input")
    .check();
  await page.getByRole("button", { name: "Preview changes" }).click();
  await expect(
    page.locator(".comparison td[data-is-imputed=true]"),
  ).toContainText("2000");
  await page.getByRole("button", { name: "Delete file", exact: true }).click();
});

test("interactive spreadsheet basic cleanup, colored hover issues, confirmed fixes and export", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .getByText("Interactive spreadsheet: basic cleanup first", { exact: false })
    .click();
  await page.getByLabel("Choose spreadsheet").setInputFiles({
    name: "interactive.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      "Customer_ID,Name,Birth_Date,Salary,Email\n001, mary david ,2025-01-02,$100,bad-email\n002,MARY DAVID,05/10/2025,200,mary@example.com\n003,Other,88-99-2089,NA,other@example.com\n",
    ),
  });
  await expect(
    page.getByRole("heading", { name: "Your interactive spreadsheet." }),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "Mary David", exact: true }),
  ).toHaveCount(2);
  const cell = page.getByRole("button", { name: /Issues in Birth_Date row 4/ });
  await cell.hover();
  const dialog = page.getByRole("dialog", { name: "Fix Birth_Date row 4" });
  await expect(dialog).toBeVisible();
  await dialog.getByLabel("Corrected cell value").fill("2025-10-06");
  await dialog.getByRole("button", { name: "Preview fix" }).click();
  await expect(dialog).toContainText("1 cells / rows would change");
  await expect(cell).toContainText("88-99-2089");
  await dialog.getByRole("button", { name: "Confirm and apply" }).click();
  await expect(cell).toHaveCount(0);
  await expect(
    page.getByRole("cell", { name: "2025-10-06", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: /Issues in Email row 2/ }).click();
  await page.getByLabel("Corrected cell value").fill("mary@example.com");
  await page.getByRole("button", { name: "Preview fix" }).click();
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(
    page.getByRole("button", { name: /Issues in Email row 2/ }),
  ).toContainText("bad-email");
  await page.keyboard.press("Escape");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: /Issues in Salary row 4/ }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.keyboard.press("Escape");
  const downloaded = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download CSV", exact: true }).click();
  const download = await downloaded;
  expect(await fs.readFile((await download.path())!, "utf8")).toContain(
    "2025-10-06",
  );
  await page.getByRole("button", { name: "Delete file", exact: true }).click();
});
