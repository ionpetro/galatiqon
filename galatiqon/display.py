"""Screen output. `pygame` draws fullscreen via KMS/DRM (HDMI, DSI, or a
framebuffer-mapped SPI panel); `none` just logs, for headless testing."""

from __future__ import annotations

import logging
import os

from .config import DisplayConfig

log = logging.getLogger(__name__)

BG = (0, 0, 0)
FG = (255, 255, 255)
DIM = (140, 140, 140)


class NullDisplay:
    def show(self, status: str, body: str) -> None:
        log.info("screen | %s | %s", status, body.replace("\n", " / "))

    def pump(self) -> None:
        pass


class PygameDisplay:
    def __init__(self, cfg: DisplayConfig):
        os.environ.setdefault("SDL_VIDEODRIVER", "kmsdrm")
        import pygame

        self.pg = pygame
        pygame.display.init()
        pygame.font.init()
        pygame.mouse.set_visible(False)
        self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        self.w, self.h = self.screen.get_size()
        self.body_font = pygame.font.Font(None, int(cfg.font_size * 1.4))
        self.status_font = pygame.font.Font(None, cfg.font_size)
        self.margin = max(8, self.w // 40)

    def _wrap(self, text: str) -> list[str]:
        max_w = self.w - 2 * self.margin
        lines: list[str] = []
        for para in text.splitlines() or [""]:
            line = ""
            for word in para.split():
                trial = f"{line} {word}".strip()
                if self.body_font.size(trial)[0] <= max_w:
                    line = trial
                else:
                    if line:
                        lines.append(line)
                    line = word
            lines.append(line)
        return lines

    def show(self, status: str, body: str) -> None:
        self.screen.fill(BG)
        y = self.margin
        if status:
            self.screen.blit(self.status_font.render(status, True, DIM), (self.margin, y))
            y += self.status_font.get_linesize() + self.margin
        for line in self._wrap(body):
            if y + self.body_font.get_linesize() > self.h:
                break
            self.screen.blit(self.body_font.render(line, True, FG), (self.margin, y))
            y += self.body_font.get_linesize()
        self.pg.display.flip()

    def pump(self) -> None:
        self.pg.event.pump()


def make(cfg: DisplayConfig):
    if cfg.backend == "pygame":
        try:
            return PygameDisplay(cfg)
        except Exception as e:  # no screen attached, missing SDL driver, etc.
            log.warning("pygame display unavailable (%s); using log-only display", e)
    return NullDisplay()
