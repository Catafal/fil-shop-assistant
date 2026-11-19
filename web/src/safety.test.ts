import { it, expect } from "vitest";
it("sends control actions without a body and keeps ownership in cookies", async () => {
  const { api } = await import("./safety");
  const original = globalThis.fetch;
  const requests: RequestInit[] = [];
  globalThis.fetch = async (_url, init) => {
    requests.push(init!);
    return new Response('{"ended":true}', {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };
  try {
    await api("/session/end", null);
    await api("/session/retry", null);
    for (const request of requests) {
      expect(request.method).toBe("POST");
      expect(request.body).toBeUndefined();
      expect(request.credentials).toBe("same-origin");
    }
  } finally {
    globalThis.fetch = original;
  }
});
