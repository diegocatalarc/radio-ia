from pathlib import Path
from types import SimpleNamespace

import pytest

from radio.video.render import VIDEO_DIR, RenderError, render_video


def test_render_video_builds_expected_command(tmp_path):
    seen = {}

    def runner(cmd, **kw):
        seen["cmd"], seen["kw"] = cmd, kw
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    render_video(tmp_path / "props.json", tmp_path, "Semanal16x9", tmp_path / "o.mp4", runner=runner)
    cmd = seen["cmd"]
    assert cmd[:3] == ["npx", "remotion", "render"]
    assert "Semanal16x9" in cmd and str(tmp_path / "o.mp4") in cmd
    assert f"--props={tmp_path / 'props.json'}" in cmd and f"--public-dir={tmp_path}" in cmd
    assert Path(seen["kw"]["cwd"]) == VIDEO_DIR and (VIDEO_DIR / "src" / "index.ts").exists()


def test_render_failure_raises_render_error_with_stderr_tail(tmp_path):
    def runner(cmd, **kw):
        return SimpleNamespace(returncode=1, stdout="", stderr="\n".join(f"linea{i}" for i in range(30)))

    with pytest.raises(RenderError, match="linea29") as e:
        render_video(tmp_path / "p.json", tmp_path, "Semanal9x16", tmp_path / "o.mp4", runner=runner)
    assert "linea0" not in str(e.value)
