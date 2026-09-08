# State Files

The scheduled scan workflow appends durable records here.

- `jobs.jsonl` stores scored candidate snapshots.
- `applications.jsonl` stores explicit PREPARE/application state transitions.
- `contacts.jsonl` stores manually discovered/public human-path records.
- `events.jsonl` stores important pipeline transitions.
- `runtime/` is ignored and used for local indexes, temporary references and test scratch data.

