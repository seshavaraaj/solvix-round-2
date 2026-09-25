import { describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { Recommendation } from "../api/types";
import { RecommendationCard } from "./RecommendationCard";
import { errorBody, jsonResponse, mockFetch } from "../test/helpers";

const rec: Recommendation = {
  id: "rec_0017",
  created_at: "2026-09-25T17:15:00+05:30",
  action: "move_bus",
  from_route_id: "423",
  to_route_id: "534",
  bus_count: 2,
  window_start: "2026-09-25T17:30:00+05:30",
  window_end: "2026-09-25T19:00:00+05:30",
  trigger_flags: ["overcrowded"],
  expected_effect: {
    to_route: { wait_min_before: 11, wait_min_after: 7, peak_load_before: 1.25, peak_load_after: 0.92 },
    from_route: { wait_min_before: 7.5, wait_min_after: 9, peak_load_before: 0.28, peak_load_after: 0.41 },
  },
  deadhead_km: 6,
  confidence: "high",
  explanation: "Move 2 buses from Route 423 to Route 534, 17:30–19:00.",
  status: "pending",
  solver: "cp_sat",
};

function setup(r: Recommendation = rec) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <RecommendationCard rec={r} />
    </QueryClientProvider>,
  );
}

function bodyOf(init?: RequestInit) {
  return JSON.parse(String(init?.body));
}

describe("RecommendationCard", () => {
  it("shows the explanation and before/after numbers", () => {
    mockFetch(() => jsonResponse(200, []));
    setup();
    expect(screen.getByText(/Move 2 buses from Route 423/)).toBeInTheDocument();
    const cell = (re: RegExp) => screen.getByText((_, el) => el?.tagName === "TD" && re.test(el.textContent ?? ""));
    expect(cell(/125%\s*→\s*92%/)).toBeInTheDocument();
    expect(cell(/11\.0\s*→\s*7\.0\s*min/)).toBeInTheDocument();
  });

  it("approve posts a decision", async () => {
    const f = mockFetch((url) =>
      url.endsWith("/decisions") ? jsonResponse(201, { recommendation_id: rec.id, decision: "approve" }) : jsonResponse(200, []),
    );
    setup();
    await userEvent.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(f).toHaveBeenCalled());
    const call = f.mock.calls.find((c) => String(c[0]).endsWith("/decisions"))!;
    expect(bodyOf(call[1])).toEqual({ recommendation_id: "rec_0017", decision: "approve" });
  });

  it("reject requires a reason, then sends reason and note", async () => {
    const f = mockFetch(() => jsonResponse(201, {}));
    setup();
    await userEvent.click(screen.getByRole("button", { name: "Reject" }));
    const dialog = screen.getByRole("dialog");
    const submit = dialog.querySelector("button[type=submit]") as HTMLButtonElement;

    await userEvent.click(submit);
    expect(screen.getByText("Choose a reason.")).toBeInTheDocument();
    expect(f).not.toHaveBeenCalled();

    await userEvent.selectOptions(screen.getByLabelText("Reason"), "no_driver");
    await userEvent.type(dialog.querySelector("textarea")!, "Shift ends 18:00");
    await userEvent.click(submit);

    await waitFor(() => expect(f).toHaveBeenCalled());
    expect(bodyOf(f.mock.calls[0][1])).toEqual({
      recommendation_id: "rec_0017",
      decision: "reject",
      reason: "no_driver",
      note: "Shift ends 18:00",
    });
  });

  it("409 shows an already-decided notice", async () => {
    mockFetch(() => jsonResponse(409, errorBody("already_decided")));
    setup();
    await userEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(await screen.findByText(/Already decided by someone else/)).toBeInTheDocument();
  });

  it("decided cards have no action buttons", () => {
    mockFetch(() => jsonResponse(200, []));
    setup({ ...rec, status: "approved" });
    expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
    expect(screen.getByText("approved")).toBeInTheDocument();
  });
});
