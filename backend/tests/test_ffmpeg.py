"""3b.1：ffmpeg 可从样例视频导出 jpg 帧。"""

from pathlib import Path

from app.media.ffmpeg import (
    extract_frames_stride,
    make_sample_video,
    probe_video,
)


def test_ffmpeg_extract_jpg_from_sample(tmp_path: Path) -> None:
    video = make_sample_video(tmp_path / "sample.mp4", seconds=1.0, fps=10)
    meta = probe_video(video)
    assert meta.width == 320
    assert meta.height == 240
    assert meta.fps > 0

    out = tmp_path / "frames"
    frames = extract_frames_stride(video, stride=5, out_dir=out, max_frames=5)
    assert len(frames) >= 1
    assert frames[0].path.suffix.lower() == ".jpg"
    assert frames[0].path.is_file()
    assert frames[0].path.stat().st_size > 0
    assert frames[0].frame_index == 0
