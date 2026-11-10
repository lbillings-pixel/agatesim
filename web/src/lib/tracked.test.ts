import { afterEach, describe, expect, it, vi } from "vitest";

import { tracked } from "../api";

describe("tracked", () => {
  afterEach(() => vi.unstubAllGlobals());

  const cancels = () => {
    const fetched = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(() =>
      Promise.resolve(new Response(null, { status: 204 })),
    );
    vi.stubGlobal("fetch", fetched);
    return () => fetched.mock.calls.filter(([url, init]) => url === "/api/progress/t1" && init?.method === "DELETE").length;
  };

  it("names the task, and cancels it on the server if abandoned while it runs", async () => {
    const sent = cancels();
    const control = new AbortController();
    const running = tracked("t1", control.signal, (named) => {
      expect(named).toEqual({ "X-Progress": "t1" });
      return new Promise<never>((_resolve, reject) => {
        control.signal.addEventListener("abort", () => reject(new Error("abandoned")));
      });
    });
    control.abort();
    await expect(running).rejects.toThrow("abandoned");
    expect(sent()).toBe(1);
  });

  it("sends nothing when a finished request is abandoned later", async () => {
    const sent = cancels();
    const control = new AbortController();
    await expect(tracked("t1", control.signal, () => Promise.resolve(7))).resolves.toBe(7);
    control.abort();
    expect(sent()).toBe(0);
  });

  it("sends no header without a task", async () => {
    await expect(tracked(undefined, null, (named) => Promise.resolve(named))).resolves.toEqual({});
  });
});
