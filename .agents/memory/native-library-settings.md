---
name: Imported native library settings
description: Why startup commands clear the imported native-library override.
---
The imported Nix configuration overrides LD_LIBRARY_PATH with older native libraries. Do not assume this override is compatible with Replit's managed runtimes.

**Why:** Node 22 failed with a missing CXXABI_1.3.15 symbol from ICU when loading the older C++ runtime. Clearing the override allowed Node and Python's ONNX, OpenCV, and PDFium imports to work.

**How to apply:** Preserve the cleared-library-path startup wrapper unless the underlying native-library configuration is explicitly repaired and both Node and Python native imports are verified.
