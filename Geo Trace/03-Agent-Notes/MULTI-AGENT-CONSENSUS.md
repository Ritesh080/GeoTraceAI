# Multi-agent consensus workflow

Agent Client can broadcast one prompt to several open chat views. Each view is an independent agent process, so consultation happens through shared notes in this vault. Codex is the final coordinator while Claude is unavailable.

## Prepare the views

1. Open one chat view per available agent with **Agent Client: Open new chat view**.
2. In each view, run the matching command: **Switch agent to Codex**, **Switch agent to Gemini CLI**, or **Switch agent to Claude Code**.
3. Keep permission mode on manual/approval. Do not run two agents that edit the same file.

## Round 1 — independent analysis

Type the prompt below in one view, then run **Agent Client: Broadcast prompt** followed by **Agent Client: Broadcast send**.

> Read AGENTS.md, 00-Project/CONTEXT.md, and the relevant project notes. Analyze this task independently: [TASK]. Do not change source code. Write your evidence, proposal, risks, and open questions to your own handoff note under 03-Agent-Notes (CODEX.md, GEMINI.md, or CLAUDE.md). Do not edit another agent's note. End with a concise recommendation.

Wait until every available agent finishes.

## Round 2 — cross-review

Broadcast this prompt to the same views:

> Read the other agents' latest handoffs in 03-Agent-Notes. Check their evidence and assumptions. Update only your own handoff with agreements, disagreements, corrections, and a revised recommendation. Do not change source code.

Wait until every available agent finishes.

## Final synthesis

Send this only to the Codex view:

> Act as the coordinator. Read the latest CODEX.md, GEMINI.md, and CLAUDE.md entries that exist for this task. Produce one final recommendation in 03-Agent-Notes/FINAL.md. Separate agreed facts, chosen approach, unresolved disagreements, risks, and next actions. Do not claim consensus where evidence differs. Do not change source code unless the user separately authorizes implementation.

## Commands

- **Broadcast prompt** copies the active view's draft to all open Agent Client views.
- **Broadcast send** sends the drafts simultaneously.
- **Broadcast cancel** stops active work in all views.
- Add keyboard shortcuts under **Settings → Hotkeys** if you use this often.

This is a staged workflow rather than automatic agent-to-agent chat. The shared Markdown handoffs make every contribution reviewable and prevent hidden coordination.
