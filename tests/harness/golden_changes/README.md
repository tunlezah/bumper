# Deliberate behaviour changes

One JSON file per golden whose expected behaviour changed on purpose, at the
same relative path as the legacy golden in `../golden/`:

```json
{"changes": ["C-00N"], "reason": "...", "expected": { ... }}
```

`changes` refer to entries in `docs/modernisation/CHANGES.md`; `../test_golden_changes.py` checks that every difference from the legacy golden is explained by them. See
`../README.md` for how the profiles use these files.
