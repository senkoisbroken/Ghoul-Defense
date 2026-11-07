"""Testable screen automation with explicit per-run bookkeeping."""

from dataclasses import dataclass
import json
import time
import cv2
from controls import WindowControls, FocusChanged, CaptureUnavailable
from gate import combat_visible


@dataclass
class ScreenState:
    last_action: object = None
    attempted_at: float = 0
    previous_status: object = None
    error_at: float = 0
    last_boss_mode: object = None
    last_movement_gate: object = None
    boss_logged_at: float = 0


def reset_tracking(motion, ultimate, tracker=None):
    motion.stop()
    ultimate.reset()
    if tracker is not None:
        tracker.reset()


class ScreenWorker:
    def __init__(self, root, desktop, motion, running, stopping, report, logger,
                 components, *, perform, attempt_ultimate,
                 controls_factory=WindowControls, clock=None):
        self.root, self.desktop, self.motion = root, desktop, motion
        self.running, self.stopping = running, stopping
        self.report, self.logger = report, logger
        self.reader, self.detector = components.reader, components.detector
        self.boss_tracker = components.boss_tracker
        self.ultimate, self.catalog = components.ultimate, components.catalog
        self.perform, self.attempt_ultimate = perform, attempt_ultimate
        self.controls_factory = controls_factory
        self.clock = clock if clock is not None else time.monotonic
        self.state = ScreenState()

    def step(self, capture):
        hwnd = self.desktop.roblox_window()
        if not hwnd:
            reset_tracking(self.motion, self.ultimate, self.boss_tracker)
            self.state.last_action = None
            return 'Waiting for Roblox in the foreground'
        bounds = self.desktop.client_rect(hwnd)
        context = self.controls_factory(self.desktop, capture, hwnd, bounds,
                                       lambda: self.running.is_set() and not self.stopping.is_set())
        image = context.read()
        decision = self.detector.read(image)
        if decision is None:
            return self.handle_combat(context, image, hwnd)
        return self.handle_menu(context, image, hwnd, decision)

    def run(self, capture):
        while not self.stopping.is_set():
            if not self.running.wait(.1):
                self.state.last_action = None
                continue
            if self.stopping.is_set():
                break
            try:
                message = self.step(capture)
                if message != self.state.previous_status:
                    self.report(message)
                    self.state.previous_status = message
            except (FocusChanged, CaptureUnavailable):
                reset_tracking(self.motion, self.ultimate, self.boss_tracker)
                self.state.last_action = None
            except Exception as exc:
                reset_tracking(self.motion, self.ultimate)
                self.report('Error: ' + str(exc))
                now = self.clock()
                if now-self.state.error_at > 10:
                    self.logger.exception('Worker error')
                    self.state.error_at = now
                self.stopping.wait(.5)
            self.stopping.wait(.12)

    def handle_combat(self, context, image, hwnd):
        combat = combat_visible(image, reader=self.reader)
        boss = self.boss_tracker.read(image) if combat else None
        target = boss.target if boss is not None else None
        movement_gate = (combat, boss is not None, target is not None)
        if movement_gate != self.state.last_movement_gate:
            self.logger.info('movement_gate combat=%s boss=%s target=%s', *movement_gate)
            self.state.last_movement_gate = movement_gate
        self.motion.observe(hwnd, combat and (boss is None or target is not None), self.clock(), boss=target)
        if self.attempt_ultimate(context, self.detector, self.boss_tracker, self.ultimate, boss, self.clock()):
            self.logger.info('ultimate_f_sent window=%s boss=%s', hwnd, boss.name)
        if combat and self.clock() - self.state.boss_logged_at > 3:
            self.logger.info('boss_scan %s', json.dumps(self.boss_tracker.last, ensure_ascii=True))
            self.state.boss_logged_at = self.clock()
        message = 'Waiting for the combat HUD — movement stopped' if not combat else 'Following ' + boss.name + ' lane' if target is not None else 'Boss detected — checking its lane' if boss is not None else 'W/S patrol — watching for choices and Start Wave'
        mode = (boss.name, boss.remaining, tuple((round(y / 12) for y in target)) if target else None) if boss is not None else None
        if mode != self.state.last_boss_mode:
            self.logger.info('boss_tracking %s', json.dumps({'name': boss.name if boss else None, 'remaining': boss.remaining if boss else None, 'target': target, 'window': int(hwnd)}))
            if boss is not None and target is None:
                path = self.root / 'work/boss_lane_unclear.png'
                cv2.imwrite(str(path), image)
                self.logger.info('boss_lane_capture %s', path)
            self.state.last_boss_mode = mode
        self.state.last_action = None
        return message

    def handle_menu(self, context, image, hwnd, decision):
        reset_tracking(self.motion, self.ultimate, self.boss_tracker)
        self.state.last_movement_gate = None
        for path in self.catalog.save(image, decision):
            self.logger.info('catalog_saved %s', path)
        identity = (hwnd, decision.signature)
        now = self.clock()
        message = 'Playing again' if decision.kind == 'replay' else 'Starting next wave' if decision.kind == 'wave' else 'Choosing ' + decision.name
        if identity != self.state.last_action or now - self.state.attempted_at >= 1.5:
            accepted = self.perform(context, self.detector, decision)
            self.state.last_action, self.state.attempted_at = (identity, self.clock())
            self.logger.info('action %s', json.dumps({'kind': decision.kind, 'chosen': decision.name, 'offered': decision.names, 'target': decision.target, 'accepted': bool(accepted), 'window': int(hwnd)}))
            if not accepted:
                message = 'Screen changed — checking again'
        return message
