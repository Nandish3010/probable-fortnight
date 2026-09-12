# Voice session (documented stub)

The phone view's microphone opens a Gemini Live session (model id `live` in `config/models.toml`)
scoped to Kutumb Mart operations with four tools: `get_gaps(node_id)`, `explain_play(play_id)`,
`approve_play(play_id)`, `ask_confirmation(question)`. Language: Kannada with English fallback.

Status: not wired in this build. `live.py` holds the session configuration (system instruction,
tool declarations, language settings) so the week-3 owner can connect it to the Live API without
touching the phone view. The video records the voice beat; the finale uses it live only if the
week-3 rehearsals pass on hotel-grade wifi (DECISIONS §5.1, §15 cut order).
