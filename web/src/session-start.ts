/** Serialize token minting through cancellation cleanup: the endpoint owns one session per cookie. */
export class SessionStartGate {
  private generation = 0;
  pending = false;

  cancel() {
    this.generation += 1;
  }

  async run<T>(
    mint: () => Promise<T>,
    connect: (session: T) => void,
    discard: (session: T) => Promise<void>,
  ): Promise<boolean> {
    if (this.pending) return false;
    const generation = ++this.generation;
    this.pending = true;
    try {
      const session = await mint();
      if (generation !== this.generation) {
        await discard(session);
        return false;
      }
      connect(session);
      return true;
    } finally {
      this.pending = false;
    }
  }
}
