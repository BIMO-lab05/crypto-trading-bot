---
type: decision
status: accepted
date: 2026-07-28
context: "every authenticated Bybit POST failed retCode 10004 'error sign' because signed bytes != transmitted bytes"
deciders: [operator]
tags: [decision, adr, bybit-connector, security, signing]
created: 2026-07-29
updated: 2026-07-29
---

# ADR-023: Bybit request-signing fix — sign the exact compact bytes transmitted

## Context

The bybit-connector signed the request body with `json.dumps(data)` (default separators `", "` / `": "`, i.e. with spaces) but transmitted the body via httpx's `json=`, which serializes *compactly* (`","` / `":"`). Bybit recomputes the HMAC over the received bytes; because the signed string and the sent string differed byte-for-byte, Bybit rejected **every authenticated POST** with `retCode 10004` ("error sign") — order placement and cancellation were broken on the live path. GETs had an analogous risk: the signature sorts query params, but an unsorted dict could transmit a different query string.

## Decision

`bybit-connector/app/bybit_rest_client.py`:

- **Serialize the body once, compactly, and send those exact bytes.** `body_str = json.dumps(data, separators=(",", ":"), ensure_ascii=False)` is computed once, signed via `authenticator.get_headers(body=body_str)`, and transmitted verbatim through httpx `content=body_str` (not `json=`). Signed bytes == transmitted bytes. `bybit_rest_client.py:138-162, 208-214`.
- **Transmit query params in signed (sorted) order.** `ordered_params = sorted(params.items())` so the GET query string matches the string the signature was computed over. `bybit_rest_client.py:202-211`.

## Consequences

- Authenticated POSTs (create/cancel order) and signed GETs pass Bybit's signature check; the LIVE order path works.
- This is a live-path correctness fix; paper mode does not route to the connector (see [[ADR-006-mainnet-prices-paper-orders]]), so it is a prerequisite for LIVE but does not change paper behavior.

## Related

- `services/bybit-connector/app/bybit_rest_client.py:138-214`
- [[../modules/bybit-connector]]
- [[ADR-004-paper-trading-default]]
- [[../flows/Order-Lifecycle]]
