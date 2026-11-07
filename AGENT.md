# RefCanvas agent instructions

- Do not create tests or test harnesses.
- Do not run tests; the user validates behaviour manually in Painter.
- After every code change, build and install automatically from `sp-refcanvas`:
  `call .\build_install.bat --no-pause`.
- If the plugin copy fails because Painter is running, leave the build in place and tell the user to restart Painter; do not kill Painter.
- Keep every docstring and comment to one line.
- Keep modules under 1000 lines; add focused modules instead of growing one file.
- Prefer PySide6 and the documented `substance_painter.ui` API only.
- Runtime Python modules live in `src/`; `build_install.bat` stages them into `plugins/refcanvas_plugin` and copies them into Painter's `python\plugins\refcanvas_plugin`.
- Primary future use is color picking from reference layers and collage images, not painting.
