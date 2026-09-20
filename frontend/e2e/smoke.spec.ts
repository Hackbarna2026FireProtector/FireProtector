import { expect, test } from "@playwright/test";

test.describe("smoke", () => {
  test("app loads and API is healthy", async ({ page, request }) => {
    const health = await request.get("/api/health");
    expect(health.ok()).toBeTruthy();
    const body = await health.json();
    expect(body.status).toBe("ok");
    // Either provenance is fine here; `degraded` means nothing can be
    // forecast at all, which is a genuine failure of this smoke test.
    expect(["live", "cached"]).toContain(body.data_mode);

    await page.goto("/");
    await expect(page.getByText("FireProtector")).toBeVisible();
    await expect(page.getByTestId("data-mode-badge")).toHaveText(body.data_mode);

    // The first scenario in the seed file is what the picker opens on. The name
    // lives inside a <select> now, so assert on the selected value rather than
    // on visible text — a closed native select does not render its options.
    const scenarios = await (await request.get("/api/scenarios")).json();
    const first = scenarios.scenarios[0];
    const picker = page.getByTestId("scenario-select");
    await expect(picker).toBeVisible();
    await expect(picker).toHaveValue(first.scenario_id);
    await expect(page.getByText("Scenario")).toBeVisible();

    // Every colour on the map is explained somewhere on screen.
    await expect(page.getByTestId("map-legend")).toBeVisible();

    // Ranked list populates from /score. The first request for a scenario with
    // no recorded bundle runs a live simulation, so this waits a long time.
    await expect(page.getByTestId("ranked-list").locator("button").first()).toBeVisible({
      timeout: 120_000,
    });
  });
});
