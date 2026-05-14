# HappyRobot Workflow Provisioning

The Inbound Carrier Sales workflow is **defined as code** under this directory:

- [`config.yaml`](./config.yaml) — agent persona, voice, model, transcriber, keyterms, call limits.
- [`prompts/system_prompt.md`](./prompts/system_prompt.md) — full system prompt for Riley.
- [`tools/*.json`](./tools/) — function/parameter schemas for the 4 tools the agent can call.
- [`workflows/inbound_carrier_sales.json`](./workflows/inbound_carrier_sales.json) — snapshot of the live workflow with persistent node IDs and version history.

The live workflow currently runs at:

> **https://api.platform.happyrobot.ai/fdeharrysoiland/workflow/hhh9hxa9j8cr/editor/a4x4ob8nxxxm**

## How the workflow was built

Workflow creation, node configuration, version forking, and publish are done through the **HappyRobot Workflows MCP server** (`https://mcp.platform.happyrobot.ai/workflows/mcp`). The MCP tools wrap HR's REST API and handle the rich-text/Plate JSON conversions for prompts, headers, and webhook body templates. Direct REST calls require the same node-ID and Plate-paragraph mechanics; the public REST surface for arbitrary node-level config edits is not yet documented, so we standardise on MCP for provisioning.

To recreate or modify the workflow you need:

1. A HappyRobot organisation with the **HappyRobot platform API key** (`HAPPYROBOT_API_KEY`).
2. The MCP server connected to that org. With Claude Code:
   ```bash
   claude mcp add --transport http happyrobot-workflows https://mcp.platform.happyrobot.ai/workflows/mcp
   ```
   Then run `/mcp` inside Claude Code to complete the OAuth flow.

## Provisioning from scratch (new HR org)

The high-level pattern, each step is one MCP tool call:

1. `mcp__happyrobot-workflows__create_workflow` — pass `name: "Inbound Carrier Sales"` and the full `nodes` array. The DAG to recreate is documented in [`workflows/inbound_carrier_sales.json`](./workflows/inbound_carrier_sales.json) under `trigger`, `tools`, and `post_call`. The exact node definitions used in v1 are in this repo's git history (see commit `9fc0ce1`).

   Key things to set on the agent node:
   - `event_id`: `0192e5dc-08df-78bf-a549-f43c6bf9f087` (Inbound Voice Agent)
   - `agent.voices[]`: must be `templated_value` objects: `{"type":"static","static":{"id":..., "name":...}}`
   - `agent.languages[]`: same templated-value shape
   - `transcriber`: `{"id":"deepgram-nova-3-multi","name":"Deepgram Nova 3 Multilingual"}` — **required for STT**, without it the agent will speak but never hear the caller
   - `enable_denoised_stt`: `true`
   - `keyterms`: list from `config.yaml`
   - `prompt.prompt_md`: load from `prompts/system_prompt.md`
   - `prompt.initial_message`: from `config.yaml`
   - `prompt.model`: `{"type":"static","static":{"id":"gpt-5.1-instant","name":"gpt-5.1-instant"}}`

2. After create returns, use `mcp__happyrobot-workflows__get_workflow_details` with `include_nodes=true` to capture the new persistent_ids. Save them to `workflows/inbound_carrier_sales.json`.

3. The trigger may auto-create without `room_name` in its `params` — add it via `mcp__happyrobot-workflows__update_workflow_nodes`:
   ```
   action: update
   node_id: <trigger node id>
   updates: {"configuration": {"params": ["call_id", "carrier_phone", "room_name"]}}
   ```

4. `mcp__happyrobot-workflows__test_workflow action=test_all` — webhook actions will fail with DNS errors until the API is deployed; that's expected.

5. `mcp__happyrobot-workflows__manage_versions action=publish environment=production`.

## Updating the live workflow

Live versions are **locked**. To make changes you must fork → edit → publish. The flow:

1. `manage_versions action=fork version_id=<current_live_version_id>` → returns a new editable draft version_id.
2. `get_workflow_details include_nodes=true version_id=<new_version_id>` → maps persistent_ids to the fork's new node_ids.
3. For each node you want to change, `get_node_details` (because `configuration` is a FULL REPLACE on update), modify, then `update_workflow_nodes action=update`.
4. `manage_versions action=publish environment=production force=true` — the `force=true` automatically unpublishes the prior live version.
5. Update `workflows/inbound_carrier_sales.json` so `current_live_version_id` reflects the new version and append a `version_history` entry.

## Re-pointing webhook URLs after API redeploys

