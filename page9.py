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

# Qt 跨平台语音（用于提示语）
try:
    from PyQt6.QtTextToSpeech import QTextToSpeech
except ImportError:
    QTextToSpeech = None


class Page9Widget(QWidget):
    """
    睁眼 vs 闭眼 EEG 实验范式（Page9）

    时间轴以“点击开始按钮”的时刻为 0。

    实验流程（每个 run）：
      0) 全局：Start 按下 → 初始倒计时 10s

      对每个 run：
        1) 5s 提示期：
             文本 & 语音：“请闭眼，听到哔的一声，请睁眼”
        2) 闭眼激活期（closed_duration 秒）：
             文本：“{closed_duration}秒闭眼数据采集中”
             * 激活期开始记 marker（eye_closed）
        3) 闭眼结束：
             系统哔一声 (QApplication.beep)
        4) 睁眼激活期（open_duration 秒）：
             文本：“{open_duration}秒睁眼数据采集中”
             * 激活期开始记 marker（eye_open）
        5) Run 结束提示 3s：
             文本 & 语音：“采集结束”
        6) 若不是最后一个 run：
             休息 10s：“请休息{n}秒”
             然后进入下一 run
           若是最后一个 run：
             直接写日志并重置

    日志每行：
      start_time,end_time,condition,duration=激活期秒数
      - 时间单位：秒，小数点后三位
      - 相对 Start 按钮点击时刻
      - condition: eye_closed / eye_open
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("睁眼 vs 闭眼 实验")
        self.setMinimumSize(900, 700)

        # ------------ 默认参数 ------------
        self.initial_countdown = 10     # 实验前倒计时（秒）
        self.cue_duration = 5           # 提示阶段（秒）
        self.closed_duration = 10       # 闭眼激活期（秒）
        self.open_duration = 10         # 睁眼激活期（秒）
        self.rest_duration = 10         # run 间休息（秒）
        self.default_runs = 5           # run 数量

        # 条件标签
        self.condition_closed = "eye_closed"
        self.condition_open = "eye_open"

        # ------------ 状态变量 ------------
        self.name = ""
        self.runs = self.default_runs
        self.current_run = 0            # 1..runs
        self.logical_ms = 0             # Start 按下时刻 = 0
        self.trial_logs = []            # 每个激活期记录

        self._countdown_timer = None

        # ------------ 语音引擎 ------------
        self.tts = None
        self._init_tts()

        # ------------ UI ------------
        root = QVBoxLayout(self)
        root.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        # 说明
        self.instruction = QLabel(
            "填写信息后点击开始。\n"
            "本实验在每个 Run 中依次采集【闭眼】和【睁眼】状态下的 EEG 信号。\n"
            "按下 Start 即视为时间零点，请同时启动 EEG 记录。"
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
        self.runs_spin.setRange(1, 200)
        self.runs_spin.setValue(self.default_runs)
        form.addRow("Runs 数量:", self.runs_spin)

        self.closed_spin = QSpinBox()
        self.closed_spin.setRange(1, 600)
        self.closed_spin.setValue(self.closed_duration)
        form.addRow("闭眼激活期时长 (秒):", self.closed_spin)

        self.open_spin = QSpinBox()
        self.open_spin.setRange(1, 600)
        self.open_spin.setValue(self.open_duration)
        form.addRow("睁眼激活期时长 (秒):", self.open_spin)

        root.addWidget(settings)
        self.settings_widget = settings

        # 开始按钮
        self.start_btn = QPushButton("开始实验")
        self.start_btn.clicked.connect(self.on_start_clicked)
        root.addWidget(self.start_btn, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        # 阶段大文本
        self.stage_label = QLabel("")
        fs = self.stage_label.font()
        fs.setPointSize(40)
        self.stage_label.setFont(fs)
        self.stage_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.stage_label.hide()
        root.addWidget(self.stage_label)

        # 倒计时标签
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

    # ------------ TTS 初始化 ------------

    def _init_tts(self):
        """根据平台初始化 QTextToSpeech；Windows 上优先使用 sapi 引擎。"""
        if QTextToSpeech is None:
            self.tts = None
            return

        engines = QTextToSpeech.availableEngines()
        platform = sys.platform.lower()

        try:
            if platform.startswith("win"):
                # Windows：尽量用 sapi
                if "sapi" in engines:
                    self.tts = QTextToSpeech("sapi", self)
                else:
                    self.tts = QTextToSpeech(self)
            else:
                # macOS / Linux：默认引擎
                self.tts = QTextToSpeech(self)
        except Exception:
            self.tts = None
            return

        if self.tts is None:
            return

        # 尝试选中文声
        try:
            voices = self.tts.availableVoices()
            target = -1
            for i, v in enumerate(voices):
                loc = v.locale().name().lower()
                name = (v.name() or "").lower()
                if "zh" in loc or "chinese" in name or "mandarin" in name:
                    target = i
                    break
            if target >= 0:
                self.tts.setVoice(voices[target])
            elif voices:
                self.tts.setVoice(voices[0])
            self.tts.setVolume(1.0)
        except Exception:
            pass

    # ------------ 开始入口 ------------

    def on_start_clicked(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "错误", "请输入姓名！")
            return

        closed_dur = self.closed_spin.value()
        open_dur = self.open_spin.value()
        runs = self.runs_spin.value()

        if closed_dur <= 0 or open_dur <= 0:
            QMessageBox.warning(self, "错误", "激活期时长必须大于0秒。")
            return

        self.name = name
        self.closed_duration = closed_dur
        self.open_duration = open_dur
        self.runs = runs

        # 状态复位
        self.current_run = 0
        self.trial_logs = []
        self.logical_ms = 0  # Start 按下 = 0

        # 隐藏配置 UI
        self.instruction.hide()
        self.start_btn.hide()
        self.settings_widget.hide()

        # 初始 10 秒倒计时
        self._show_fullscreen_message(
            "{n}秒后将开始实验",
            self.initial_countdown,
            plain=True,
            next_callback=self._after_initial_countdown,
        )

    def _after_initial_countdown(self):
        # 累加初始倒计时
        self.logical_ms += self.initial_countdown * 1000
        # 开始第一个 run
        self._start_next_run()

    # ------------ Run 流程 ------------

    def _start_next_run(self):
        self.current_run += 1
        if self.current_run > self.runs:
            # 理论上不会到这里（run 结束都会走 _finish_and_save）
            self._finish_and_save()
            return

        # 5 秒提示期：请闭眼，听到哔的一声，请睁眼
        cue_text = "请闭眼，听到哔的一声，请睁眼"
        self._speak(cue_text)
        self._show_fullscreen_message(
            cue_text,
            self.cue_duration,
            bg="#ffec99",
            fg="#000000",
            plain=False,
            next_callback=self._after_cue,
        )

    def _after_cue(self):
        # 累加提示期
        self.logical_ms += self.cue_duration * 1000
        # 进入闭眼激活期
        self._start_closed_activation()

    def _start_closed_activation(self):
        dur = self.closed_duration
        start_ms = self.logical_ms
        end_ms = start_ms + int(dur * 1000)

        # 记录闭眼激活期
        self.trial_logs.append(
            {
                "condition": self.condition_closed,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "duration": int(dur),
            }
        )

        # 显示闭眼采集
        self._apply_bg("#ffffff")
        self._apply_fg("#000000")
        self.stage_label.setText(f"{dur}秒闭眼数据采集中")
        self.stage_label.show()
        self.countdown_label.hide()

        QtCore.QTimer.singleShot(int(dur * 1000), self._end_closed_activation)

    def _end_closed_activation(self):
        # 对齐逻辑时间
        last = self.trial_logs[-1]
        self.logical_ms = last["end_ms"]

        # 哔一声，提示睁眼
        QApplication.beep()

        # 直接进入睁眼激活期
        self._start_open_activation()

    def _start_open_activation(self):
        dur = self.open_duration
        start_ms = self.logical_ms
        end_ms = start_ms + int(dur * 1000)

        # 记录睁眼激活期
        self.trial_logs.append(
            {
                "condition": self.condition_open,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "duration": int(dur),
            }
        )

        # 显示睁眼采集
        self._apply_bg("#ffffff")
        self._apply_fg("#000000")
        self.stage_label.setText(f"{dur}秒睁眼数据采集中")
        self.stage_label.show()
        self.countdown_label.hide()

        QtCore.QTimer.singleShot(int(dur * 1000), self._end_open_activation)

    def _end_open_activation(self):
        # 睁眼激活结束，对齐时间
        last = self.trial_logs[-1]
        self.logical_ms = last["end_ms"]

        # 本 run 结束提示：3 秒“采集结束”
        end_text = "采集结束"
        self._speak(end_text)

        self._show_fullscreen_message(
            end_text,
            3,
            bg="#e6ffea",
            fg="#000000",
            plain=False,
            next_callback=self._after_run_end,
        )

    def _after_run_end(self):
        # 将 3 秒提示计入时间线
        self.logical_ms += 3 * 1000

        # 若还有下一 run，则休息 10 秒；否则结束实验
        if self.current_run < self.runs:
            self._start_rest()
        else:
            self._finish_and_save()

    def _start_rest(self):
        self._show_fullscreen_message(
            "请休息{n}秒",
            self.rest_duration,
            bg="#e6ffea",
            fg="#000000",
            plain=False,
            next_callback=self._after_rest,
        )

    def _after_rest(self):
        # 将休息时间计入逻辑时间
        self.logical_ms += self.rest_duration * 1000
        # 下一 run
        self._start_next_run()

    # ------------ 全屏消息 + 倒计时 ------------

    def _show_fullscreen_message(
        self,
        template_or_text: str,
        seconds: int,
        bg: str | None = None,
        fg: str | None = None,
        plain: bool = False,
        next_callback=None,
    ):
        """
        显示全屏文本或倒计时：
        - template_or_text: 可包含 {n}，则显示倒计时；否则显示静态文本。
        - seconds: 总显示时间。
        - plain=True: 清除背景样式。
        """
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

        # 初次显示
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

    # ------------ 样式 & 语音 ------------

    def _apply_bg(self, color: str):
        self.setStyleSheet(f"background-color:{color};")

    def _apply_fg(self, color: str):
        self.stage_label.setStyleSheet(f"color:{color};")
        self.countdown_label.setStyleSheet(f"color:{color};")

    def _clear_styles(self):
        self.setStyleSheet("")
        self.stage_label.setStyleSheet("")
        self.countdown_label.setStyleSheet("")

    def _speak(self, text: str):
        """使用 QTextToSpeech 播报提示语；失败则静默。"""
        if self.tts is None:
            return
        try:
            self.tts.setVolume(1.0)
            self.tts.say(text)
        except Exception:
            pass

    # ------------ 结束 & 中断 ------------

    def _finish_and_save(self):
        self._save_report()
        self._reset_ui()

    def abort_and_finalize(self):
        # ESC 中断：保存已有数据（如果有）
        self._save_report(aborted=True)
        self._reset_ui()

    def _save_report(self, aborted: bool = False):
        if not self.trial_logs:
            return
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        flag = "ABORT" if aborted else "DONE"
        fname = f"EyeOpenClose_{self.name}_{ts}_blocks{len(self.trial_logs)}_{flag}.txt"
        try:
            with open(fname, "w", encoding="utf-8") as f:
                for rec in self.trial_logs:
                    t0 = rec["start_ms"] / 1000.0
                    t1 = rec["end_ms"] / 1000.0
                    cond = rec["condition"]
                    dur = rec["duration"]
                    f.write(f"{t0:.3f},{t1:.3f},{cond},duration={dur}\n")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"写入日志失败：{e}")

    def _reset_ui(self):
        # 停止倒计时
        if self._countdown_timer is not None:
            self._countdown_timer.stop()
            self._countdown_timer.deleteLater()
            self._countdown_timer = None

        # 清 UI
        self._clear_styles()
        self.stage_label.hide()
        self.countdown_label.hide()

        # 恢复初始界面
        self.name_input.clear()
        self.instruction.show()
        self.start_btn.show()
        self.settings_widget.show()

        # 状态复位
        self.current_run = 0
        self.trial_logs = []
        self.logical_ms = 0


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = Page9Widget()
    w.show()
    sys.exit(app.exec())
