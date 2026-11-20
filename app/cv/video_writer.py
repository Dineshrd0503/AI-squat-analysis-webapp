"""Browser-playable video output.

OpenCV's VideoWriter is not suitable for the annotated video:

* its default codec is MPEG-4 Part 2 (`mp4v`), which Chrome, Firefox and
  Edge refuse to decode, so the file downloads but will not play inline;
* it writes the `moov` atom at the *end* of the file, so a browser has to
  download the entire file before it can start playing.

So frames are piped into a real ffmpeg and encoded to H.264 with
``yuv420p`` (what Safari and every mobile browser expect) and
``+faststart`` (so the index sits at the front and playback starts
immediately). If ffmpeg is unavailable we fall back to OpenCV's H.264
writer, which at least produces a decodable file.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Optional, Tuple

import cv2
import numpy as np


def _ffmpeg_exe() -> Optional[str]:
    """Locate an ffmpeg binary: on PATH, or bundled with imageio-ffmpeg."""
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        return exe if exe and os.path.exists(exe) else None
    except Exception:
        return None


class FfmpegWriter:
    """Writes raw BGR frames to an H.264 MP4 with faststart."""

    def __init__(self, path: str, fps: float, size: Tuple[int, int], crf: int = 24):
        exe = _ffmpeg_exe()
        if not exe:
            raise RuntimeError("ffmpeg not available")
        self.path = path
        self.width = int(size[0]) // 2 * 2
        self.height = int(size[1]) // 2 * 2
        cmd = [
            exe, "-y", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "bgr24",
            "-s", f"{self.width}x{self.height}",
            "-r", f"{fps:.6f}", "-i", "-",
            "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf),
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            path,
        ]
        self.proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE)
        self._failed = False

    def write(self, frame: np.ndarray) -> None:
        if self._failed:
            return
        try:
            if frame.shape[1] != self.width or frame.shape[0] != self.height:
                frame = cv2.resize(frame, (self.width, self.height),
                                   interpolation=cv2.INTER_AREA)
            self.proc.stdin.write(np.ascontiguousarray(frame).tobytes())
        except (BrokenPipeError, OSError):
            self._failed = True

    def release(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
        except (BrokenPipeError, OSError):
            pass
        try:
            err = self.proc.stderr.read().decode("utf-8", "ignore") if self.proc.stderr else ""
            self.proc.wait(timeout=60)
            if err.strip():
                print("ffmpeg:", err.strip()[:400])
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass


class OpenCvWriter:
    """Fallback writer using OpenCV's H.264 encoder."""

    def __init__(self, path: str, fps: float, size: Tuple[int, int]):
        self.writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"avc1"),
                                      fps, size)
        if not self.writer.isOpened():
            self.writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"),
                                          fps, size)
        self.writer.release()
        self.writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"avc1"),
                                      fps, size)
        if not self.writer.isOpened():
            self.writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"),
                                          fps, size)

    def write(self, frame: np.ndarray) -> None:
        self.writer.write(frame)

    def release(self) -> None:
        self.writer.release()


def open_video_writer(path: str, fps: float, size: Tuple[int, int],
                       crf: int = 24):
    """Open a writer that produces a browser-playable file.

    Returns (writer, description).
    """
    if _ffmpeg_exe():
        try:
            w = FfmpegWriter(path, fps, size, crf=crf)
            return w, "h264 (faststart)"
        except Exception as exc:  # noqa: BLE001
            print("ffmpeg writer failed, falling back to OpenCV:", exc)
    return OpenCvWriter(path, fps, size), "h264 (openencv)"


def verify_playable(path: str) -> Tuple[bool, str]:
    """Check the produced file really is an H.264 MP4 with the index at the
    front, so a browser can start playing it immediately."""
    try:
        with open(path, "rb") as f:
            head = f.read(65536)
            size = os.path.getsize(path)
            if size > 131072:
                f.seek(max(0, size - 131072))
                tail = f.read()
            else:
                tail = b""
    except OSError as exc:
        return False, f"cannot read file: {exc}"

    has_avc1 = b"avc1" in head or b"avc1" in tail
    moov = head.find(b"moov")
    mdat = head.find(b"mdat")
    faststart = moov != -1 and (mdat == -1 or moov < mdat)
    if not has_avc1:
        return False, "no H.264 sample entry (avc1) found"
    if not faststart:
        return False, "index is not at the front (browser must download the whole file)"
    return True, "H.264 MP4 with faststart"
