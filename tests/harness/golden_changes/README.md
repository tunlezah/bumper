# Deliberate behaviour changes

One JSON file per golden whose expected behaviour changed on purpose, at the
same relative path as the legacy golden in `../golden/`:

```json
{"change": "C-00N", "reason": "...", "expected": { ... }}
```

`change` refers to an entry in `docs/modernisation/CHANGES.md`. See
`../README.md` for how the profiles use these files.
