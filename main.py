import math
import os
import random
import struct
import wave

from kivy.app import App
from kivy.clock import Clock
from kivy.core.audio import SoundLoader
from kivy.core.window import Window
from kivy.graphics import (Color, Ellipse, Line, PopMatrix, PushMatrix,
                           Rectangle, Rotate)
from kivy.metrics import sp
from kivy.uix.label import Label
from kivy.uix.widget import Widget

# ===== Settings (sizes are fractions of the screen size) =====
GRAVITY = 1.8            # higher = falls faster
JUMP_VELOCITY = 1.04     # higher = jumps higher
PLATFORM_W = 0.22        # platform width
PLAYER_SIZE = 0.09       # player size at level 1
MIN_GAP = 0.09           # min vertical gap between platforms
MAX_GAP = 0.19           # max gap (keep below jump height ~0.30)
MILESTONE_EVERY = 100    # chime every N points
LEVEL_POINTS = 1000      # points needed for each new level
GROWTH_PER_LEVEL = 0.08  # player grows 8% every level
MAX_GROWTH = 1.9         # player never gets bigger than 1.9x
PLATFORM_SHRINK = 0.03   # platforms get 3% narrower each level (0 = off)
MIN_PLATFORM_SCALE = 0.6

MOVES = ["flip", "backflip", "dance", "dance", "spin"]


# ===== Sound effects: generated in code, no audio files needed =====
def make_wav(path, segments, rate=22050):
    """segments = list of (start_freq, end_freq, seconds, volume)"""
    frames = bytearray()
    for f0, f1, dur, vol in segments:
        n = int(rate * dur)
        phase = 0.0
        for i in range(n):
            t = i / n
            freq = f0 + (f1 - f0) * t
            phase += 2 * math.pi * freq / rate
            env = (1 - t) ** 1.5
            if i < 120:                      # short fade-in to avoid clicks
                env *= i / 120
            value = int(32767 * vol * env * math.sin(phase))
            frames += struct.pack("<h", value)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))


def build_sounds(folder):
    os.makedirs(folder, exist_ok=True)
    files = {
        "bounce": [(380, 820, 0.11, 0.45)],
        "milestone": [(660, 660, 0.09, 0.4), (990, 990, 0.16, 0.4)],
        "levelup": [(523, 523, 0.09, 0.4), (659, 659, 0.09, 0.4),
                    (784, 784, 0.09, 0.4), (1046, 1046, 0.25, 0.45)],
        "over": [(520, 110, 0.65, 0.5)],
    }
    sounds = {}
    for name, segments in files.items():
        path = os.path.join(folder, name + ".wav")
        try:
            make_wav(path, segments)
            sounds[name] = SoundLoader.load(path)
        except Exception:
            sounds[name] = None
    return sounds


