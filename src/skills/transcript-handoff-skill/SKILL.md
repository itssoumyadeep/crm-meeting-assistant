---
name: transcript-handoff-skill
description: Guidance for turning raw meeting transcripts into clean executive summaries, action items, and follow-up tasks.
---

# Transcript Handoff Skill

This skill tells the transcript analysis agent how to convert an unstructured meeting transcript into a clean handoff for downstream CRM workflows.

## Goals

- Summarize the meeting in plain business language.
- Extract only concrete action items and follow-up tasks.
- Keep the output concise, grounded in the transcript, and ready for downstream agents.

## Rules

- Prefer evidence-backed statements over speculation.
- Keep action items specific and actionable.
- Separate what was discussed from what should happen next.
- Avoid duplicate or vague follow-up items.

## Output Expectations

- Executive summary: 3–5 sentences.
- Action items: short list of clear commitments.
- Follow-up tasks: short list of next steps for the sales team.
