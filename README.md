# dcmassist

**Turn an existing Snowflake database into a [DCM project](https://docs.snowflake.com/en/user-guide/dcm-projects/dcm-projects-overview) in seconds.**

You've decided to manage your Snowflake schema with Declarative Change Management. Now you need a `DEFINE TABLE …` block for every table, view, schema, stage, sequence, file format, and tag you already have. Hand-writing thousands of these is the wrong way to start.

Point `dcmassist` at your database and it produces a complete, ready-to-commit DCM project — `manifest.yml`, `Makefile`, definitions, optional macros, the lot.

```bash
uvx dcmassist export --database MYDB --out-folder ./my-dcm-project
```

That's it. Commit, deploy, done.

## Why dcmassist

- **Zero-to-DCM in one command.** No bespoke scripts, no copy-pasting from `GET_DDL`, no fixing up identifier quoting by hand.
- **Multi-environment from day one.** Database names are templated to `{{ database }}` automatically, so the same project deploys to dev, staging, and prod.
- **Safe with secrets.** Stage definitions are synthesized without credentials — credentials live on storage integrations, not in git. You won't accidentally commit AWS keys.
- **Built for real Snowflake accounts.** Paginates `SHOW` past the 10K-row cap. Quotes identifiers properly so leading-digit and lowercase names survive. Skips objects your role can't see instead of failing the run.
- **Predictable output.** Per-type files, deterministic ordering, automatic chunking when a type grows beyond a threshold. Diffs stay readable as your project evolves.
- **Optional Jinja macros.** With `--use-macros`, every definition is a one-line macro invocation, so a column rename touches one file instead of hundreds.
- **Observable runs.** Live status panel while it works; a per-run log file you can tail when something looks wrong.

## What you get

```
my-dcm-project/
├── manifest.yml                # targets, configurations, templating defaults
├── Makefile                    # deploy, plan, sync, validate
├── dcmassist-export.log        # per-run log of options + per-object results
└── sources/
    ├── definitions/
    │   ├── schema.sql          # one file per type
    │   ├── table.sql           # auto-chunked into table2.sql, table3.sql … past the threshold
    │   ├── view.sql
    │   ├── sequence.sql
    │   ├── stage.sql           # synthesized — no credentials
    │   ├── file_format.sql
    │   └── tag.sql
    └── macros/                 # only with --use-macros
        └── <type>.sql
```

## Run

Requires Python ≥ 3.10, [`uv`](https://docs.astral.sh/uv/), and a configured [`snow` CLI](https://docs.snowflake.com/en/developer-guide/snowflake-cli/index) connection.

`dcmassist` is a one-shot tool — you run it when you need a DCM project and rarely after that. The simplest way is `uvx`, which fetches and runs without a permanent install:

```bash
uvx dcmassist export --database MYDB
```

Pin a version for reproducibility:

```bash
uvx dcmassist@0.1.15 export --database MYDB
```

If you'd rather keep it installed:

```bash
uv tool install dcmassist
# or
pipx install dcmassist
```

## Quick examples

The examples below use `uvx`; substitute `dcmassist` if you've installed it.

Just tables and views from one schema, with macros, into a custom folder:

```bash
uvx dcmassist export \
    --database MYDB \
    --schema PUBLIC \
    --include Table --include View \
    --use-macros \
    --out-folder ./project
```

Multi-environment manifest with templated configurations:

```bash
uvx dcmassist export \
    --database MYDB \
    --target dev --target prod \
    --configuration STAGING \
    --templating-default warehouse=COMPUTE_WH
```

Run `uvx dcmassist export --help` for every option.

## Type support

**Implemented:** Schema, Table, View, Sequence, Stage, File format, Tag.

**Recognized but not yet exported:** Dynamic table, Task, Alert, SQL function, Data metric function, SQL procedure, Role, Database role, Grant, Authentication policy. Including these in `--include` is accepted (they pass validation) but they produce no output yet — contributions welcome.

`Database` is intentionally never exported: DCM rejects `DEFINE DATABASE` for the project's own parent database.

## Configuration

| Environment variable | Effect |
|----------------------|--------|
| `DCMASSIST_EXPORT_OBJECTS_PER_FILE` | Max objects per chunked SQL file (default: 100). Lower it if your DDL files grow uncomfortably large. |
| `DCMASSIST_NO_STATUS=1` | Disable the live status panel (also auto-disabled on non-TTY and `NO_COLOR=1`). |

| Exit code | Meaning |
|-----------|---------|
| `0` | Success |
| `4` | Ran to completion but exported nothing — every object failed (typically permission errors) |
| `5` | Setup error — bad env var, or non-empty output folder without `--force` |

## Project status

Pre-1.0. The output layout, CLI flags, and log format are stable enough to use; expect breaking changes between minor versions until 1.0. Issues and pull requests welcome at [github.com/jamiekt/dcmassist](https://github.com/jamiekt/dcmassist).

## License

MIT.
