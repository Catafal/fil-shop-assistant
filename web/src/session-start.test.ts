import { it, expect, vi } from "vitest";
import { SessionStartGate } from "./session-start";
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}
it("never starts voice for a token arriving after End; serializes cleanup before another mint", async () => {
  const gate = new SessionStartGate(),
    token = deferred<string>(),
    cleanup = deferred<void>();
  const mint = vi.fn(() => token.promise),
    connect = vi.fn(),
    discard = vi.fn(() => cleanup.promise);
  const first = gate.run(mint, connect, discard);
  gate.cancel();
  expect(await gate.run(mint, connect, discard)).toBe(false);
  expect(mint).toHaveBeenCalledTimes(1);
  token.resolve("late-token");
  await Promise.resolve();
  expect(discard).toHaveBeenCalledWith("late-token");
  expect(connect).not.toHaveBeenCalled();
  expect(await gate.run(mint, connect, discard)).toBe(false);
  cleanup.resolve();
  expect(await first).toBe(false);
  expect(gate.pending).toBe(false);
  expect(await gate.run(async () => "fresh-token", connect, discard)).toBe(
    true,
  );
  expect(connect).toHaveBeenCalledExactlyOnceWith("fresh-token");
});
it("releases the mint lock after failure without connecting", async () => {
  const gate = new SessionStartGate(),
    connect = vi.fn();
  await expect(
    gate.run(
      async () => {
        throw Error("offline");
      },
      connect,
      async () => {},
    ),
  ).rejects.toThrow("offline");
  expect(gate.pending).toBe(false);
  expect(connect).not.toHaveBeenCalled();
});
