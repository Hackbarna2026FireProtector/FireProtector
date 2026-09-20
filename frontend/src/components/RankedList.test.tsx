import { render, screen } from "@testing-library/react";
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
    // Deselect the "not threatened" tier chip.
    await userEvent.click(screen.getByRole("button", { name: "not threatened" }));
    expect(screen.queryByText("Asset a3")).not.toBeInTheDocument();
    expect(screen.getByText("Asset a1")).toBeInTheDocument();
  });

  it("threatened-only hides zero-risk assets", async () => {
    render(<RankedList result={scoreResult()} {...props} />);
    await userEvent.click(screen.getByLabelText(/threatened only/i));
    expect(screen.queryByText("Asset a3")).not.toBeInTheDocument();
    expect(screen.getByText("Asset a2")).toBeInTheDocument();
  });
});
