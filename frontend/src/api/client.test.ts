import { vi } from "vitest";

import { ApiError, getScenarios, postScore } from "./client";
import type { ScoreParams } from "./types";

const PARAMS: ScoreParams = {
  tau: 90,
  w_value: 1,
  w_conf: 1,
  w_vuln: 1,
  w_urgency: 1,
  horizon: null,
};

describe("api client", () => {
  it("parses the error envelope into ApiError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({ error: { code: "bad_request", message: "tau: too big" } }),
            {
              status: 400,
            },
          ),
      ),
    );
    const err = await postScore("f1", PARAMS).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(400);
    expect(err.code).toBe("bad_request");
    expect(err.message).toBe("tau: too big");
  });

  it("returns parsed JSON on success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ scenarios: [] }), { status: 200 })),
    );
    await expect(getScenarios()).resolves.toEqual({ scenarios: [] });
  });

  it("reads FastAPI's own {detail} errors as well as the contract envelope", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify({ detail: "No ignition scenario 'nope'." }), {
            status: 404,
          }),
      ),
    );
    const err = await postScore("nope", PARAMS).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(404);
    expect(err.message).toBe("No ignition scenario 'nope'.");
  });
});
