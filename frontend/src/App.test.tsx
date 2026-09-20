import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import App from "./App";
import "./i18n";
import { scoreResult } from "./testFixtures";

vi.mock("./map/MapView", () => ({
  default: () => <div data-testid="map" />,
}));

const SCENARIO = {
  scenario_id: "la-jonquera-001",
  name: "La Jonquera",
  description: "Alt Emporda, near the border.",
  ignition_point: { type: "Point", coordinates: [2.87, 42.42] },
  declared_at: "2026-09-19T14:00:00Z",
};

function mockFetch() {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const payload =
      url === "/api/health"
        ? {
            status: "ok",
            data_mode: "cached",
            providers: {},
            recorded_scenarios: [SCENARIO.scenario_id],
          }
        : url === "/api/scenarios"
          ? { scenarios: [SCENARIO] }
          : url.endsWith("/spread")
            ? { type: "FeatureCollection", features: [] }
            : url.endsWith("/score")
              ? scoreResult()
              : url.endsWith("/sensitivity")
                ? {
                    robustness: "robust",
                    most_sensitive_parameter: "tau",
                    perturbations: [],
                    rank_ranges: {},
                  }
                : { parameters: {} };
    void init;
    return new Response(JSON.stringify(payload), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
}

describe("App", () => {
  it("renders the command-centre shell and loads data", async () => {
    vi.stubGlobal("fetch", mockFetch());
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: 0 } } })}>
        <App />
      </QueryClientProvider>,
    );
    expect(screen.getByText("FireProtector")).toBeInTheDocument();
    expect(screen.getByTestId("map")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("La Jonquera")).toBeInTheDocument());
    // The header must say this is a scenario, not an incident.
    expect(screen.getByText("Scenario")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByTestId("ranked-list").children.length).toBeGreaterThan(0),
    );
  });
});