If the deployed API URL or `API_KEY` rotates, the four webhook actions need to be updated. The standalone Python script [`scripts/setup_happyrobot.py`](../scripts/setup_happyrobot.py) is the long-running re-point tool. It currently targets the unauthenticated REST path used by the MCP server; if HR ever publishes the canonical REST surface, that script can call it directly. Until then, run the MCP version manually (the four `update_workflow_nodes` calls patching each webhook's `headers[].X-API-Key.value` and `url`).

A reproducer of the v1→v2 webhook re-point (full Plate JSON for each of the four actions) lives in git history at commit `c3bd0c5`'s `scripts/setup_happyrobot.py`, and the v3 STT-config change is in commit `<this>`.

## Version history

The live workflow is **`Inbound Carrier Sales`** (workflow_id `019e24c6-a691-74bf-bc63-4104aefebb7e`, slug `k4ecerqo7z1i`). It replaces an earlier workflow that was deleted during the trigger-swap rollback below.

| Phase | Version / Workflow | Note |
|---|---|---|
| Original | `Inbound Carrier Sales` v1 (deleted) | First workflow via MCP. Predefined Webhook trigger; webhook URLs placeholder. |
| Original v2 | (deleted) | Webhook `X-API-Key` headers updated to deployed `API_KEY`. |
| Original v3 | (deleted) | Added Deepgram Nova 3 transcriber, `enable_denoised_stt`, freight `keyterms`. |
| Original v4 attempt | (deleted) | Tried to in-place swap trigger to Inbound Phone. `update_workflow_nodes` silently kept `event_id` — trigger config shape changed but type didn't. Rolled back. |
| `Inbound Carrier Sales (Phone)` | (deleted) | Fresh workflow with Inbound Phone trigger + Onboarding number. Publish blocked by a stuck platform-side `Dispatch rules conflict for numbers +16282142490` (HTTP 500) that requires HR support to clear. Couldn't proceed programmatically. |
| **Current — `Inbound Carrier Sales` v1** | `019e24c6-a69b-7d4c-9c71-e8b2906e8379` | Predefined Webhook trigger (`b329e750-...`) with `call_id`, `carrier_phone`, `room_name` params. HR's "Web Call" test in the editor populates `room_name` so the agent has a valid audio source. STT fully wired. End-to-end works for the web-call demo path. |

## Critical: which voice agent event to use

HappyRobot exposes two voice-agent event types: **Inbound Voice Agent** (`0192e5dc-08df-78bf-a549-f43c6bf9f087`) and **Outbound Voice Agent** (`0192e5dc-090a-7f57-87a0-76308ed6ef28`). The name strongly suggests you'd use the Inbound one for an inbound carrier sales agent. **You'd be wrong.**

For HappyRobot's **Web Call Test** flow (browser-initiated test calls from the editor) the working pattern — and the one HR's own Voice Agent template uses — is:

- **Trigger:** Predefined Webhook (`b329e750-...`) with params `["call_id", "carrier_phone", "room_name"]`.
- **Agent:** **Outbound** Voice Agent with `from_number` set to one of the org's phone numbers (the Onboarding +1 number works out of the box because it has an Outbound Trunk).
- The editor's Test button replaces the actual outbound dial with a browser audio session. Riley speaks, hears, and the tool flow runs.

Using the **Inbound** Voice Agent in a webhook-triggered workflow looks plausible (agent boots, validates) but ends in silence on the browser test — there's no inbound audio path because the Predefined Webhook trigger isn't a call source. Trying to fix that by swapping the trigger to **Inbound Phone** (`0192a20c-...`) ran into dispatch-rule conflicts on first publish that need HR support to clear (see the `Dispatch claim stickiness` gotcha below).

## Gotchas surfaced during build

1. **Trigger `event_id` is immutable through `update_workflow_nodes`.** The API returns "Updated fields: event_id" but the persistence layer doesn't actually change it. To switch trigger types you must create a new workflow (no fork-and-swap path). Add a regression check or wait for HR to surface this in the public API.
2. **Inbound Phone trigger + dispatch rules can lock a number to a deleted workflow.** Once a number was claimed in some prior state, even after `manage_workflow action=delete` of the claiming workflow + `manage_versions action=unpublish` on all visible candidates, the dispatch rules don't clear. HR support is the unblock.
3. **`agent.voices[]` / `agent.languages[]` must be templated-value objects** (`{type: "static", static: {id, name}}`), not bare strings. First publish attempt failed on this.
4. **`numbers[]` on Inbound Phone trigger expects `{id, name, number}` plain objects**, not templated_value. Different schema shape than voices/languages.
5. **AI Extract output references** must use `response.` prefix at runtime: `{{<extract_pid>.response.carrier_mc}}`.
6. **`configuration` is a FULL REPLACE on update** — always `get_node_details` first, mutate, send the complete object back. Sending partial wipes everything else.
7. **Inbound voice agents need a `transcriber`** — without one, the agent will TTS (speak) but never STT (hear). Default is **not** auto-set, which was the v3 fix in the original workflow.
8. **Web Call test in HR's editor** works against any trigger that provides a `room_name` to the inbound voice agent. The Predefined Webhook trigger satisfies this when `room_name` is in `configuration.params`. The "no node selected for inbound calls" editor warning is a yellow hint, not a functional blocker for web-call testing.

## What lives in the snapshot vs the YAML

| Concern | File |
|---|---|
| Workflow DAG, persistent IDs, version history | `workflows/inbound_carrier_sales.json` |
| Agent persona + style + flow | `prompts/system_prompt.md` |
| Voice / model / transcriber / keyterms / call limits | `config.yaml` |
| Tool function schemas (name, description, parameters) | `tools/*.json` |
| Provisioning recipe & MCP commands | This file |

If you change any of the above, also update `workflows/inbound_carrier_sales.json` so the snapshot reflects the live state.