class Game(Widget):
    def __init__(self, sounds=None, **kwargs):
        super().__init__(**kwargs)
        self.sounds = sounds or {}
        self.sound_on = True
        self.score_label = Label(text="0", font_size=sp(28))
        self.level_label = Label(text="Level 1", font_size=sp(18))
        self.sound_label = Label(text="Sound: ON", font_size=sp(16))
        self.banner_label = Label(text="", font_size=sp(44))
        self.msg_label = Label(text="", font_size=sp(30), halign="center",
                               valign="middle")
        for w in (self.score_label, self.level_label, self.sound_label,
                  self.banner_label, self.msg_label):
            self.add_widget(w)
        self.touch_id = None
        self.reset()

    def play(self, name):
        if not self.sound_on:
            return
        s = self.sounds.get(name)
        if s:
            try:
                s.stop()
                s.play()
            except Exception:
                pass

    def reset(self):
        W, H = Window.size
        self.level = 1
        self.scale = 1.0
        self.pw = PLAYER_SIZE * W
        self.px = W / 2
        self.py = H * 0.09          # py = the player's feet
        self.vy = JUMP_VELOCITY * H
        self.vx = 0.0
        self.tilt = 0.0
        self.score = 0.0
        self.next_mark = MILESTONE_EVERY
        self.banner_t = 0.0
        self.special = False
        self.game_over = False
        self.touch_x = None
        self.touch_id = None
        # first platform spans the whole width so you never miss it
        self.platforms = [[W / 2, H * 0.08, W]]
        self.top = H * 0.08
        self.fill()
        self.start_move()
        self.msg_label.text = ""
        self.banner_label.text = ""

    def platform_width(self, W):
        shrink = max(MIN_PLATFORM_SCALE, 1 - PLATFORM_SHRINK * (self.level - 1))
        return PLATFORM_W * W * shrink

    def fill(self):
        W, H = Window.size
        pwid = self.platform_width(W)
        while self.top < H * 1.3:
            self.top += random.uniform(MIN_GAP, MAX_GAP) * H
            x = random.uniform(pwid / 2, W - pwid / 2)
            self.platforms.append([x, self.top, pwid])

    # ===== Tricks: a new one is picked on every bounce =====
    def start_move(self):
        self.move_t = 0.0
        self.turns = 1
        if self.special:                       # level-up celebration
            self.special = False
            self.move = random.choice(["flip", "backflip"])
            self.turns = 2
            return
        self.move = random.choice(MOVES)
        if (self.move in ("flip", "backflip", "spin")
                and random.random() < min(0.4, 0.08 * self.level)):
            self.turns = 2

    def get_pose(self, H):
        t = self.move_t
        air = 2 * JUMP_VELOCITY / GRAVITY          # seconds in the air
        prog = min(t / (air * 0.85), 1.0)
        ease = prog * prog * (3 - 2 * prog)
        k = max(-1.0, min(1.0, self.vy / (JUMP_VELOCITY * H)))
        arms = -20 + 70 * k                        # arms rise when going up
        pose = {"angle": 0.0, "sx": 1.0, "sy": 1.0,
                "arm_l": arms, "arm_r": arms, "leg_l": 0.0, "leg_r": 0.0}

        if self.move in ("flip", "backflip"):
            direction = 1 if self.move == "backflip" else -1
            pose["angle"] = direction * 360 * self.turns * ease
            pose["arm_l"] = pose["arm_r"] = 25
        elif self.move == "dance":
            s = math.sin(t * 16)
            pose["angle"] = 12 * math.sin(t * 8)
            pose["arm_l"] = 55 + 45 * s
            pose["arm_r"] = 55 - 45 * s
            pose["leg_l"] = 0.16 * s
            pose["leg_r"] = -0.16 * s
        elif self.move == "spin":
            pose["sx"] = max(0.15, abs(math.cos(2 * math.pi * self.turns * ease)))

        # squash when landing
        if t < 0.12:
            q = 1 - t / 0.12
            pose["sy"] *= 1 - 0.3 * q
            pose["sx"] *= 1 + 0.25 * q

        pose["angle"] += self.tilt                 # lean toward the finger
        return pose

    # ===== Touch: the player follows your finger =====
    def on_touch_down(self, touch):
        W, H = Window.size
        # sound on/off button (top-right corner)
        if touch.x > W - sp(120) and touch.y > H - sp(60):
            self.sound_on = not self.sound_on
            self.sound_label.text = "Sound: ON" if self.sound_on else "Sound: OFF"
            return True
        if self.game_over:
            self.reset()
            return True
        self.touch_id = touch.uid
        self.touch_x = touch.x
        return True

    def on_touch_move(self, touch):
        if touch.uid == self.touch_id:
            self.touch_x = touch.x
        return True

    def on_touch_up(self, touch):
        if touch.uid == self.touch_id:
            self.touch_x = None
            self.touch_id = None
        return True

    # ===== Game loop =====
    def update(self, dt):
        W, H = Window.size
        dt = min(dt, 1 / 30)
        self.move_t += dt
        if self.banner_t > 0:
            self.banner_t -= dt

        # the player grows smoothly with the level
        target = min(MAX_GROWTH, 1 + GROWTH_PER_LEVEL * (self.level - 1))
        self.scale += (target - self.scale) * min(1, dt * 4)
        self.pw = PLAYER_SIZE * W * self.scale
        total_h = self.pw * 1.3

        points = int(self.score / H * 100)

        if not self.game_over:
            prev_px = self.px
            if self.touch_x is not None:
                self.px = min(max(self.touch_x, 0), W)
            if dt > 0:
                inst = (self.px - prev_px) / dt
                self.vx += (inst - self.vx) * min(1, dt * 12)
            self.tilt = -max(-1.0, min(1.0, self.vx / (W * 2))) * 18

            prev_feet = self.py
            self.vy -= GRAVITY * H * dt
            self.py += self.vy * dt

            # landing on a platform (only while falling)
            if self.vy <= 0:
                half = self.pw / 2
                for x, y, w in self.platforms:
                    if (prev_feet >= y - 1 and self.py <= y
                            and abs(self.px - x) <= w / 2 + half * 0.6):
                        self.py = y
                        self.vy = JUMP_VELOCITY * H
                        self.play("bounce")
                        self.start_move()
                        break

            # scroll the world down when the player goes high
            if self.py > H * 0.6:
                shift = self.py - H * 0.6
                self.py -= shift
                self.top -= shift
                self.score += shift
                for p in self.platforms:
                    p[1] -= shift
                self.platforms = [p for p in self.platforms if p[1] > -H * 0.05]
                self.fill()

            points = int(self.score / H * 100)

            # level up / milestone chime
            new_level = points // LEVEL_POINTS + 1
            if new_level > self.level:
                self.level = new_level
                self.special = True                # next bounce = double flip
                self.banner_t = 1.6
                self.play("levelup")
            elif points >= self.next_mark:
                self.play("milestone")
            while points >= self.next_mark:
                self.next_mark += MILESTONE_EVERY

            # fell off the bottom
            if self.py + total_h < 0:
                self.game_over = True
                self.play("over")
                self.msg_label.text = ("Game Over\nScore: %d\nLevel: %d\n"
                                       "Tap to restart" % (points, self.level))

        self.draw(W, H, points)

    def draw_player(self, H):
        pose = self.get_pose(H)
        pw = self.pw
        bw = pw * pose["sx"]
        bh = pw * pose["sy"]
        leg = pw * 0.28
        arm = pw * 0.42 * (0.3 + 0.7 * pose["sx"])
        cx = self.px
        cy = self.py + leg + bh / 2
        lw = max(sp(2), pw * 0.07)

        PushMatrix()
        Rotate(angle=pose["angle"], origin=(cx, cy))

        # legs and arms
        Color(0.95, 0.6, 0.1)
        for side, kick, lift in ((-1, pose["leg_l"], pose["arm_l"]),
                                 (1, pose["leg_r"], pose["arm_r"])):
            x0 = cx + side * bw * 0.2
            y0 = cy - bh / 2
            Line(points=[x0, y0, x0 + kick * pw, self.py], width=lw)
            a = math.radians(lift)
            sx0 = cx + side * bw / 2
            sy0 = cy + bh * 0.05
            Line(points=[sx0, sy0, sx0 + side * math.cos(a) * arm,
                         sy0 + math.sin(a) * arm], width=lw)

        # body
        Color(1, 0.85, 0.2)
        Ellipse(pos=(cx - bw / 2, cy - bh / 2), size=(bw, bh))

        # eyes (they look where you are moving)
        look = max(-1.0, min(1.0, self.vx / (Window.width * 1.5)))
        ew, eh = bw * 0.22, bh * 0.26
        for side in (-1, 1):
            ex = cx + side * bw * 0.2
            ey = cy + bh * 0.12
            Color(1, 1, 1)
            Ellipse(pos=(ex - ew / 2, ey - eh / 2), size=(ew, eh))
            Color(0.1, 0.1, 0.1)
            pd = ew * 0.5
            Ellipse(pos=(ex - pd / 2 + look * ew * 0.2, ey - pd / 2),
                    size=(pd, pd))

        # smile
        Color(0.5, 0.25, 0.05)
        Line(circle=(cx, cy - bh * 0.05, bw * 0.16, 90, 270),
             width=max(sp(1.5), lw * 0.6))

        PopMatrix()

    def draw(self, W, H, points):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(0.08, 0.09, 0.16)
            Rectangle(pos=(0, 0), size=(W, H))
            Color(0.3, 0.85, 0.4)
            th = H * 0.015
            for x, y, w in self.platforms:
                Rectangle(pos=(x - w / 2, y - th), size=(w, th))
            self.draw_player(H)

        self.score_label.text = str(points)
        self.score_label.size = (W, sp(50))
        self.score_label.pos = (0, H - sp(60))
        self.level_label.text = "Level %d" % self.level
        self.level_label.size = (sp(120), sp(50))
        self.level_label.pos = (0, H - sp(60))
        self.sound_label.size = (sp(120), sp(50))
        self.sound_label.pos = (W - sp(120), H - sp(60))
        self.banner_label.text = ("LEVEL %d" % self.level
                                  if self.banner_t > 0 and not self.game_over else "")
        self.banner_label.size = (W, sp(70))
        self.banner_label.pos = (0, H * 0.7)
        self.msg_label.size = (W, H * 0.3)
        self.msg_label.text_size = (W, H * 0.3)
        self.msg_label.pos = (0, H * 0.35)


class NattatApp(App):
    def build(self):
        sounds = build_sounds(os.path.join(self.user_data_dir, "sfx"))
        game = Game(sounds=sounds)
        Clock.schedule_interval(game.update, 1 / 60)
        return game


if __name__ == "__main__":
    NattatApp().run()
