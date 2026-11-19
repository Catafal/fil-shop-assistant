# Fil: conversational shopping with observable actions

A customer rarely starts with a perfect product query. They describe an occasion, give an approximate size, change colour or language, and ask whether something can arrive in time. Fil is a fictional shop built to explore that customer journey through voice and a synchronized product interface.

Ona can retrieve a shortlist, inspect an exact variant, and request a temporary hold. The page shows catalogue facts and completed actions from the shop server. The agent interprets spoken consent, while the server validates the quote and stock. The catalogue, shipping, and holds are synthetic.

The central design decision is to make business state authoritative on the server. Search revisions invalidate old selections. Quotes bind one variant and delivery choice. Reservation creation rechecks stock atomically; retries return the same hold. An inventory-outage scenario returns a real failure rather than changing only the agent's prompt. The operator drawer shows these actual outcomes.

An early text simulation passed the evaluator after a prompt repair. Transcript review then found that the agent had invented a delivery deadline. A later tool revision requires the shopper's date phrase alongside the ISO date. The shop rejects a named weekday that conflicts with the ISO date and invalidates the quote. The agent still has to forward the shopper's words faithfully. The experience showed why we review the transcript and stored outcome alongside the evaluator score. [Date contract](architecture.md#checking-delivery)

Local tests cover stock, quote expiry, ownership, and retries. Text simulations exercise tool use and let reviewers inspect consent. Audio probes exercise speech transport. A human browser call still needs to verify audible playback, interruption recovery, and the visible product updates together. [Evaluation method](evaluation-v2.md)
