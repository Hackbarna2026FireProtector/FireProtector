import { rankDelta, rankMap } from "./ranks";
import { scoreResult } from "../testFixtures";

describe("rank helpers", () => {
  it("maps asset_id to rank", () => {
    const m = rankMap(scoreResult().features);
    expect(m.get("a1")).toBe(1);
    expect(m.get("a3")).toBe(3);
  });

  it("computes positive delta when rank improves (number decreases)", () => {
    const prev = new Map([["a1", 3]]);
    expect(rankDelta("a1", 1, prev)).toBe(2);
    expect(rankDelta("a1", 5, prev)).toBe(-2);
    expect(rankDelta("new", 1, prev)).toBe(0);
  });
});
