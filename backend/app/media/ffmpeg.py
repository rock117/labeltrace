"""ffmpeg / ffprobe 封装：元数据与抽帧。失败必须抛错并带日志，禁止静默。"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.core.errors import ValidationAppError
from app.core.logging import get_logger

logger = get_logger("labeltrace.ffmpeg")


@dataclass(frozen=True)
class VideoMeta:
    duration_ms: int
    fps: float
    width: int
    height: int
    nb_frames: int | None


@dataclass(frozen=True)
class ExtractedFrame:
    frame_index: int
    time_ms: int
    path: Path


def _bin(name: str) -> str:
    path = shutil.which(name)
    if not path:
        logger.error("ffmpeg_binary_missing name=%s", name)
        raise RuntimeError(f"未找到 {name}，请安装并加入 PATH")
    return path


def probe_video(path: Path) -> VideoMeta:
    """用 ffprobe 读取时长/fps/分辨率。"""
    ffprobe = _bin("ffprobe")
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,r_frame_rate,nb_frames,avg_frame_rate:format=duration",
        "-of",
        "json",
        str(path),
    ]
    logger.info("ffprobe_start path=%s", path.name)
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, check=False, timeout=120
        )
    except subprocess.TimeoutExpired as exc:
        logger.exception("ffprobe_timeout path=%s", path)
        raise RuntimeError("ffprobe 超时") from exc
    if proc.returncode != 0:
        logger.error(
            "ffprobe_failed code=%s stderr=%s",
            proc.returncode,
            (proc.stderr or "")[:500],
        )
        raise ValidationAppError("无法解析视频元数据")
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        logger.exception("ffprobe_json_invalid")
        raise RuntimeError("ffprobe 输出无效") from exc

    streams = data.get("streams") or []
    if not streams:
        raise ValidationAppError("视频无视频流")
    stream = streams[0]
    fmt = data.get("format") or {}
    width = int(stream.get("width") or 0)
    height = int(stream.get("height") or 0)
    duration_s = float(fmt.get("duration") or 0)
    rate = stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "0/1"
    fps = _parse_rate(rate)
    nb_raw = stream.get("nb_frames")
    nb_frames = int(nb_raw) if nb_raw and str(nb_raw).isdigit() else None
    if width <= 0 or height <= 0:
        raise ValidationAppError("视频分辨率无效")
    meta = VideoMeta(
        duration_ms=max(0, int(duration_s * 1000)),
        fps=fps,
        width=width,
        height=height,
        nb_frames=nb_frames,
    )
    logger.info(
        "ffprobe_ok duration_ms=%s fps=%s %sx%s nb_frames=%s",
        meta.duration_ms,
        meta.fps,
        meta.width,
        meta.height,
        meta.nb_frames,
    )
    return meta


def _parse_rate(rate: str) -> float:
    if "/" in rate:
        num, den = rate.split("/", 1)
        try:
            n, d = float(num), float(den)
            return n / d if d else 0.0
        except ValueError:
            return 0.0
    try:
        return float(rate)
    except ValueError:
        return 0.0


def extract_frames_stride(
    video_path: Path,
    *,
    stride: int,
    out_dir: Path,
    max_frames: int | None = None,
) -> list[ExtractedFrame]:
    """每隔 stride 帧导出一张 jpg（select=not(mod(n\\,stride))）。"""
    if stride < 1:
        raise ValidationAppError("stride 必须 >= 1")
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = probe_video(video_path)
    ffmpeg = _bin("ffmpeg")
    pattern = str(out_dir / "frame_%06d.jpg")
    # fps filter: 每 stride 帧取一帧 ≈ fps/stride
    vf = f"select='not(mod(n\\,{stride}))',setpts=N/FRAME_RATE/TB"
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(video_path),
        "-vf",
        vf,
        "-vsync",
        "vfr",
        "-q:v",
        "2",
        pattern,
    ]
    if max_frames is not None and max_frames > 0:
        cmd = cmd[:-1] + ["-frames:v", str(max_frames), pattern]

    logger.info(
        "ffmpeg_extract_start stride=%s max_frames=%s out=%s",
        stride,
        max_frames,
        out_dir,
    )
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, check=False, timeout=600
        )
    except subprocess.TimeoutExpired as exc:
        logger.exception("ffmpeg_extract_timeout")
        raise RuntimeError("ffmpeg 抽帧超时") from exc
    if proc.returncode != 0:
        logger.error(
            "ffmpeg_extract_failed code=%s stderr=%s",
            proc.returncode,
            (proc.stderr or "")[:800],
        )
        raise RuntimeError("ffmpeg 抽帧失败")

    files = sorted(out_dir.glob("frame_*.jpg"))
    results: list[ExtractedFrame] = []
    for i, fp in enumerate(files):
        frame_index = i * stride
        time_ms = int(frame_index / meta.fps * 1000) if meta.fps > 0 else 0
        results.append(
            ExtractedFrame(frame_index=frame_index, time_ms=time_ms, path=fp)
        )
    logger.info("ffmpeg_extract_ok count=%s", len(results))
    return results


def extract_frames_interval_ms(
    video_path: Path,
    *,
    interval_ms: int,
    out_dir: Path,
    max_frames: int | None = None,
) -> list[ExtractedFrame]:
    """按时间间隔抽帧。"""
    if interval_ms < 1:
        raise ValidationAppError("interval_ms 必须 >= 1")
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = probe_video(video_path)
    fps_out = 1000.0 / interval_ms
    ffmpeg = _bin("ffmpeg")
    pattern = str(out_dir / "frame_%06d.jpg")
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(video_path),
        "-vf",
        f"fps={fps_out}",
        "-q:v",
        "2",
        pattern,
    ]
    if max_frames is not None and max_frames > 0:
        cmd = cmd[:-1] + ["-frames:v", str(max_frames), pattern]

    logger.info(
        "ffmpeg_extract_interval_start interval_ms=%s max_frames=%s",
        interval_ms,
        max_frames,
    )
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, check=False, timeout=600
        )
    except subprocess.TimeoutExpired as exc:
        logger.exception("ffmpeg_extract_timeout")
        raise RuntimeError("ffmpeg 抽帧超时") from exc
    if proc.returncode != 0:
        logger.error(
            "ffmpeg_extract_failed code=%s stderr=%s",
            proc.returncode,
            (proc.stderr or "")[:800],
        )
        raise RuntimeError("ffmpeg 抽帧失败")

    files = sorted(out_dir.glob("frame_*.jpg"))
    results: list[ExtractedFrame] = []
    for i, fp in enumerate(files):
        time_ms = i * interval_ms
        frame_index = int(time_ms / 1000.0 * meta.fps) if meta.fps > 0 else i
        results.append(
            ExtractedFrame(frame_index=frame_index, time_ms=time_ms, path=fp)
        )
    logger.info("ffmpeg_extract_ok count=%s", len(results))
    return results


def extract_poster_frame(
    video_path: Path,
    out_path: Path,
    *,
    at_sec: float = 1.0,
) -> Path:
    """从视频截取一帧 JPG 作为列表缩略图（轻量，非整段解码）。"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = _bin("ffmpeg")
    t = max(0.05, float(at_sec))
    cmd = [
        ffmpeg,
        "-y",
        "-ss",
        f"{t:.3f}",
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        "-q:v",
        "5",
        str(out_path),
    ]
    logger.info("ffmpeg_poster_start at_sec=%s out=%s", t, out_path.name)
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, check=False, timeout=60
        )
    except subprocess.TimeoutExpired as exc:
        logger.exception("ffmpeg_poster_timeout")
        raise RuntimeError("ffmpeg 截取封面超时") from exc
    if proc.returncode != 0 or not out_path.is_file():
        # 片头黑场或 seek 失败时退回第 0 帧
        cmd0 = [
            ffmpeg,
            "-y",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-q:v",
            "5",
            str(out_path),
        ]
        proc0 = subprocess.run(
            cmd0, capture_output=True, text=True, check=False, timeout=60
        )
        if proc0.returncode != 0 or not out_path.is_file():
            logger.error(
                "ffmpeg_poster_failed stderr=%s",
                (proc.stderr or proc0.stderr or "")[:500],
            )
            raise RuntimeError("ffmpeg 截取封面失败")
    logger.info("ffmpeg_poster_ok path=%s size=%s", out_path.name, out_path.stat().st_size)
    return out_path


def make_sample_video(path: Path, *, seconds: float = 1.0, fps: int = 10) -> Path:
    """生成测试用纯色视频（依赖 ffmpeg）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = _bin("ffmpeg")
    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=blue:s=320x240:d={seconds}",
        "-r",
        str(fps),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=60)
    if proc.returncode != 0 or not path.is_file():
        logger.error("sample_video_failed stderr=%s", (proc.stderr or "")[:500])
        raise RuntimeError("无法生成样例视频")
    return path


def write_bytes_to_temp(data: bytes, suffix: str) -> Path:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(data)
    tmp.close()
    return Path(tmp.name)
