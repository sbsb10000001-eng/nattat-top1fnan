import random
from kivy.app import App
from kivy.uix.widget import Widget
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.graphics import Rectangle, Color
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.properties import NumericProperty, BooleanProperty

# ---------------- Tunable constants ----------------
GRAVITY = -1300
JUMP_VELOCITY = 1100
ROCKET_VELOCITY = 1700
PLATFORM_W = 160
PLATFORM_H = 32
PLAYER_W = 70
PLAYER_H = 70
STAGE_HEIGHT = 1400
STARS_FOR_CHECKPOINT = 3
SCROLL_START_Y = 0.45

class GameWidget(FloatLayout):
    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self.width_ = Window.width
        self.height_ = Window.height

        # background
        with self.canvas.before:
            self.bg = Rectangle(source="assets/bg.png", pos=(0, 0), size=(self.width_, self.height_))
        self.bind(size=self._update_bg, pos=self._update_bg)

        # state
        self.reset_state(full_reset=True)

        # player sprite
        self.player = Image(source="assets/character.png", size=(PLAYER_W, PLAYER_H),
                             size_hint=(None, None))
        self.add_widget(self.player)

        # HUD
        self.score_label = Label(text="0", font_size=28, bold=True,
                                  pos_hint={"x": 0.02, "top": 0.99}, size_hint=(None, None),
                                  size=(150, 40), color=(0.1, 0.1, 0.1, 1))
        self.add_widget(self.score_label)

        self.stars_label = Label(text="⭐ 0/3", font_size=22, bold=True,
                                  pos_hint={"right": 0.98, "top": 0.99}, size_hint=(None, None),
                                  size=(150, 40), color=(0.5, 0.3, 0, 1))
        self.add_widget(self.stars_label)

        self.shield_label = Label(text="", font_size=20, bold=True,
                                   pos_hint={"center_x": 0.5, "top": 0.99}, size_hint=(None, None),
                                   size=(200, 40), color=(0.1, 0.6, 0.1, 1))
        self.add_widget(self.shield_label)

        self.platform_widgets = []
        self.item_widgets = []  # list of dicts: {"widget", "kind", "platform"}

        self.spawn_initial_platforms()
        self.place_player_on_start()

        Clock.schedule_interval(self.update, 1 / 60)
        Window.bind(on_touch_down=self.on_touch)

    # ---------------- setup helpers ----------------
    def _update_bg(self, *args):
        self.width_ = self.width
        self.height_ = self.height
        self.bg.pos = (0, 0)
        self.bg.size = (self.width_, self.height_)

    def reset_state(self, full_reset=False):
        self.vel_y = 0
        self.scroll_offset = 0
        self.score = 0
        self.max_score = 0
        self.game_over = False
        self.shield_active = False
        self.rocket_active = False
        self.rocket_timer = 0
        self.current_stage = 0
        if full_reset:
            self.total_stars = 0
            self.checkpoint_score = 0
            self.checkpoint_platform_seed = None

    def clear_world(self):
        for w in self.platform_widgets:
            self.remove_widget(w["widget"])
        for it in self.item_widgets:
            self.remove_widget(it["widget"])
        self.platform_widgets = []
        self.item_widgets = []

    def spawn_initial_platforms(self):
        self.clear_world()
        # starting platform right under the player
        base_x = self.width_ / 2 - PLATFORM_W / 2
        base_y = 120
        self.add_platform(base_x, base_y, breakable=False)
        y = base_y
        while y < self.height_ + 400:
            y += random.randint(90, 150)
            x = random.uniform(10, max(10, self.width_ - PLATFORM_W - 10))
            self.add_platform(x, y)
        self.top_spawn_y = y

    def add_platform(self, x, y, breakable=None):
        difficulty = min(self.checkpoint_score / 4000, 1.0)
        if breakable is None:
            breakable = random.random() < 0.15 + 0.15 * difficulty
        src = "assets/platform_crack.png" if breakable else "assets/platform.png"
        w = Image(source=src, size=(PLATFORM_W, PLATFORM_H), size_hint=(None, None), pos=(x, y))
        self.add_widget(w)
        pdata = {"widget": w, "x": x, "y": y, "breakable": breakable, "broken": False}
        self.platform_widgets.append(pdata)

        # chance to spawn item on top
        roll = random.random()
        if roll < 0.12:
            self.add_item(x + PLATFORM_W / 2 - 16, y + PLATFORM_H, "star", pdata)
        elif roll < 0.15:
            self.add_item(x + PLATFORM_W / 2 - 16, y + PLATFORM_H, "rocket", pdata)
        return pdata

    def add_item(self, x, y, kind, platform):
        size = (32, 32) if kind == "star" else (44, 66)
        src = f"assets/{kind}.png"
        w = Image(source=src, size=size, size_hint=(None, None), pos=(x, y))
        self.add_widget(w)
        self.item_widgets.append({"widget": w, "kind": kind, "platform": platform, "collected": False})

    def place_player_on_start(self):
        base = self.platform_widgets[0]
        self.player.pos = (base["x"] + PLATFORM_W / 2 - PLAYER_W / 2, base["y"] + PLATFORM_H)
        self.vel_y = JUMP_VELOCITY * 0.6

    # ---------------- input ----------------
    def on_touch(self, window, touch):
        if self.game_over:
            return
        # simple: tap left half = move left, right half = move right (auto-jump handles vertical)
        pass

    # ---------------- game loop ----------------
    def update(self, dt):
        if self.game_over:
            return

        # horizontal auto drift toward center-ish random walk via touch could be added;
        # for now, gentle auto side-to-side using accelerometer-less simple AI drift
        self.handle_horizontal(dt)

        # physics
        if self.rocket_active:
            self.vel_y = ROCKET_VELOCITY
            self.rocket_timer -= dt
            if self.rocket_timer <= 0:
                self.rocket_active = False
        else:
            self.vel_y += GRAVITY * dt

        new_y = self.player.y + self.vel_y * dt
        self.player.y = new_y

        # collision with platforms only when falling
        if self.vel_y <= 0:
            for p in self.platform_widgets:
                if p["broken"]:
                    continue
                px, py = p["x"], p["y"]
                if (self.player.x + PLAYER_W * 0.7 > px and self.player.x + PLAYER_W * 0.3 < px + PLATFORM_W
                        and self.player.y <= py + PLATFORM_H and self.player.y >= py - 10):
                    self.land_on_platform(p)
                    break

        # scroll world when player climbs above threshold
        threshold = self.height_ * SCROLL_START_Y
        if self.player.y > threshold:
            dy = self.player.y - threshold
            self.player.y = threshold
            self.scroll_world(dy)

        # item collisions
        self.check_item_collisions()

        # fell off bottom -> die
        if self.player.y < -PLAYER_H:
            self.die()

        # update score
        self.score = max(self.score, int(self.scroll_offset))
        self.score_label.text = str(self.score)
        stage = self.score // STAGE_HEIGHT
        if stage != self.current_stage:
            self.current_stage = stage
            self.shield_active = False  # shield resets each new stage until re-earned
        self.shield_label.text = "🛡️ محمي" if self.shield_active else ""

    def handle_horizontal(self, dt):
        # gentle continuous drift + wrap around screen edges (auto-runner style)
        if not hasattr(self, "_dir"):
            self._dir = random.choice([-1, 1])
            self._dir_timer = random.uniform(0.8, 1.8)
        self._dir_timer -= dt
        if self._dir_timer <= 0:
            self._dir = random.choice([-1, 1])
            self._dir_timer = random.uniform(0.8, 1.8)
        speed = 140
        self.player.x += self._dir * speed * dt
        if self.player.x < -PLAYER_W / 2:
            self.player.x = self.width_ - PLAYER_W / 2
        elif self.player.x > self.width_ - PLAYER_W / 2:
            self.player.x = -PLAYER_W / 2

    def land_on_platform(self, p):
        self.vel_y = JUMP_VELOCITY
        if p["breakable"]:
            p["broken"] = True
            p["widget"].opacity = 0

    def scroll_world(self, dy):
        self.scroll_offset += dy
        for p in self.platform_widgets:
            p["y"] -= dy
            p["widget"].y = p["y"]
        for it in self.item_widgets:
            it["widget"].y -= dy

        # remove off-screen platforms/items, spawn new ones on top
        keep_platforms = []
        for p in self.platform_widgets:
            if p["y"] < -60:
                self.remove_widget(p["widget"])
            else:
                keep_platforms.append(p)
        self.platform_widgets = keep_platforms

        keep_items = []
        for it in self.item_widgets:
            if it["widget"].y < -60 or it["collected"]:
                if it["widget"].parent:
                    self.remove_widget(it["widget"])
            else:
                keep_items.append(it)
        self.item_widgets = keep_items

        self.top_spawn_y -= dy
        while self.top_spawn_y < self.height_ + 300:
            self.top_spawn_y += random.randint(90, 150)
            x = random.uniform(10, max(10, self.width_ - PLATFORM_W - 10))
            self.add_platform(x, self.top_spawn_y)

    def check_item_collisions(self):
        for it in self.item_widgets:
            if it["collected"]:
                continue
            w = it["widget"]
            if (self.player.x < w.x + w.width and self.player.x + PLAYER_W > w.x
                    and self.player.y < w.y + w.height and self.player.y + PLAYER_H > w.y):
                it["collected"] = True
                w.opacity = 0
                if it["kind"] == "star":
                    self.collect_star()
                elif it["kind"] == "rocket":
                    self.activate_rocket()

    def collect_star(self):
        self.total_stars += 1
        if self.total_stars >= STARS_FOR_CHECKPOINT:
            self.total_stars = 0
            self.checkpoint_score = self.score
            self.shield_active = True
        self.stars_label.text = f"⭐ {self.total_stars}/{STARS_FOR_CHECKPOINT}"

    def activate_rocket(self):
        self.rocket_active = True
        self.rocket_timer = 1.6

    def die(self):
        if self.shield_active:
            # shield absorbs the fall/hit once, respawn near current height
            self.shield_active = False
            self.vel_y = JUMP_VELOCITY
            self.player.y = self.height_ * SCROLL_START_Y - 40
            return
        self.game_over = True
        self.app.show_game_over(self.score, self.checkpoint_score)

    def restart_from_checkpoint(self):
        self.reset_state(full_reset=False)
        self.score = self.checkpoint_score
        self.spawn_initial_platforms()
        self.place_player_on_start()
        self.stars_label.text = f"⭐ {self.total_stars}/{STARS_FOR_CHECKPOINT}"


