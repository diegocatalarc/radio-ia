"""Render del video con Remotion (``npx remotion render``)."""
from __future__ import annotations

import subprocess
from pathlib import Path

VIDEO_DIR = Path(__file__).resolve().parents[2] / "video"
STDERR_TAIL_LINES = 10


class RenderError(Exception):
    """Remotion terminó con error."""


def render_video(props_path: Path, public_dir: Path, composition: str, out_path: Path,
                 runner=subprocess.run) -> None:
    cmd = ["npx", "remotion", "render", "src/index.ts", composition, str(Path(out_path).resolve()),
           f"--props={Path(props_path).resolve()}", f"--public-dir={Path(public_dir).resolve()}"]
    res = runner(cmd, cwd=VIDEO_DIR, capture_output=True, text=True)
    if res.returncode != 0:
        tail = "\n".join((res.stderr or "").strip().splitlines()[-STDERR_TAIL_LINES:])
        raise RenderError(f"remotion render {composition} falló (código {res.returncode}):\n{tail}")
