---
name: image-overlay
description: How images reach the user in this omp-inside-nvim setup — tool-result images auto-overlay bottom-left via omp-img-overlay; herdr-img displays an image on demand. Read when showing an image or debugging image display.
---

# Image overlay (nvim `:terminal` workaround)

Inline images (tool results containing image blocks — screenshots, diagrams, rendered results) are automatically displayed to the user as an overlay in the bottom-left of the pane by the omp-img-overlay extension. You do not need to do anything for that; just mention what the image shows as usual.

To deliberately put an image in front of the user, run:

    herdr-img <path-to-image>

It overlays the image bottom-left (auto-clears after 12s; `--hold`/`--clear`/`--cols`/`--rows` for control). Only works when the pane is visible in the active herdr tab.

Both mechanisms are a WORKAROUND: this omp runs inside nvim, whose `:terminal` has no image support (nvim limitation, not an omp bug). If nvim ever gains `:terminal` graphics, drop the omp-img-overlay extension and herdr-img.
