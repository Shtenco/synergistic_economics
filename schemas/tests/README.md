# Schema validation tests

Run from the repository root:

```bash
python -m pip install -r schemas/requirements-dev.txt
python -m unittest discover -s schemas/tests -v
```

The tests check Draft 2020-12 meta-schema validity, all included example records, rejection of undeclared fields, rejection of negative SCI scores and rejection of unknown record types. They validate structure only; cross-record references, accounting balance, legal claims and evidence authenticity remain application-level responsibilities.
