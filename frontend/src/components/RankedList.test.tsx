import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import "../i18n";
import { scoreResult } from "../testFixtures";
import RankedList from "./RankedList";

describe("RankedList", () => {
  const props = { prevRanks: new Map(), selectedId: null, onSelect: () => {} };

  it("renders all rows and filters by tier", async () => {
    render(<RankedList result={scoreResult()} {...props} />);
    expect(screen.getByText("Asset a1")).toBeInTheDocument();
    expect(screen.getByText("Asset a3")).toBeInTheDocument();
    // Deselect the "not threatened" tier chip. The chip now carries its count
    // too, so match on the tier name rather than the whole label.
    await userEvent.click(screen.getByRole("button", { name: /not threatened/i }));
    expect(screen.queryByText("Asset a3")).not.toBeInTheDocument();
    expect(screen.getByText("Asset a1")).toBeInTheDocument();
  });

  it("threatened-only hides zero-risk assets", async () => {
    render(<RankedList result={scoreResult()} {...props} />);
    await userEvent.click(screen.getByLabelText(/threatened only/i));
    expect(screen.queryByText("Asset a3")).not.toBeInTheDocument();
    expect(screen.getByText("Asset a2")).toBeInTheDocument();
  });

  it("counts what the filters are hiding", async () => {
    render(<RankedList result={scoreResult()} {...props} />);
    expect(screen.getByText("3 of 3")).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText(/threatened only/i));
    expect(screen.getByText("2 of 3")).toBeInTheDocument();
  });

  it("offers a way back when the filters match nothing", async () => {
    render(<RankedList result={scoreResult()} {...props} />);
    for (const tier of ["critical", "high", "not threatened"]) {
      await userEvent.click(screen.getByRole("button", { name: new RegExp(tier, "i") }));
    }
    expect(screen.getByText(/no assets match/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /clear filters/i }));
    expect(screen.getByText("Asset a1")).toBeInTheDocument();
  });

  it("says so when the named layer never arrived", () => {
    // A ranking of unnamed register buildings must not read as a place with no
    // critical facilities in it — see the note in the frontend README.
    const result = scoreResult();
    result.named_layer = { available: false, count: 0, error: "OSM query failed" };
    render(<RankedList result={result} {...props} />);
    expect(screen.getByTestId("named-layer-warning")).toBeInTheDocument();
    expect(screen.getByText(/names unavailable/i)).toBeInTheDocument();
  });

  it("shows ids, not register labels, when the named layer is missing", () => {
    const result = scoreResult();
    result.named_layer = { available: false, count: 0, error: "OSM query failed" };
    result.features[0].properties.name = "residential";
    result.features[0].properties.asset_type = "storageTank";
    render(<RankedList result={result} {...props} />);
    const list = within(screen.getByTestId("ranked-list"));
    expect(list.getByText("a1")).toBeInTheDocument();
    expect(list.queryByText("residential")).not.toBeInTheDocument();
  });

  it("hides the warning when names did arrive", () => {
    render(<RankedList result={scoreResult()} {...props} />);
    expect(screen.queryByTestId("named-layer-warning")).not.toBeInTheDocument();
  });

  it("shows the id instead of a name that only repeats the type", () => {
    const result = scoreResult();
    result.features[0].properties.name = "residential";
    result.features[0].properties.asset_type = "residential";
    render(<RankedList result={result} {...props} />);
    // Scoped to the list: "residential" is also a type-filter option now.
    const list = within(screen.getByTestId("ranked-list"));
    expect(list.getByText("a1")).toBeInTheDocument(); // the id stands in for the name
    expect(list.getByText("residential")).toBeInTheDocument(); // once, on the type line
  });
});
