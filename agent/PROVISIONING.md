# HappyRobot Workflow Provisioning

The Inbound Carrier Sales workflow is **defined as code** under this directory:

- [`config.yaml`](./config.yaml) — agent persona, voice, model, transcriber, keyterms, call limits.
- [`prompts/system_prompt.md`](./prompts/system_prompt.md) — full system prompt for Riley.
- [`tools/*.json`](./tools/) — function/parameter schemas for the 4 tools the agent can call.
- [`workflows/inbound_carrier_sales.json`](./workflows/inbound_carrier_sales.json) — snapshot of the live workflow with persistent node IDs and version history.

The live workflow currently runs at:

> **https://api.platform.happyrobot.ai/fdeharrysoiland/workflow/l52g564dq2gf/editor/ef75jglyg906**

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

| Version | ID | Note |
|---|---|---|
| 1 | `019e1f1e-937d-790c-af26-12f2de41f33b` | Initial workflow via MCP. Webhook URLs placeholder. |
| 2 | `019e2088-a90a-7c2d-a22a-1a3902c243a4` | Webhook `X-API-Key` headers updated to deployed `API_KEY`. |
| 3 | `019e2484-8bc4-70e0-b69c-9afb3cb536d0` | Added transcriber (Deepgram Nova 3 Multilingual), `enable_denoised_stt`, and freight `keyterms`. STT now works. |

## What lives in the snapshot vs the YAML

| Concern | File |
|---|---|
| Workflow DAG, persistent IDs, version history | `workflows/inbound_carrier_sales.json` |
| Agent persona + style + flow | `prompts/system_prompt.md` |
| Voice / model / transcriber / keyterms / call limits | `config.yaml` |
| Tool function schemas (name, description, parameters) | `tools/*.json` |
| Provisioning recipe & MCP commands | This file |

If you change any of the above, also update `workflows/inbound_carrier_sales.json` so the snapshot reflects the live state.
