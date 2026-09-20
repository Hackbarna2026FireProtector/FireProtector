import { displayName, hasRealName, rankDelta, rankMap } from "./ranks";
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

describe("displayName", () => {
  it("treats a name that repeats the type as a placeholder", () => {
    const row = { name: "residential", asset_type: "residential", asset_id: "asset-728456" };
    expect(hasRealName(row)).toBe(false);
    expect(displayName(row)).toBe("asset-728456");
  });

  it("keeps a real name", () => {
    const row = { name: "CAP La Jonquera", asset_type: "clinic", asset_id: "osm-12" };
    expect(hasRealName(row)).toBe(true);
    expect(displayName(row)).toBe("CAP La Jonquera");
  });

  it("falls back to the id when the name is empty", () => {
    expect(displayName({ name: "", asset_type: "shed", asset_id: "asset-1" })).toBe("asset-1");
  });
});

describe("displayName with the named layer missing", () => {
  it("shows the id even when the register name differs from the type", () => {
    // The register calls a storage tank "residential"; that is not a name.
    const row = { name: "residential", asset_type: "storageTank", asset_id: "asset-3893434" };
    expect(hasRealName(row, false)).toBe(false);
    expect(displayName(row, false)).toBe("asset-3893434");
    // With the layer available the same row is taken at its word.
    expect(displayName(row, true)).toBe("residential");
  });
});
