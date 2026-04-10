# Log

Append-only record of all wiki operations.
Each entry starts with `## [YYYY-MM-DD] <event_type> | <title>`
so it can be filtered with simple tools:

```
grep "^## \[" wiki/log.md | tail -5
```