class MenuScreen(FloatLayout):
    def __init__(self, start_cb, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            self.bg = Rectangle(source="assets/bg.png", pos=(0, 0), size=Window.size)
        self.bind(size=self._upd, pos=self._upd)

        title = Label(text="نطاط", font_size=64, bold=True, color=(0.1, 0.3, 0.1, 1),
                       pos_hint={"center_x": 0.5, "center_y": 0.65})
        self.add_widget(title)

        char = Image(source="assets/character.png", size=(140, 140), size_hint=(None, None),
                      pos_hint={"center_x": 0.5, "center_y": 0.45})
        self.add_widget(char)

        btn = Button(text="ابدأ اللعب", font_size=28, size_hint=(None, None), size=(220, 70),
                     pos_hint={"center_x": 0.5, "center_y": 0.22},
                     background_color=(0.3, 0.75, 0.4, 1))
        btn.bind(on_press=lambda *_: start_cb())
        self.add_widget(btn)

    def _upd(self, *a):
        self.bg.pos = (0, 0)
        self.bg.size = self.size


class GameOverScreen(FloatLayout):
    def __init__(self, score, checkpoint, restart_cb, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(0, 0, 0, 0.55)
            self.rect = Rectangle(pos=(0, 0), size=Window.size)
        self.bind(size=self._upd, pos=self._upd)

        box_label = Label(text="💥 خسرت!", font_size=48, bold=True, color=(1, 1, 1, 1),
                           pos_hint={"center_x": 0.5, "center_y": 0.62})
        self.add_widget(box_label)

        score_label = Label(text=f"نقاطك: {score}", font_size=28, color=(1, 1, 1, 1),
                             pos_hint={"center_x": 0.5, "center_y": 0.52})
        self.add_widget(score_label)

        cp_text = f"هتبدأ من: {checkpoint}" if checkpoint > 0 else "هتبدأ من الأول"
        cp_label = Label(text=cp_text, font_size=22, color=(1, 1, 0.6, 1),
                          pos_hint={"center_x": 0.5, "center_y": 0.44})
        self.add_widget(cp_label)

        btn = Button(text="كمّل تاني", font_size=26, size_hint=(None, None), size=(200, 65),
                     pos_hint={"center_x": 0.5, "center_y": 0.3},
                     background_color=(0.3, 0.75, 0.4, 1))
        btn.bind(on_press=lambda *_: restart_cb())
        self.add_widget(btn)

    def _upd(self, *a):
        self.rect.pos = (0, 0)
        self.rect.size = self.size


class NattatApp(App):
    def build(self):
        self.title = "نطاط"
        Window.clearcolor = (1, 1, 1, 1)
        self.root_widget = FloatLayout()
        self.game = None
        self.show_menu()
        return self.root_widget

    def show_menu(self):
        self.root_widget.clear_widgets()
        self.root_widget.add_widget(MenuScreen(self.start_game))

    def start_game(self):
        self.root_widget.clear_widgets()
        self.game = GameWidget(self)
        self.root_widget.add_widget(self.game)

    def show_game_over(self, score, checkpoint):
        overlay = GameOverScreen(score, checkpoint, self.restart_game)
        self.root_widget.add_widget(overlay)

    def restart_game(self):
        self.root_widget.clear_widgets()
        self.game.restart_from_checkpoint()
        self.root_widget.add_widget(self.game)


if __name__ == "__main__":
    NattatApp().run()
