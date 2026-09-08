# dev/ — throwaway diagnostics

One-off scripts used while building the CLI. **Not part of the package, not imported by
anything, not maintained.** Hardcoded course IDs and local paths. Kept only as reference.

| file | what it did |
|---|---|
| `probe_drive.py` / `probe_drive2.py` | diagnose `403` on Drive attachments in Classroom submissions |
| `extract_rars.py` | manual `.rar` extraction via WinRAR before `classroom_tool/extract.py` existed |
| `dump_extracted.py` | dump extracted student code files to stdout for eyeballing |
| `stale_doctor_root_copy.py` | dead duplicate of `classroom_tool/doctor.py` (has package-relative imports, can't run standalone) — the live one is `classroom_tool/doctor.py`, used by `cli.py` |

If you need a real dev tool, add it to the `classroom_tool` package or `tools/` instead.
