# page9.py

import sys
from datetime import datetime

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QPushButton,
    QMessageBox,
)
from PyQt6.QtGui import QShortcut, QKeySequence

try:
    from PyQt6.QtTextToSpeech import QTextToSpeech
except ImportError:
    QTextToSpeech = None


class Page9Widget(QWidget):
    """
    睁眼/闭眼范式（Run 级设计）

    时间从“点击开始按钮”的时刻算起（t=0）。

    每个 run 结构示意（以 To/ Tc / Tr 为配置）：

      初始一次：
        0–10s: 初始倒计时（不记日志）

      每个 run（i = 1..N）：
        +3s:   提示“请睁眼”（3s，不记日志）
        +To:   eye_open（记日志）
        +Tc:   提示“请闭眼”+闭眼采集（同一时间段；记日志为 eye_closed）
        +To:   提示“请睁眼”+睁眼采集（同一时间段；记日志为第二段 eye_open）
        +3s:   “采集结束”提示（不记日志）
        +Tr:   休息（仅在非最后一个 run，不记日志）

    激活期标签：
      - eye_open
      - eye_closed

    日志：
      start_sec,end_sec,condition,duration=秒,run=idx,segment=标记
      所有时间为逻辑时间（相对 Start 点击）。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("睁眼 / 闭眼 实验")
        self.setMinimumSize(900, 700)

        # ---------- 固定/默认参数 ----------
        self.initial_countdown = 10  # 实验开始前倒计时（秒）
        self.cue_open_pre = 3  # ✅ 每个 run 开始时“请睁眼”提示时长（秒，原来是5，改为3）
        self.end_cue_duration = 3  # 每个 run 的“采集结束”提示时长（秒）

        self.default_open_duration = 10  # 默认 eye_open 激活期（秒）
        self.default_closed_duration = 10  # 默认 eye_closed 激活期（秒）
        self.default_rest_duration = 10  # 默认 run 间休息（秒）
        self.default_runs = 5  # 默认 run 数量

        # 条件标签
        self.COND_OPEN = "eye_open"
        self.COND_CLOSED = "eye_closed"

        # ---------- 状态变量 ----------
        self.name = ""
        self.total_runs = self.default_runs
        self.current_run = 0  # 从 0 开始计数
        self.logical_ms = 0  # 逻辑时间：start 按下 = 0
        self.trial_logs = []  # 每个激活期一条记录

        self.open_duration = self.default_open_duration
        self.closed_duration = self.default_closed_duration
        self.rest_duration = self.default_rest_duration

        self._countdown_timer = None

        # ---------- 语音 ----------
        self.tts = None
        self._init_tts()

        # ---------- UI ----------
        root = QVBoxLayout(self)
        root.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        # 说明
        self.instruction = QLabel(
            "填写信息后点击开始。\n"
            "本范式在每个 Run 内按顺序采集：睁眼 → 闭眼 → 睁眼。\n"
            "时间轴从点击 Start 那一刻开始，请同步启动 EEG 采集。"
        )
        f = self.instruction.font()
        f.setPointSize(13)
        self.instruction.setFont(f)
        self.instruction.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.instruction.setWordWrap(True)
        root.addWidget(self.instruction)

        # 参数设置
        settings = QWidget()
        settings.setMaximumWidth(520)
        form = QFormLayout(settings)
        form.setFormAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        self.name_input = QLineEdit()
        form.addRow("姓名:", self.name_input)

        self.runs_spin = QSpinBox()
        self.runs_spin.setRange(1, 999)
        self.runs_spin.setValue(self.default_runs)
        form.addRow("Runs 数（每个 Run: 开-闭-开）:", self.runs_spin)

        self.open_spin = QSpinBox()
        self.open_spin.setRange(1, 600)
        self.open_spin.setValue(self.default_open_duration)
        form.addRow("睁眼激活期时长 To (秒):", self.open_spin)

        self.closed_spin = QSpinBox()
        self.closed_spin.setRange(1, 600)
        self.closed_spin.setValue(self.default_closed_duration)
        form.addRow("闭眼激活期时长 Tc (秒):", self.closed_spin)

        self.rest_spin = QSpinBox()
        self.rest_spin.setRange(0, 600)
        self.rest_spin.setValue(self.default_rest_duration)
        form.addRow("Run 间休息 Tr (秒):", self.rest_spin)

        root.addWidget(settings)
        self.settings_widget = settings

        # 开始按钮
        self.start_btn = QPushButton("开始实验")
        self.start_btn.clicked.connect(self.on_start_clicked)
        root.addWidget(self.start_btn, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        # 大显示区
        self.stage_label = QLabel("")
        fs = self.stage_label.font()
        fs.setPointSize(40)
        self.stage_label.setFont(fs)
        self.stage_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.stage_label.hide()
        root.addWidget(self.stage_label)

        # 倒计时显示
        self.countdown_label = QLabel("")
        fc = self.countdown_label.font()
        fc.setPointSize(32)
        self.countdown_label.setFont(fc)
        self.countdown_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.countdown_label.hide()
        root.addWidget(self.countdown_label)

        # ESC 中断
        self.esc_shortcut = QShortcut(QKeySequence(QtCore.Qt.Key.Key_Escape), self)
        self.esc_shortcut.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
        self.esc_shortcut.activated.connect(self.abort_and_finalize)

    # ---------- 语音初始化 ----------

    def _init_tts(self):
        if QTextToSpeech is None:
            return
        try:
            engines = QTextToSpeech.availableEngines()
        except Exception:
            return
        if not engines:
            return

        # Windows 下优先使用 sapi 引擎
        if sys.platform.startswith("win") and "sapi" in engines:
            engine = "sapi"
        else:
            engine = engines[0]

        try:
            self.tts = QTextToSpeech(engine, self)
            self.tts.setVolume(1.0)
        except Exception:
            self.tts = None

    def _speak(self, text: str):
        if self.tts is not None and text:
            try:
                self.tts.say(text)
            except Exception:
                pass

    # ---------- 开始入口 ----------

    def on_start_clicked(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "错误", "请输入姓名！")
            return

        To = self.open_spin.value()
        Tc = self.closed_spin.value()
        Tr = self.rest_spin.value()
        runs = self.runs_spin.value()

        if To <= 0 or Tc <= 0:
            QMessageBox.warning(self, "错误", "激活期时长必须大于 0 秒。")
            return

        self.name = name
        self.open_duration = To
        self.closed_duration = Tc
        self.rest_duration = Tr
        self.total_runs = runs

        # 状态重置
        self.current_run = 0
        self.logical_ms = 0
        self.trial_logs = []

        # UI 切换
        self.instruction.hide()
        self.start_btn.hide()
        self.settings_widget.hide()

        # 初始倒计时，从此刻起 t=0
        self._show_fullscreen_message(
            "{n}秒后将开始实验",
            self.initial_countdown,
            plain=True,
            next_callback=self._after_initial_countdown,
        )

    def _after_initial_countdown(self):
        # 初始倒计时结束，逻辑时间前进
        self.logical_ms += self.initial_countdown * 1000
        self._start_run()

    # ---------- Run 流程 ----------

    def _start_run(self):
        if self.current_run >= self.total_runs:
            # 所有 run 完成
            self._finish_and_save()
            return

        # Run 起始：3s 提示“请睁眼”（不记日志）
        cue = "请睁眼"
        self._speak(cue)
        self._show_fullscreen_message(
            cue,
            self.cue_open_pre,
            bg="#ffec99",
            fg="#000000",
            plain=False,
            next_callback=self._run_open1,
        )

    def _run_open1(self):
        # 完成 3s 提示
        self.logical_ms += self.cue_open_pre * 1000

        dur = self.open_duration
        start_ms = self.logical_ms
        end_ms = start_ms + dur * 1000

        # 第一次睁眼激活期
        self.trial_logs.append(
            {
                "condition": self.COND_OPEN,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "duration": dur,
                "run": self.current_run + 1,
                "segment": "open1",
            }
        )

        self._apply_bg("#ffffff")
        self._apply_fg("#000000")
        self.stage_label.setText("睁眼数据采集中")
        self.stage_label.show()
        self.countdown_label.hide()

        QtCore.QTimer.singleShot(dur * 1000, self._run_closed)

    def _run_closed(self):
        # 第一次睁眼结束
        self.logical_ms = self.trial_logs[-1]["end_ms"]

        dur = self.closed_duration
        start_ms = self.logical_ms
        end_ms = start_ms + dur * 1000

        # 闭眼阶段：提示 + 激活期重叠
        self.trial_logs.append(
            {
                "condition": self.COND_CLOSED,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "duration": dur,
                "run": self.current_run + 1,
                "segment": "closed",
            }
        )

        txt = "闭眼数据采集中"
        self._speak("请闭眼")
        self._apply_bg("#ffffff")
        self._apply_fg("#000000")
        self.stage_label.setText(txt)
        self.stage_label.show()
        self.countdown_label.hide()

        QtCore.QTimer.singleShot(dur * 1000, self._run_open2)

    def _run_open2(self):
        # 闭眼结束
        self.logical_ms = self.trial_logs[-1]["end_ms"]

        dur = self.open_duration
        start_ms = self.logical_ms
        end_ms = start_ms + dur * 1000

        # 第二次睁眼阶段：提示 + 激活期重叠
        self.trial_logs.append(
            {
                "condition": self.COND_OPEN,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "duration": dur,
                "run": self.current_run + 1,
                "segment": "open2",
            }
        )

        txt = "睁眼数据采集中"
        self._speak("请睁眼")
        self._apply_bg("#ffffff")
        self._apply_fg("#000000")
        self.stage_label.setText(txt)
        self.stage_label.show()
        self.countdown_label.hide()

        QtCore.QTimer.singleShot(dur * 1000, self._run_end_cue)

    def _run_end_cue(self):
        # 第二次睁眼结束
        self.logical_ms = self.trial_logs[-1]["end_ms"]

        # 3s “采集结束”提示（不记日志）
        txt = "采集结束"
        self._speak(txt)
        self._show_fullscreen_message(
            txt,
            self.end_cue_duration,
            bg="#e6ffea",
            fg="#000000",
            plain=False,
            next_callback=self._after_run_end_cue,
        )

    def _after_run_end_cue(self):
        # 结束提示计入时间
        self.logical_ms += self.end_cue_duration * 1000
        self.current_run += 1

        # 最后一个 run：不休息，直接结束
        if self.current_run >= self.total_runs:
            self._finish_and_save()
            return

        # 其他 run：休息 Tr 秒（不记日志）
        if self.rest_duration > 0:
            self._show_fullscreen_message(
                "请休息，{n}秒后开始下一次实验",
                self.rest_duration,
                bg="#dddddd",
                fg="#000000",
                plain=False,
                next_callback=self._after_rest,
            )
        else:
            # 没有休息，直接下一个 run
            self._start_run()

    def _after_rest(self):
        self.logical_ms += self.rest_duration * 1000
        self._start_run()

    # ---------- 全屏消息 & 倒计时 ----------

    def _show_fullscreen_message(
        self,
        template_or_text: str,
        seconds: int,
        bg: str | None = None,
        fg: str | None = None,
        plain: bool = False,
        next_callback=None,
    ):
        if plain:
            self._clear_styles()
        else:
            if bg is not None:
                self._apply_bg(bg)
            if fg is not None:
                self._apply_fg(fg)

        self.stage_label.hide()
        self.countdown_label.show()

        self._countdown_value = int(seconds)
        self._countdown_template = template_or_text

        # 初始显示
        if "{n}" in template_or_text:
            txt = template_or_text.format(n=self._countdown_value)
        else:
            txt = template_or_text
        self.countdown_label.setText(txt)

        # 清理旧 timer
        if self._countdown_timer is not None:
            self._countdown_timer.stop()
            self._countdown_timer.deleteLater()
            self._countdown_timer = None

        self._countdown_timer = QtCore.QTimer(self)
        self._countdown_timer.timeout.connect(lambda: self._tick(next_callback))
        self._countdown_timer.start(1000)

    def _tick(self, next_callback):
        self._countdown_value -= 1
        if self._countdown_value > 0:
            if "{n}" in self._countdown_template:
                txt = self._countdown_template.format(n=self._countdown_value)
            else:
                txt = self._countdown_template
            self.countdown_label.setText(txt)
        else:
            if self._countdown_timer is not None:
                self._countdown_timer.stop()
                self._countdown_timer.deleteLater()
                self._countdown_timer = None
            self.countdown_label.hide()
            if callable(next_callback):
                next_callback()

    # ---------- 样式 ----------

    def _apply_bg(self, color: str):
        self.setStyleSheet(f"background-color:{color};")

    def _apply_fg(self, color: str):
        self.stage_label.setStyleSheet(f"color:{color};")
        self.countdown_label.setStyleSheet(f"color:{color};")

    def _clear_styles(self):
        self.setStyleSheet("")
        self.stage_label.setStyleSheet("")
        self.countdown_label.setStyleSheet("")

    # ---------- 结束 & 中断 ----------

    def _finish_and_save(self):
        self._save_report()
        self._reset_ui()

    def abort_and_finalize(self):
        self._save_report(aborted=True)
        self._reset_ui()

    def _save_report(self, aborted: bool = False):
        if not self.trial_logs:
            return
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        flag = "ABORT" if aborted else "DONE"
        fname = f"EyeOpenClose_{self.name}_{ts}_runs{self.total_runs}_{flag}.txt"
        try:
            with open(fname, "w", encoding="utf-8") as f:
                for rec in self.trial_logs:
                    t0 = rec["start_ms"] / 1000.0
                    t1 = rec["end_ms"] / 1000.0
                    cond = rec["condition"]
                    dur = rec["duration"]
                    run = rec.get("run", "")
                    seg = rec.get("segment", "")
                    f.write(f"{t0:.3f},{t1:.3f},{cond},duration={dur},run={run},segment={seg}\n")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"写入日志失败：{e}")

    def _reset_ui(self):
        if self._countdown_timer is not None:
            self._countdown_timer.stop()
            self._countdown_timer.deleteLater()
            self._countdown_timer = None

        self._clear_styles()
        self.stage_label.hide()
        self.countdown_label.hide()

        # 恢复配置区
        self.name_input.clear()
        self.instruction.show()
        self.start_btn.show()
        self.settings_widget.show()

        # 状态复位
        self.current_run = 0
        self.logical_ms = 0
        self.trial_logs = []


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = Page9Widget()
    w.show()
    sys.exit(app.exec())
