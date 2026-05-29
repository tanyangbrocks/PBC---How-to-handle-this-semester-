# ============================================================
#  ui_video.py -- Pure-pygame sprite-folder video player
#  Replaces cv2.VideoCapture for pygbag / WebAssembly compat.
# ============================================================
import os
import json
import pygame


class SpritePlayer:
    """
    Frame-folder video player — no cv2 required.

    Expects a directory produced by scripts/extract_video_frames.py:
        <frames_dir>/00000.webp
        <frames_dir>/00001.webp
        ...
        <frames_dir>/meta.json   {"fps": 15.0, "frame_count": 120}

    If meta.json is absent, fps defaults to 15.0 and frame_count is
    counted from the directory listing.

    Parameters
    ----------
    frames_dir : str
        Absolute path to the frame directory.
    loop : bool
        True  → wrap back to frame 0 when the last frame is reached.
        False → hold the last frame and set .done = True.
    """

    def __init__(self, frames_dir: str, loop: bool = True):
        self.frames_dir = frames_dir
        self.loop       = loop
        self.done       = False

        self._cache:         dict  = {}      # idx → pygame.Surface | None
        self._frame_count:   int   = 0
        self._fps:           float = 15.0
        self._ms_per_frame:  float = 1000.0 / 15.0
        self._idx:           int   = 0
        self._last_adv_ms:   float = -1.0    # -1 = not started yet
        self._ext:           str   = ".webp"

        # ── Read metadata ────────────────────────────────────
        meta_path = os.path.join(frames_dir, "meta.json")
        if os.path.isfile(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as fh:
                    meta = json.load(fh)
                self._fps         = float(meta.get("fps", 15.0))
                self._frame_count = int(meta.get("frame_count", 0))
            except Exception:
                pass

        # ── Count frames from filesystem (fallback) ──────────
        if self._frame_count == 0 and os.path.isdir(frames_dir):
            for ext in (".webp", ".jpg", ".png"):
                cnt = sum(1 for f in os.listdir(frames_dir)
                          if f.lower().endswith(ext))
                if cnt > 0:
                    self._frame_count = cnt
                    self._ext = ext
                    break

        self._ms_per_frame = 1000.0 / max(self._fps, 1.0)

    # ── Public properties ────────────────────────────────────

    @property
    def loaded(self) -> bool:
        """True if at least one frame exists."""
        return self._frame_count > 0

    @property
    def fps(self) -> float:
        return self._fps

    # ── Internal helpers ─────────────────────────────────────

    def _load(self, idx: int) -> "pygame.Surface | None":
        """Lazily load and cache frame *idx*."""
        if idx not in self._cache:
            fn = f"{idx:05d}{self._ext}"
            fp = os.path.join(self.frames_dir, fn)
            if not os.path.isfile(fp):
                # Try alternate extensions
                for ext in (".webp", ".jpg", ".png"):
                    alt = os.path.join(self.frames_dir, f"{idx:05d}{ext}")
                    if os.path.isfile(alt):
                        fp = alt
                        break
                else:
                    self._cache[idx] = None
                    return None
            try:
                self._cache[idx] = pygame.image.load(fp).convert()
            except Exception:
                self._cache[idx] = None
        return self._cache[idx]

    # ── Public API ───────────────────────────────────────────

    def get_surface(
        self,
        now_ms:      int,
        target_size: "tuple[int, int] | None" = None,
    ) -> "pygame.Surface | None":
        """
        Return the current frame Surface (optionally scaled to *target_size*).
        Advances the internal frame counter based on elapsed time.
        Call once per game frame.
        """
        if self._frame_count == 0:
            return None

        # Initialise timer on first call
        if self._last_adv_ms < 0:
            self._last_adv_ms = float(now_ms)

        # Advance frame index by however many frames have elapsed
        if not self.done:
            while (now_ms - self._last_adv_ms) >= self._ms_per_frame:
                self._last_adv_ms += self._ms_per_frame
                self._idx += 1
                if self._idx >= self._frame_count:
                    if self.loop:
                        self._idx = 0
                    else:
                        self._idx = self._frame_count - 1
                        self.done = True
                        break

        surf = self._load(self._idx)
        if surf is None:
            return None
        if target_size is not None and target_size != surf.get_size():
            return pygame.transform.scale(surf, target_size)
        return surf

    def reset(self) -> None:
        """Rewind to frame 0 (e.g. for loop restart or game replay)."""
        self._idx         = 0
        self._last_adv_ms = -1.0
        self.done         = False
