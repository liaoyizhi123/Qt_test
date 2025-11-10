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

# 尝试导入 Qt 自带的跨平台语音模块（macOS / Windows 兼容）
try:
    from PyQt6.QtTextToSpeech import QTextToSpeech
except ImportError:
    QTextToSpeech = None


class Page9Widget(QWidget):
    """
    睁眼 vs 闭眼 EEG 实验范式（Page9）

    时间轴以“点击开始按钮”的时刻为 0：
      - Start 按下：t = 0
      - 初始倒计时 10 秒（提示“10秒后将开始实验”）
      - 对每个循环（cycle）执行：
          1) 睁眼块：
              - 3s：语音“请睁眼” + 文本
              - 激活期 open_duration 秒：
                    显示“睁眼数据采集中”
                    * 激活期开始时刻记为 marker（start_time）
              - 3s：语音“采集完成” + 文本
          2) 闭眼块：
              - 3s：语音“请闭眼” + 文本
              - 激活期 close_duration 秒：
                    显示“闭眼数据采集中”
                    * 激活期开始时刻记为 marker（start_time）
              - 3s：语音“采集完成” + 文本
      - 所有块结束：
          - 10s：“X秒后实验结束” 倒计时
          - 写日志 + 重置界面

    日志每行：
      start_time,end_time,condition,duration=激活期秒数
      时间单位为秒，保留 3 位小数，相对 Start 点击时刻。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("睁眼 vs 闭眼 实验")
        self.setMinimumSize(900, 700)

        # ------------ 默认参数 ------------
        self.initial_countdown = 10  # 实验前倒计时（秒）
        self.end_countdown = 10  # 实验结束倒计时（秒）
        self.open_duration = 10  # 睁眼激活期默认时长
        self.close_duration = 10  # 闭眼激活期默认时长
        self.default_cycles = 5  # 每循环包含：睁眼 + 闭眼

        # 条件标签
        self.condition_open = "eye_open"
        self.condition_closed = "eye_closed"

        # ------------ 状态变量 ------------
        self.name = ""
        self.cycles = self.default_cycles
        self.block_plan = []  # ["睁眼","闭眼", "睁眼","闭眼", ...]
        self.block_index = -1
        self.current_condition = None

        self.logical_ms = 0  # 逻辑时间（毫秒），Start=0
        self.trial_logs = []  # 每个激活期记录

        self._countdown_timer = None

        # 语音引擎
        self.tts = QTextToSpeech(self) if QTextToSpeech is not None else None

        # ------------ UI ------------
        root = QVBoxLayout(self)
        root.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        # 说明
        self.instruction = QLabel(
            "填写信息后点击开始。\n"
            "本实验交替采集【睁眼】与【闭眼】状态下的EEG信号。\n"
            "按下 Start 即视为时间零点，请同步启动 EEG 记录。"
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

        self.cycles_spin = QSpinBox()
        self.cycles_spin.setRange(1, 100)
        self.cycles_spin.setValue(self.default_cycles)
        form.addRow("Runs（每次包含：睁眼 + 闭眼）:", self.cycles_spin)

        self.open_spin = QSpinBox()
        self.open_spin.setRange(1, 600)
        self.open_spin.setValue(self.open_duration)
        form.addRow("睁眼激活期时长 (秒):", self.open_spin)

        self.close_spin = QSpinBox()
        self.close_spin.setRange(1, 600)
        self.close_spin.setValue(self.close_duration)
        form.addRow("闭眼激活期时长 (秒):", self.close_spin)

        

        root.addWidget(settings)
        self.settings_widget = settings

        # 开始按钮
        self.start_btn = QPushButton("开始实验")
        self.start_btn.clicked.connect(self.on_start_clicked)
        root.addWidget(self.start_btn, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        # 大文本标签
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

        # ESC 中断快捷键
        self.esc_shortcut = QShortcut(QKeySequence(QtCore.Qt.Key.Key_Escape), self)
        self.esc_shortcut.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
        self.esc_shortcut.activated.connect(self.abort_and_finalize)

    # ------------ 开始入口 ------------

    def on_start_clicked(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "错误", "请输入姓名！")
            return

        open_dur = self.open_spin.value()
        close_dur = self.close_spin.value()
        cycles = self.cycles_spin.value()

        if open_dur <= 0 or close_dur <= 0:
            QMessageBox.warning(self, "错误", "激活期时长必须大于0秒。")
            return

        self.name = name
        self.open_duration = open_dur
        self.close_duration = close_dur
        self.cycles = cycles

        # 生成 block 计划：固定顺序 [睁眼, 闭眼] * cycles
        self.block_plan = []
        for _ in range(self.cycles):
            self.block_plan.append(self.condition_open)
            self.block_plan.append(self.condition_closed)

        self.block_index = -1
        self.trial_logs = []
        self.logical_ms = 0  # Start 时刻 = 0

        # 隐藏配置界面
        self.instruction.hide()
        self.start_btn.hide()
        self.settings_widget.hide()

        # 初始 10 秒倒计时（时间从此开始计）
        self._show_fullscreen_message(
            "{n}秒后将开始实验",
            self.initial_countdown,
            plain=True,
            next_callback=self._after_initial_countdown,
        )

    def _after_initial_countdown(self):
        # 完成初始倒计时，逻辑时间前进
        self.logical_ms += self.initial_countdown * 1000
        # 进入第一个区块之前的语音提示
        self._start_next_block_pre_voice()

    # ------------ Block 流程 ------------

    def _start_next_block_pre_voice(self):
        self.block_index += 1

        # 所有 block 完成，进入结束倒计时
        if self.block_index >= len(self.block_plan):
            self._show_fullscreen_message(
                "{n}秒后实验结束",
                self.end_countdown,
                plain=True,
                next_callback=self._finish_and_save,
            )
            return

        self.current_condition = self.block_plan[self.block_index]

        if self.current_condition == self.condition_open:
            text = "请睁眼"
        else:
            text = "请闭眼"

        self._speak(text)

        # 3 秒前置提示
        self._show_fullscreen_message(
            text,
            3,
            bg="#ffec99",
            fg="#000000",
            plain=False,
            next_callback=self._start_activation,
        )

    def _start_activation(self):
        # 前置提示 3s 完成，推进逻辑时间
        self.logical_ms += 3 * 1000

        if self.current_condition == self.condition_open:
            dur = self.open_duration
            label = "睁眼数据采集中"
        else:
            dur = self.close_duration
            label = "闭眼数据采集中"

        start_ms = self.logical_ms
        end_ms = start_ms + int(dur * 1000)

        # 记录激活期（marker 在开始）
        self.trial_logs.append(
            {
                "condition": self.current_condition,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "duration": int(dur),
            }
        )

        # 显示采集中文案
        self._apply_bg("#ffffff")
        self._apply_fg("#000000")
        self.stage_label.setText(label)
        self.stage_label.show()
        self.countdown_label.hide()

        # 激活期结束后进入 _activation_done
        QtCore.QTimer.singleShot(int(dur * 1000), self._activation_done)

    def _activation_done(self):
        # 激活期结束，对齐逻辑时间
        last = self.trial_logs[-1]
        self.logical_ms = last["end_ms"]

        done_text = "采集完成"
        self._speak(done_text)

        # 3 秒“采集完成”提示
        self._show_fullscreen_message(
            done_text,
            3,
            bg="#e6ffea",
            fg="#000000",
            plain=False,
            next_callback=self._after_post_voice,
        )

    def _after_post_voice(self):
        # 完成提示 3s 结束，推进时间
        self.logical_ms += 3 * 1000
        # 进入下一个 block
        self._start_next_block_pre_voice()

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
        显示全屏文本+可选倒计时。
        - template_or_text: 可包含 {n}，会替换为剩余秒数。
        - seconds: 总秒数。
        - plain=True: 清除背景样式（用于黑屏+文字）。
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

        # 初始文本
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
        """跨平台语音：优先 QTextToSpeech，没有则静默。"""
        if self.tts is not None:
            self.tts.say(text)

    # ------------ 结束 & 中断 ------------

    def _finish_and_save(self):
        # 结束倒计时也计入逻辑时间（如需）
        self.logical_ms += self.end_countdown * 1000
        self._save_report()
        self._reset_ui()

    def abort_and_finalize(self):
        # ESC 中断：保存已有数据
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
        # 停掉倒计时
        if self._countdown_timer is not None:
            self._countdown_timer.stop()
            self._countdown_timer.deleteLater()
            self._countdown_timer = None

        self._clear_styles()
        self.stage_label.hide()
        self.countdown_label.hide()

        # 恢复配置
        self.name_input.clear()
        self.instruction.show()
        self.start_btn.show()
        self.settings_widget.show()

        # 状态复位
        self.block_index = -1
        self.block_plan = []
        self.trial_logs = []
        self.logical_ms = 0


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = Page9Widget()
    w.show()
    sys.exit(app.exec())
