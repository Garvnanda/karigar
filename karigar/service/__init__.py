"""Phase 7 service: Karigar as an OpenAI-compatible endpoint with a Blender worker.

- core.py    KarigarService, the transport-free core (queue, conversations, replies)
- http.py    HTTP adapters: /v1 (OpenAI-compatible, also /sakhi/v1 and /karigar/v1), /api, /worker, /files
- worker.py  the Blender worker: polls the service, runs the Orchestrator, uploads results
- jobs.py    the service's SQLite store (jobs, messages, files)
- convo.py   conversation and idempotency keys from chat history
- replies.py chat reply text, code only

The service side (core, http, jobs, convo, replies) is stdlib only: no bpy, pydantic or LLM.
"""
