import { fmtDistance, firstPoint, geometryDistance, haversineMeters } from "./geo";

describe("geo", () => {
  it("finds the first coordinate pair at any nesting depth", () => {
    expect(firstPoint([1.2, 41.8])).toEqual([1.2, 41.8]);
    expect(firstPoint([[[1.2, 41.8], [1.3, 41.9]]])).toEqual([1.2, 41.8]);
    expect(firstPoint([])).toBeNull();
    expect(firstPoint("nope")).toBeNull();
  });

  it("measures a known distance", () => {
    // One degree of latitude is ~111 km anywhere.
    const d = haversineMeters([2.87, 42.0], [2.87, 43.0]);
    expect(d).toBeGreaterThan(110_000);
    expect(d).toBeLessThan(112_000);
  });

  it("returns null when either geometry is missing or empty", () => {
    const pt = { type: "Point", coordinates: [2.87, 42.4] };
    expect(geometryDistance(undefined, pt)).toBeNull();
    expect(geometryDistance(pt, { type: "Point", coordinates: [] })).toBeNull();
  });

  it("measures between two geometries", () => {
    const a = { type: "Point", coordinates: [2.87, 42.405] };
    const b = { type: "Point", coordinates: [2.87, 42.42] };
    expect(geometryDistance(a, b)).toBeGreaterThan(1500);
  });

  it("switches unit at a kilometre", () => {
    expect(fmtDistance(840)).toBe("840 m");
    expect(fmtDistance(1449)).toBe("1.4 km");
    expect(fmtDistance(null)).toBe("—");
  });
});
