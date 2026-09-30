# Agent setup and verification

Configured on 2026-09-19 in the existing Geo Trace vault.

## Installed components
- Agent Client 0.13.0 (already installed before this setup)
- Claude ACP adapter 0.79.0; existing Claude Code CLI reports signed in
- Codex ACP adapter 1.12.0; Codex CLI 0.155.1 reports signed in with ChatGPT
- Gemini CLI 0.60.0; no saved Gemini configuration or OAuth file found
- Runtime directory: `/Users/riteshbhardwaj/Documents/Codex/GeoTrace-Agent-Runtime`
- Node: `/opt/homebrew/bin/node`

Agent Client uses absolute executable paths. No API keys were entered or copied. Permission prompts remain enabled. Only Claude, Codex, and Gemini presets are enabled in its settings.

## Verification status
- All configured executable paths exist.
- Existing Markdown notes are unchanged, verified by SHA-256 comparison.
- Shared context and provider entry files exist and were read by the setup agent.
- Claude, Codex, Gemini end-to-end context reads: pending.
- Agent Client was disabled for reload; re-enabling is awaiting user approval required by automatic approval review.

## Use after activation
Open the command palette → **Agent Client: Open chat view**. Choose an agent. For the first check send:

> Read AGENTS.md and 00-Project/CONTEXT.md from this vault. Return the exact workspace verification marker and the current implementation modules. Do not edit files or start login.

Expected marker: `GEOTRACE-SHARED-CONTEXT-20260919`.

Start ordinary work with [[HOME]]. Keep separate handoffs in [[CLAUDE]], [[CODEX]], and [[GEMINI]]. Export useful conversations into `03-Agent-Notes/Chats`.

## Authentication
Ask the user before login or any credential/API-key step. Enter any approved key directly in Obsidian Keychain, never in these notes or chat. Existing sign-in status does not by itself verify subscription access or available quota.

## References
- [Agent Client documentation](https://rait-09.github.io/obsidian-agent-client/)
- [Claude setup](https://rait-09.github.io/obsidian-agent-client/agent-setup/claude-code.html)
- [Codex setup](https://rait-09.github.io/obsidian-agent-client/agent-setup/codex.html)
- [Gemini setup](https://rait-09.github.io/obsidian-agent-client/agent-setup/gemini-cli.html)
