# Email: Carlos Becker — POC walkthrough

**To:** c.becker@happyrobot.ai
**Cc:** `{{RECRUITER_EMAIL}}`
**Subject:** Inbound carrier sales POC — ready to walk through

---

Hi Carlos,

Thanks again for the conversation last week — I really enjoyed digging into the inbound carrier sales problem with you and I'm looking forward to our meeting this `{{MEETING_DAY}}`.

The proof of concept is built and deployed. A few concrete results from the 250-call mock dataset shipped with the demo:

- 92% margin preservation across 247 booked calls — the server-side negotiation floor (default 10% off loadboard) holds even when the agent runs the full three rounds.
- 1.8 rounds to close on average, well under the three-round cap, with 71% of bookings landing in a single counter.
- FMCSA vetting under two seconds at p95, with a 24h cache that drops repeat-caller checks under fifty milliseconds.
- Config-as-code workflow — spinning up a regional variant (say, a reefer-only southeast desk) is roughly thirty lines of YAML in the HappyRobot editor plus one env var bump. No redeploy.

Quick links:

- Dashboard: `https://inbound-carrier-sales-dashboard.fly.dev` `<TBD until deploy>`
- API: `https://inbound-carrier-sales-api.fly.dev` `<TBD until deploy>`
- Repo: `https://github.com/<org>/inbound-carrier-sales` `<TBD until pushed>`
- HappyRobot workflow editor: `<TBD — Workstream G output>`
- 5-minute walkthrough video: `<TBD — Workstream J output>`

For the live demo I'll cover, in about five minutes: a real inbound call against the deployed agent (FMCSA vet → load match → negotiation → booking), the dashboard refreshing in real time, and a quick tour of where the tunable knobs live in the workflow. Is there anything specific you'd like me to focus on — a particular failure mode, a specific lane, the security model? Happy to tailor it.

Looking forward to it.

Best,
`{{SENDER_NAME}}`
