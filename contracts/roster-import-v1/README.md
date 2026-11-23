# roster-import/v1 fixtures

Canonical test fixtures for the club → roster deep link. Both repos test against
these files: `bolt-club-hq` (S8.3, the sender) and `roster-generator` (R1, the reader).
Contract: `bolt-club-hq/docs/PLAN.md` §8.1 and §8.3.

## Link format

```
{ROSTER_APP_URL}/planner#import=<base64url(JSON)>
```

The data sits in the URL fragment, so it is never sent to the server.

## Payload

```json
{
  "v": 1,
  "source": "bolt-club-hq",
  "event": { "title": "Thu Mixed Doubles", "starts_at": "2027-01-14T18:00:00Z", "format": "XD" },
  "players": [ { "name": "Ashok Bommisetti", "short": "Ashok", "guest": false } ]
}
```

- `v` must be `1`. Any other value is rejected with a friendly "unsupported version" message.
- `event.starts_at` and `event.format` are optional. `format` is a hint only.
- `players[].short` is optional. When missing, the reader uses the first word of `name`.
- `players[].guest` is optional and defaults to `false`.
- Readers ignore unknown fields.

## Limits

- Encoded fragment: at most 8192 characters.
- Players: at most 200.
- Each `name` and `short`: at most 120 characters.

## Layout

- `golden/`: payloads that must import correctly.
- `invalid/`: payloads that must show a banner and leave the planner usable.
  Malformed base64 and oversized payloads are generated in the tests, not stored here.
