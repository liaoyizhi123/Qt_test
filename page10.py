# page10.py - 眼电实验页面（与 Page9 相同的 marker 记录方式）

import sys
import os
import random
from datetime import datetime
from PyQt6 import QtCore, QtWidgets
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QLineEdit, QSpinBox, QPushButton, QMessageBox, QGroupBox, QScrollArea,
    QComboBox, QGridLayout
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QShortcut, QKeySequence

try:
    from PyQt6.QtTextToSpeech import QTextToSpeech
except ImportError:
    QTextToSpeech = None

# 眼部动作类型（condition 名称 = key）
EYE_MOVEMENTS = {
    'look_up': '向上看',
    'look_down': '向下看',
    'look_left': '向左看',
    'look_right': '向右看',
    'blink_2': '眨眼两次',
    'blink_3': '眨眼三次'
}


class Page10Widget(QWidget):
    """
    眼电范式（Run 级 + Trial 级设计）

    时间从“点击开始按钮”的时刻算起（t=0，逻辑时间 logical_ms）。

    每个 run 的结构（可配置）：
      - trial 按顺序依次执行：
          提示阶段（prompt_duration 秒，不记日志）
          动作阶段（action_duration 秒，记日志：condition 为动作类型）
      - run 间休息 rest_duration 秒（仅非最后一个 run，不记日志）

    日志一条对应一次“动作执行阶段”（activation）：
      start_sec,end_sec,condition,duration=秒,run=idx,segment=trial{序号}_action
    所有时间为逻辑时间（相对 Start 点击）。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("眼电信号采集实验（与 Page9 同步的 marker 格式）")
        self.setMinimumSize(960, 720)

        # ---------- 固定/默认参数 ----------
        self.initial_countdown = 5          # 实验开始前倒计时（秒）
        self.prompt_duration = 2            # 提示阶段时长（秒，不记日志）
        self.action_duration = 3            # 动作阶段时长（秒，记日志）
        self.rest_duration = 5              # run 间休息（秒，不记日志）
        self.default_runs = 3               # 默认 run 数量

        # ---------- 状态变量（与 Page9 一致的记录思路） ----------
        self.name = ""
        self.total_runs = self.default_runs
        self.current_run = 0                # 0-based
        self.current_trial = 0              # 0-based（run 内）
        self.logical_ms = 0                 # 逻辑时间：start 按下 = 0
        self.trial_logs = []                # 与 Page9 相同的列表结构

        self.trial_counts = {}              # 每类动作在每个 run 内的数量配置
        self.all_runs_sequences = []        # 全部 run 的 trial 序列（列表的列表）
        self.is_random_order = True

        self._countdown_timer = None

        # ---------- 可选语音 ----------
        self.tts = None
        self._init_tts()

        # ---------- UI ----------
        root = QVBoxLayout(self)
        root.setAlignment(Qt.AlignmentFlag.AlignTop)

        # 说明
        self.instruction = QLabel(
            "眼电信号采集实验（Page10）\n\n"
            "日志/marker 写法与 Page9 完全一致：仅在“动作执行阶段”记一条记录；\n"
            "提示与休息不记日志；所有时间均为 Start 后的逻辑时间。\n"
            "每个 Trial：提示 2s → 动作 3s（可更改）。"
        )
        f = self.instruction.font()
        f.setPointSize(12)
        self.instruction.setFont(f)
        self.instruction.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.instruction.setWordWrap(True)
        root.addWidget(self.instruction)

        # 配置区
        settings = QWidget()
        settings.setMaximumWidth(640)
        self.settings_widget = settings
        form_wrap = QVBoxLayout(settings)

        # 基本设置
        basic_group = QGroupBox("基本设置")
        basic_form = QFormLayout()

        self.name_input = QLineEdit()
        basic_form.addRow("受试者姓名:", self.name_input)

        self.runs_spin = QSpinBox()
        self.runs_spin.setRange(1, 99)
        self.runs_spin.setValue(self.default_runs)
        basic_form.addRow("Runs 数量:", self.runs_spin)

        # 时长设置
        self.prompt_spin = QSpinBox()
        self.prompt_spin.setRange(1, 60)
        self.prompt_spin.setValue(self.prompt_duration)
        basic_form.addRow("提示阶段时长（秒）:", self.prompt_spin)

        self.action_spin = QSpinBox()
        self.action_spin.setRange(1, 60)
        self.action_spin.setValue(self.action_duration)
        basic_form.addRow("动作阶段时长（秒）:", self.action_spin)

        self.rest_spin = QSpinBox()
        self.rest_spin.setRange(0, 600)
        self.rest_spin.setValue(self.rest_duration)
        basic_form.addRow("Run 间休息（秒）:", self.rest_spin)

        self.order_combo = QComboBox()
        self.order_combo.addItems(["随机顺序", "固定顺序"])
        basic_form.addRow("Trial 顺序:", self.order_combo)

        basic_group.setLayout(basic_form)
        form_wrap.addWidget(basic_group)

        # Trial 类型和数量
        trial_group = QGroupBox("每个 Run 内各动作 Trial 数量")
        trial_wrap = QVBoxLayout()
        trial_note = QLabel("0 表示该动作在每个 Run 内不出现")
        trial_note.setStyleSheet("color:#666; font-size:11px;")
        trial_wrap.addWidget(trial_note)

        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        self.trial_spin_boxes = {}
        row = 0
        for key, label in EYE_MOVEMENTS.items():
            lab = QLabel(label)
            spn = QSpinBox()
            spn.setRange(0, 50)
            spn.setValue(1)
            grid.addWidget(lab, row, 0)
            grid.addWidget(spn, row, 1)
            self.trial_spin_boxes[key] = spn
            row += 1

        self.total_trials_label = QLabel("每个 Run 总计: 6 个 Trials")
        self.total_trials_label.setStyleSheet("font-weight:bold; color:#0066cc;")
        grid.addWidget(self.total_trials_label, row, 0, 1, 2)

        for spn in self.trial_spin_boxes.values():
            spn.valueChanged.connect(self._update_total_trials)

        trial_wrap.addLayout(grid)
        trial_group.setLayout(trial_wrap)
        form_wrap.addWidget(trial_group)

        # 开始按钮
        self.start_btn = QPushButton("开始实验")
        self.start_btn.setMinimumHeight(40)
        self.start_btn.clicked.connect(self.on_start_clicked)
        form_wrap.addWidget(self.start_btn)

        # 滚动容器
        scroll = QScrollArea()
        scroll.setWidget(settings)
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(480)
        root.addWidget(scroll)

        # 进度/显示/倒计时
        self.progress_label = QLabel("")
        pf = self.progress_label.font()
        pf.setPointSize(14)
        pf.setBold(True)
        self.progress_label.setFont(pf)
        self.progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress_label.hide()
        root.addWidget(self.progress_label)

        self.stage_label = QLabel("")   # 大的动作显示
        sf = self.stage_label.font()
        sf.setPointSize(48)
        sf.setBold(True)
        self.stage_label.setFont(sf)
        self.stage_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stage_label.setMinimumHeight(360)
        self.stage_label.hide()
        root.addWidget(self.stage_label)

        self.countdown_label = QLabel("")
        cf = self.countdown_label.font()
        cf.setPointSize(28)
        self.countdown_label.setFont(cf)
        self.countdown_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.countdown_label.hide()
        root.addWidget(self.countdown_label)

        # ESC 中断
        self.esc_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self.esc_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self.esc_shortcut.activated.connect(self.abort_and_finalize)

    # ---------- 语音 ----------
    def _init_tts(self):
        if QTextToSpeech is None:
            return
        try:
            engines = QTextToSpeech.availableEngines()
        except Exception:
            return
        if not engines:
            return
        engine = "sapi" if sys.platform.startswith("win") and "sapi" in engines else engines[0]
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

    # ---------- 工具 ----------
    def _update_total_trials(self):
        total = sum(sp.value() for sp in self.trial_spin_boxes.values())
        if total == 0:
            self.total_trials_label.setText("每个 Run 总计: 0 个 Trials")
            self.total_trials_label.setStyleSheet("font-weight:bold; color:red;")
        else:
            self.total_trials_label.setText(f"每个 Run 总计: {total} 个 Trials")
            self.total_trials_label.setStyleSheet("font-weight:bold; color:#0066cc;")

    def _apply_bg(self, color: str):
        self.setStyleSheet(f"background-color:{color};")

    def _apply_fg(self, color: str):
        self.stage_label.setStyleSheet(f"color:{color};")
        self.countdown_label.setStyleSheet(f"color:{color};")

    def _clear_styles(self):
        self.setStyleSheet("")
        self.stage_label.setStyleSheet("")
        self.countdown_label.setStyleSheet("")

    # 倒计时/全屏消息（与 Page9 同款逻辑）
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

        txt = (
            template_or_text.format(n=self._countdown_value)
            if "{n}" in template_or_text else template_or_text
        )
        self.countdown_label.setText(txt)

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
            txt = (
                self._countdown_template.format(n=self._countdown_value)
                if "{n}" in self._countdown_template else self._countdown_template
            )
            self.countdown_label.setText(txt)
        else:
            if self._countdown_timer is not None:
                self._countdown_timer.stop()
                self._countdown_timer.deleteLater()
                self._countdown_timer = None
            self.countdown_label.hide()
            if callable(next_callback):
                next_callback()

    # ---------- 开始 ----------
    def on_start_clicked(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "错误", "请输入受试者姓名！")
            return

        # 每个 run 的 total trials 必须 > 0
        per_run_total = sum(sp.value() for sp in self.trial_spin_boxes.values())
        if per_run_total == 0:
            QMessageBox.warning(self, "错误", "请至少为某一类设置 1 个 Trial！")
            return

        self.name = name
        self.total_runs = self.runs_spin.value()
        self.prompt_duration = self.prompt_spin.value()
        self.action_duration = self.action_spin.value()
        self.rest_duration = self.rest_spin.value()
        self.is_random_order = (self.order_combo.currentIndex() == 0)

        # 读取 trial 数量配置
        self.trial_counts = {}
        for k, sp in self.trial_spin_boxes.items():
            c = sp.value()
            if c > 0:
                self.trial_counts[k] = c

        # 状态复位
        self.current_run = 0
        self.current_trial = 0
        self.logical_ms = 0
        self.trial_logs = []
        self.all_runs_sequences = self._generate_all_sequences()

        # UI 切换
        self.instruction.hide()
        self.settings_widget.hide()
        self.start_btn.hide()
        self.progress_label.show()
        self.stage_label.show()

        # 初始倒计时
        self._show_fullscreen_message(
            "{n}秒后将开始实验",
            self.initial_countdown,
            plain=True,
            next_callback=self._after_initial_countdown,
        )

    def _after_initial_countdown(self):
        self.logical_ms += self.initial_countdown * 1000
        self._start_run()

    # ---------- Run 流程 ----------
    def _generate_all_sequences(self):
        base = []
        for trial_type, cnt in self.trial_counts.items():
            base.extend([trial_type] * cnt)
        seqs = []
        for _ in range(self.total_runs):
            s = base.copy()
            if self.is_random_order:
                random.shuffle(s)
            seqs.append(s)
        return seqs

    def _start_run(self):
        if self.current_run >= self.total_runs:
            self._finish_and_save()
            return

        # 取到本 run 的 trial 序列
        self.trials_in_run = self.all_runs_sequences[self.current_run]
        self.current_trial = 0
        self.progress_label.setText(f"Run {self.current_run + 1}/{self.total_runs}")

        # 直接进入第一个 trial 的提示阶段
        QtCore.QTimer.singleShot(300, self._trial_prompt)

    def _trial_prompt(self):
        if self.current_trial >= len(self.trials_in_run):
            self._after_run_trials()
            return

        trial_type = self.trials_in_run[self.current_trial]
        trial_name = EYE_MOVEMENTS[trial_type]

        # 提示阶段（不记日志）
        self._apply_bg("#eef3ff")
        self._apply_fg("#003366")
        self.stage_label.setText(f"准备：{trial_name}")
        self._speak(f"准备，{trial_name}")

        # 提示阶段结束后进入动作阶段，推进逻辑时间
        QtCore.QTimer.singleShot(
            int(self.prompt_duration * 1000),
            self._trial_action
        )

    def _trial_action(self):
        # 提示阶段结束：推进逻辑时间
        self.logical_ms += int(self.prompt_duration * 1000)

        trial_type = self.trials_in_run[self.current_trial]
        trial_name = EYE_MOVEMENTS[trial_type]

        # 记录一次“动作执行阶段”的激活期（与 Page9 一致的结构）
        dur = float(self.action_duration)
        start_ms = self.logical_ms
        end_ms = start_ms + int(dur * 1000)

        self.trial_logs.append(
            {
                "condition": trial_type,                   # 条件名 = 动作类型（如 look_up）
                "start_ms": start_ms,
                "end_ms": end_ms,
                "duration": dur,                           # 秒
                "run": self.current_run + 1,
                "segment": f"trial{self.current_trial + 1}_action",
            }
        )

        # 显示动作阶段
        self._apply_bg("#ffffff")
        self._apply_fg("#000000")
        img_path = rf"resources\eog_images\{trial_type}.png"
        if os.path.exists(img_path):
            pm = QPixmap(img_path).scaled(
                600, 600,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.stage_label.setPixmap(pm)
            self.stage_label.setText("")  # 清掉文字
        else:
            self.stage_label.setPixmap(QPixmap())  # 清图片
            self.stage_label.setText(trial_name)

        # 动作阶段结束
        QtCore.QTimer.singleShot(int(dur * 1000), self._after_action)

    def _after_action(self):
        # 动作结束：推进逻辑时间至该激活期结束
        self.logical_ms = self.trial_logs[-1]["end_ms"]

        # 进入下一个 trial
        self.current_trial += 1
        QtCore.QTimer.singleShot(300, self._trial_prompt)

    def _after_run_trials(self):
        # 本 run 的所有 trial 完成
        self.current_run += 1

        # 最后一个 run：不休息，直接结束
        if self.current_run >= self.total_runs:
            self._finish_and_save()
            return

        # 非最后一个 run：休息（不记日志）
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
            self._start_run()

    def _after_rest(self):
        # 休息结束，推进逻辑时间
        self.logical_ms += int(self.rest_duration * 1000)
        self._start_run()

    # ---------- 结束 & 中断 ----------
    def _finish_and_save(self):
        self._save_report()
        self._reset_ui()

    def abort_and_finalize(self):
        self._save_report(aborted=True)
        self._reset_ui()

    def _save_report(self, aborted: bool = False):
        """写出与 Page9 完全一致的逐行文本格式。"""
        if not self.trial_logs:
            return
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        flag = "ABORT" if aborted else "DONE"
        # 如需完全对齐 Page9 的文件名前缀，可把 'EOG' 改成 'EyeOpenClose'
        fname = f"EOG_{self.name}_{ts}_runs{self.total_runs}_{flag}.txt"
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
        self.progress_label.hide()

        # 恢复配置区
        self.name_input.clear()
        self.instruction.show()
        self.settings_widget.show()
        self.start_btn.show()

        # 状态复位
        self.current_run = 0
        self.current_trial = 0
        self.logical_ms = 0
        self.trial_logs = []
        self.all_runs_sequences = []
        self.trial_counts = {}


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = Page10Widget()
    w.show()
    sys.exit(app.exec())
