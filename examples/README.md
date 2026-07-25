# examples

- `make_demo.py` — regenerates everything below; also the **reference for building
  graphs programmatically** (the same core API the GUI will drive).
- `workflows/edges_demo.cvflow.json` — load → gray → blur → canny → save. Run it:

  ```powershell
  .venv\Scripts\cvflow.exe run examples\workflows\edges_demo.cvflow.json --profile
  ```

- `assets/sample.png` — generated synthetic test image (shapes on black).
- `out/` — created by running the demo (git-ignorable output).

Paths inside the workflow are relative to the workflow file's folder (`../assets/...`),
demonstrating the portable-asset rule from docs/06.
