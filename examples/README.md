# examples

- `make_demo.py` — regenerates everything below; also the **reference for building
  graphs programmatically** (the same core API the GUI will drive).
- `workflows/edges_demo.cvflow.json` — load → gray → blur → canny → save. Run it:

  ```powershell
  .venv\Scripts\cvflow.exe run examples\workflows\edges_demo.cvflow.json --profile
  ```

- `assets/sample.png` — generated synthetic test image (shapes on black). **Tracked
  in git** despite being regenerable: 4 KB, and it makes a fresh clone runnable
  without running `make_demo.py` first.
- `out/` — created by running the demo; **gitignored**, since it is sink output.
  Nothing needs to pre-create it: `Save Image` makes its own parent directories.

Paths inside the workflow are relative to the workflow file's folder (`../assets/...`),
demonstrating the portable-asset rule from docs/06.
