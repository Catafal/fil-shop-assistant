# How a conversation changes the shop

The voice agent interprets the shopper's request and calls three tools. FastAPI applies the shop rules in SQLite. The React page reads a session snapshot from the server and shows the current shortlist, quote, and hold. The activity panel shows the observed tool outcomes and labels retries.

| Tool | What the shop server does |
| --- | --- |
| `search_products` | Applies the agreed filters, returns up to three matching products, and advances the search revision. |
| `check_variant` | Checks the exact size and colour against current results. Returns stock, garment measurements, and a delivery estimate. An eligible variant gets a two-minute quote. |
| `reserve_variant` | Validates the current quote, rechecks stock, and creates one ten-minute hold in a SQLite write transaction. |

## Changing a preference

A new search clears the previous variant and quote. A different delivery choice or failed check also invalidates the old quote. The browser polls `/demo/session` for state tied to its session and rejects late snapshots that would restore an old selection.

The shopper can change the spoken language independently of the interface language. The agent receives English, Catalan, and Spanish presets and the `language_detection` tool. After a language switch, the agent must continue with the agreed criteria unless the shopper changes them. The transcript preserves the language spoken.

## Checking delivery

Fil estimates delivery for Barcelona and Madrid using a noon dispatch cutoff in `Europe/Madrid`. It counts Monday through Friday and uses no holiday calendar. Standard delivery costs €4.95 and takes two business days after dispatch. Express costs €9.95 and takes one. Unsupported destinations and dates the shop cannot meet yield no reservable quote.

The tool requires an ISO date and the shopper's date phrase. A mismatch between a named weekday and the ISO date clears the quote and asks for clarification. The check applies to the fields submitted by the agent and depends on the agent forwarding the original phrase.

## Creating a hold

The agent is instructed to confirm the exact item, size, colour, item price, shipping cost, and hold duration and wait for permission. Spoken consent is verified by reviewing the conversation. The server validates quote ownership, revision, expiry, and stock independently.

Available stock equals stock on hand minus active holds. The transaction prevents two shoppers from taking the last unit. An exact retry returns the existing active hold even if its original quote has expired. Retrying an expired hold cannot create a replacement.

## Session and failure boundaries

The browser owns an HttpOnly session cookie. The server binds that session to the conversation returned when it mints a voice token. Webhooks authenticate separately with a service credential and a provider-assigned conversation ID. Provider simulations can call the tools without access to a visitor's browser session.

The guided demo sends a fixed scenario through the same shop operations and browser view. Each guided session gets a temporary SQLite store with its own stock, quotes, and holds. Guided actions use the same browser ownership and origin checks, and do not request a voice token.

The inventory outage option scopes a tool failure to one browser session. A separate inventory fixture exercises unknown stock in provider simulations. The server keeps unknown and out-of-stock results distinct.

The app seeds eight fictional products on startup. SQLite preserves stock, quotes, and holds across restarts. Browser ownership and activity live in memory, so the demo runs as a single worker and a restart starts a new browser session.
