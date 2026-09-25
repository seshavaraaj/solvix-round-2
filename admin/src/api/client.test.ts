import { describe, expect, it, vi } from "vitest";
import { api, ApiError, onApiEvent, request, session } from "./client";
import { errorBody, jsonResponse, mockFetch } from "../test/helpers";

async function catchErr(p: Promise<unknown>): Promise<ApiError> {
  try {
    await p;
  } catch (e) {
    return e as ApiError;
  }
  throw new Error("expected rejection");
}

describe("api client error mapping", () => {
  it("adds the bearer token when logged in", async () => {
    session.set("abc", "operator");
    const f = mockFetch(() => jsonResponse(200, []));
    await api.getRoutes();
    const init = f.mock.calls[0][1] as RequestInit;
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer abc");
  });

  it("401 clears the session and emits unauthorized", async () => {
    session.set("abc", "operator");
    mockFetch(() => jsonResponse(401, errorBody("invalid_token")));
    const events: string[] = [];
    const off = onApiEvent((e) => events.push(e));
    const err = await catchErr(api.getClock());
    off();
    expect(err.status).toBe(401);
    expect(err.code).toBe("invalid_token");
    expect(session.token).toBeNull();
    expect(events).toEqual(["unauthorized"]);
  });

  it("409 surfaces as ApiError without global events", async () => {
    mockFetch(() => jsonResponse(409, errorBody("already_decided", "Already decided")));
    const listener = vi.fn();
    const off = onApiEvent(listener);
    const err = await catchErr(api.decide({ recommendation_id: "rec_1", decision: "approve" }));
    off();
    expect(err.status).toBe(409);
    expect(err.message).toBe("Already decided");
    expect(listener).not.toHaveBeenCalled();
  });

  it("429 keeps the server code", async () => {
    mockFetch(() => jsonResponse(429, errorBody("rate_limited")));
    const err = await catchErr(request("/crowding", { method: "POST", body: {} }));
    expect(err.status).toBe(429);
    expect(err.code).toBe("rate_limited");
  });

  it("503 loading emits waking", async () => {
    mockFetch(() => jsonResponse(503, errorBody("loading")));
    const events: string[] = [];
    const off = onApiEvent((e) => events.push(e));
    const err = await catchErr(api.getState());
    off();
    expect(err.status).toBe(503);
    expect(err.code).toBe("loading");
    expect(events).toEqual(["waking"]);
  });

  it("network failure emits waking", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))));
    const events: string[] = [];
    const off = onApiEvent((e) => events.push(e));
    const err = await catchErr(api.getRoutes());
    off();
    expect(err.status).toBe(0);
    expect(events).toEqual(["waking"]);
  });

  it("drops empty query params", async () => {
    const f = mockFetch(() => jsonResponse(200, []));
    await api.getRecommendations(undefined);
    expect(String(f.mock.calls[0][0])).toMatch(/\/recommendations$/);
    await api.getRecommendations("pending");
    expect(String(f.mock.calls[1][0])).toMatch(/\/recommendations\?status=pending$/);
  });
});
