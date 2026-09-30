# Local India place-name index

Build the local index from the repository root:

```sh
.venv/bin/python backend/cyber/build_india_gazetteer.py
```

The generated archive and SQLite database are intentionally excluded from Git.
Source: [GeoNames India dump](https://download.geonames.org/export/dump/IN.zip).
GeoNames data is licensed under Creative Commons Attribution 4.0. The data is
provided as-is and place mentions must be corroborated before use.
