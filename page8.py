# page8.py
import os
import sys
import random
from datetime import datetime
from PyQt6 import QtCore
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QDoubleSpinBox,
    QPushButton,
    QMessageBox,
    QComboBox,
)
from PyQt6.QtGui import QKeySequence, QShortcut


class Page8Widget(QWidget):  # 这里没有run的概念
    """
    EEG 实验范式（2 条 Task：手臂抬起、静止）。

    时间记录逻辑：
    - 点击“开始实验”后，立刻调用 Page2 的 start_saving(run_dir) 开始写 EEG CSV；
      run_dir = data/arm/<Name>/<YYYYMMDDHHMMSS>。
    - 每个 trial 的 Task 阶段：
        * Task 开始时，从 Page2 获取片上时间，记为 task_start_hw（秒）。
        * Task 结束、进入自评前，再获取片上时间，记为 task_end_hw（秒）。
      这两个时间写入 txt 每行的前两列，可直接和 CSV 中的 Time 列对齐。
    - 所有 trial 完成后，还有一段“X 秒后实验结束”的倒计时，等倒计时结束后，
      调用 Page2 的 stop_saving()，然后写 txt 日志到 run_dir 下。
    - ESC 中断时，也会 stop_saving()，并写 ABORT 日志。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("EEG 实验范式（手臂抬起/静止）")
        self.setMinimumSize(900, 700)

        # ====== 数据目录：data/arm/<Name>/<timestamp> ======
        self.data_root = "data"
        self.arm_root = os.path.join(self.data_root, "miul")
        os.makedirs(self.arm_root, exist_ok=True)

        # 当前被试 & 本次实验 run 的目录
        self.current_user_name: str | None = None
        self.user_dir: str | None = None       # data/arm/<name>
        self.run_dir: str | None = None        # data/arm/<name>/<timestamp>
        self.run_timestamp: str | None = None  # YYYYMMDDHHMMSS

        # ------- 默认参数 -------
        self.initial_countdown = 10
        self.prompt_duration = 4.0
        self.task_min = 5.0
        self.task_max = 6.0
        self.assess_duration = 5.0
        self.break_duration = 5.0
        self.end_countdown = 10
        self.default_trials = 12  # 必须是 2 的倍数
        self.conditions = ["手臂抬起", "静止"]

        # Likert 标签
        self.likert_labels_3 = {1: "不同意", 2: "一般", 3: "同意"}
        self.likert_labels_5 = {
            1: "非常不同意",
            2: "不同意",
            3: "一般",
            4: "同意",
            5: "非常同意",
        }

        # ------- 状态量 -------
        self.name = ""
        self.total_trials = self.default_trials
        self.trial_index = -1
        self.trial_plan = []
        self.current_condition = None

        self.trial_logs = []
        self.pending_rating = None
        self.is_assessing = False
        self._assess_timer = None
        self._assess_remaining = 0

        self._task_timer = None
        self._task_remaining_secs = 0
        # 逻辑时间线仅内部计数，不再写入日志
        self.logical_ms = 0

        self.scale_points = 5
        self.scale_labels = self.likert_labels_5

        # ===== 与 EEG 采集页面（Page2）联动 =====
        # 在主程序中需要： page8.eeg_page = page2
        self.eeg_page = None
        self.hw_exp_start = None
        self.hw_exp_end = None

        # ------- UI -------
        root = QVBoxLayout(self)
        root.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        self.instruction = QLabel(
            "填写信息后点击开始。\n"
            "阶段：提示 → 任务 → 自我评估 → 休息；\n"
            "自评阶段请使用数字键或点击按钮评分。"
        )
        f = self.instruction.font()
        f.setPointSize(13)
        self.instruction.setFont(f)
        self.instruction.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.instruction.setWordWrap(True)
        root.addWidget(self.instruction)

        # 表单
        settings = QWidget()
        settings.setMaximumWidth(520)
        form = QFormLayout(settings)
        form.setFormAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        self.name_input = QLineEdit()
        form.addRow("姓名:", self.name_input)

        self.trials_spin = QSpinBox()
        self.trials_spin.setRange(2, 4000)
        self.trials_spin.setSingleStep(2)  # 只能以 2 步增减
        self.trials_spin.setValue(self.default_trials)
        form.addRow("循环次数(Trials):", self.trials_spin)

        self.prompt_spin = QSpinBox()
        self.prompt_spin.setRange(1, 100)
        self.prompt_spin.setValue(int(self.prompt_duration))
        form.addRow("Prompt 时长 (秒):", self.prompt_spin)

        task_box = QHBoxLayout()
        self.task_min_spin = QSpinBox()
        self.task_min_spin.setRange(1, 120)
        self.task_min_spin.setValue(int(self.task_min))
        self.task_max_spin = QSpinBox()
        self.task_max_spin.setRange(1, 120)
        self.task_max_spin.setValue(int(self.task_max))
        task_box.addWidget(QLabel("Task 区间 (秒):"))
        task_box.addWidget(self.task_min_spin)
        task_box.addWidget(self.task_max_spin)
        form.addRow(task_box)

        self.assess_spin = QDoubleSpinBox()
        self.assess_spin.setDecimals(0)
        self.assess_spin.setRange(1, 120)
        self.assess_spin.setValue(self.assess_duration)
        form.addRow("Self-assessment 时长 (秒):", self.assess_spin)

        self.break_spin = QDoubleSpinBox()
        self.break_spin.setDecimals(0)
        self.break_spin.setRange(1, 300)
        self.break_spin.setValue(self.break_duration)
        form.addRow("Break 时长 (秒):", self.break_spin)

        self.scale_combo = QComboBox()
        self.scale_combo.addItem("1 - 3（不同意 / 一般 / 同意）", 3)
        self.scale_combo.addItem("1 - 5（非常不同意 → 非常同意）", 5)
        self.scale_combo.setCurrentIndex(1)  # 默认 5 点
        form.addRow("自评量表:", self.scale_combo)

        self.start_btn = QPushButton("开始实验")
        self.start_btn.clicked.connect(self.on_start_clicked)

        root.addWidget(settings)
        root.addWidget(self.start_btn, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        # 大显示区
        self.stage_label = QLabel("")
        fs = self.stage_label.font()
        fs.setPointSize(42)
        self.stage_label.setFont(fs)
        self.stage_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.stage_label.hide()
        root.addWidget(self.stage_label)

        self.countdown_label = QLabel("")
        fc = self.countdown_label.font()
        fc.setPointSize(32)
        self.countdown_label.setFont(fc)
        self.countdown_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.countdown_label.hide()
        root.addWidget(self.countdown_label)

        self.cross_label = QLabel("+")
        fx = self.cross_label.font()
        fx.setPointSize(160)
        fx.setBold(True)
        self.cross_label.setFont(fx)
        self.cross_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.cross_label.hide()
        root.addWidget(self.cross_label)

        # Task 倒计时标签（保留用于样式统一）
        self.task_count_label = QLabel("")
        ft = self.task_count_label.font()
        ft.setPointSize(48)
        ft.setBold(True)
        self.task_count_label.setFont(ft)
        self.task_count_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.task_count_label.hide()
        root.addWidget(self.task_count_label)

        # 自评分按钮（最多 5 个）
        btn_box = QVBoxLayout()
        self.rating_btns = []
        for val in (1, 2, 3, 4, 5):
            b = QPushButton(str(val))
            b.setStyleSheet("color: black; padding: 10px 16px;")
            b.setVisible(False)
            b.clicked.connect(lambda _, v=val: self.record_rating(v))
            self.rating_btns.append(b)
            btn_box.addWidget(b, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)
        root.addLayout(btn_box)

        # 快捷键 1~5
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.shortcuts = []
        for key in [
            QtCore.Qt.Key.Key_1,
            QtCore.Qt.Key.Key_2,
            QtCore.Qt.Key.Key_3,
            QtCore.Qt.Key.Key_4,
            QtCore.Qt.Key.Key_5,
        ]:
            sc = QShortcut(QKeySequence(key), self)
            sc.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
            sc.activated.connect(
                lambda k=key: self._shortcut_record(int(k) - int(QtCore.Qt.Key.Key_0))
            )
            self.shortcuts.append(sc)

        # ESC 中断保存
        self.shortcut_esc = QShortcut(QKeySequence(QtCore.Qt.Key.Key_Escape), self)
        self.shortcut_esc.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
        self.shortcut_esc.activated.connect(self.abort_and_finalize)

    # ------- 入口 -------
    def on_start_clicked(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "错误", "请输入姓名！")
            return

        trials = self.trials_spin.value()
        if trials % 2 != 0:
            QMessageBox.warning(self, "错误", "循环次数必须为2的倍数！")
            return

        # 先检查 EEG Page2 是否在监听
        eeg_page = getattr(self, "eeg_page", None)
        if eeg_page is None or not hasattr(eeg_page, "is_listening"):
            QMessageBox.warning(
                self,
                "错误",
                "未找到 EEG 采集页面，请在主程序中确保已创建并注入 Page2Widget。"
            )
            return

        if not eeg_page.is_listening():
            QMessageBox.warning(
                self,
                "提示",
                "请先在【首页】点击“开始监测信号”，\n"
                "确保已经开始接收EEG数据后，再启动本实验范式。"
            )
            return

        p = int(self.prompt_spin.value())
        tmin = int(self.task_min_spin.value())
        tmax = int(self.task_max_spin.value())
        ta = int(self.assess_spin.value())
        tb = int(self.break_spin.value())
        if tmin > tmax:
            QMessageBox.warning(self, "错误", "Task 区间无效：最小值不能大于最大值。")
            return

        self.prompt_duration = p
        self.task_min = tmin
        self.task_max = tmax
        self.assess_duration = ta
        self.break_duration = tb

        self.scale_points = int(self.scale_combo.currentData())
        self.scale_labels = (
            self.likert_labels_3 if self.scale_points == 3 else self.likert_labels_5
        )

        self.name = name
        self.total_trials = trials

        # 分块均衡随机（每个 block 含一次“手臂抬起”和一次“静止”，顺序打乱）
        self.trial_plan = self._make_balanced_plan(self.total_trials, self.conditions)

        # ===== 构建目录：data/arm/<name>/<timestamp>/ =====
        self.current_user_name = name
        self.user_dir = os.path.join(self.arm_root, self.current_user_name)
        os.makedirs(self.user_dir, exist_ok=True)

        self.run_timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        self.run_dir = os.path.join(self.user_dir, self.run_timestamp)
        os.makedirs(self.run_dir, exist_ok=True)

        # ===== 启动 EEG CSV 记录（从点击“开始实验”这一刻起） =====
        self.hw_exp_start = None
        self.hw_exp_end = None
        try:
            if hasattr(eeg_page, "start_saving"):
                # 把本次实验 run_dir 传给 Page2，让 EEG CSV 写到这里
                eeg_page.start_saving(self.run_dir)
        except Exception:
            # 即使保存出错，也不影响范式本身运行
            pass

        # 记录整体实验起始片上时间
        first_hw = self._get_hw_timestamp_from_eeg()
        if first_hw is not None:
            self.hw_exp_start = first_hw

        # UI 切换
        self.instruction.hide()
        self.start_btn.hide()
        self.name_input.parent().hide()
        self.trial_logs = []
        self.trial_index = -1
        self.logical_ms = int(self.initial_countdown * 1000)

        # 初始倒计时
        self._show_fullscreen_message(
            "{n}秒后将开始实验",
            self.initial_countdown,
            plain=True,
            next_callback=self._start_next_trial,
        )

    # ------- 流程 -------
    def _start_next_trial(self):
        self.trial_index += 1
        if self.trial_index >= len(self.trial_plan):
            # 所有 trial 完成后，进入结束倒计时
            self._show_fullscreen_message(
                "{n}秒后实验结束",
                self.end_countdown,
                plain=True,
                next_callback=self._finish_and_save,
            )
            return

        self.current_condition = self.trial_plan[self.trial_index]
        self.pending_rating = None
        self.is_assessing = False
        self._stop_assess_timer()
        self._stop_task_timer()

        prompt_ms = int(self.prompt_duration * 1000)
        task_sec = int(
            random.randint(
                min(int(self.task_min), int(self.task_max)),
                max(int(self.task_min), int(self.task_max)),
            )
        )
        task_ms = task_sec * 1000
        assess_ms = int(self.assess_duration * 1000)
        break_ms = int(self.break_duration * 1000)

        task_start_ms = self.logical_ms + prompt_ms
        task_end_ms = task_start_ms + task_ms

        self.trial_logs.append(
            {
                "condition": self.current_condition,
                "task_start_ms": task_start_ms,
                "task_end_ms": task_end_ms,
                "task_start_hw": None,  # Task 开始片上时间（秒）
                "task_end_hw": None,    # Task 结束片上时间（秒）
                "durations": {
                    "prompt": int(self.prompt_duration),
                    "task": int(task_sec),
                    "assess": int(self.assess_duration),
                    "break": int(self.break_duration),
                },
                "rating": None,
                "rating_label": None,
                "scale_points": self.scale_points,
                "total_ms": prompt_ms + task_ms + assess_ms + break_ms,
            }
        )

        # Prompt
        if self.current_condition == "静止":
            prompt_text = "接下来请保持【静止】，不要想象运动"
        else:
            prompt_text = "接下来请想象【手臂抬起】"

        self._show_stage(
            prompt_text,
            int(self.prompt_duration),
            bg="#ffec99",
            fg="#000000",
            next_stage=self._stage_task,
        )

    def _stage_task(self):
        if self.current_condition == "静止":
            task_text = "请保持【静止】，不要想象运动"
        else:
            task_text = "请想象【手臂抬起】"

        # ===== Task 阶段开始：记录片上时间 =====
        self._record_task_start_hw_for_current_trial()

        # 不展示 task 倒计时；仅显示注视十字，时长到点自动进入评估
        self.cross_label.show()
        dur = int(self.trial_logs[-1]["durations"]["task"])
        self._show_stage(
            task_text,
            dur,
            bg="#ffffff",
            fg="#000000",
            next_stage=self._enter_assess,
            show_cross=True,
        )

    def _enter_assess(self):
        # ===== Task 阶段结束：记录片上时间 =====
        self._record_task_end_hw_for_current_trial()

        self.cross_label.hide()
        self.task_count_label.hide()
        self._stop_task_timer()
        self._stage_assess()

    def _stage_assess(self):
        self.is_assessing = True
        self._assess_remaining = int(self.assess_duration)
        self._setup_rating_controls()

        self._apply_bg("#bde0fe")
        self._apply_fg("#000000")
        self.countdown_label.hide()
        self.stage_label.show()
        self._update_assess_text()

        self._stop_assess_timer()
        self._assess_timer = QtCore.QTimer(self)
        self._assess_timer.timeout.connect(self._tick_assess)
        self._assess_timer.start(1000)

    def _setup_rating_controls(self):
        labels = self.scale_labels
        for idx, b in enumerate(self.rating_btns, start=1):
            if idx <= self.scale_points:
                b.setText(f"{idx}. {labels[idx]}")
                b.setVisible(True)
            else:
                b.setVisible(False)

    def _tick_assess(self):
        self._assess_remaining -= 1
        if self._assess_remaining > 0:
            if self.pending_rating is None:
                self._update_assess_text()
        else:
            self._stop_assess_timer()
            self._stage_break()

    def _current_assess_question(self) -> str:
        if self.current_condition == "手臂抬起":
            return "刚刚是否认真在想象手臂抬起？"
        else:
            return "刚刚是否什么都没想？"

    def _update_assess_text(self):
        assess_text = (
            f"{self._current_assess_question()}\n请在 {self._assess_remaining} 秒内作答"
        )
        self.stage_label.setText(assess_text)

    def _stage_break(self):
        self.is_assessing = False
        for b in self.rating_btns:
            b.setVisible(False)

        self.trial_logs[-1]["rating"] = self.pending_rating
        if self.pending_rating is not None:
            self.trial_logs[-1]["rating_label"] = self.scale_labels.get(self.pending_rating)

        self._show_fullscreen_message(
            "请休息{n}秒",
            int(self.break_duration),
            bg="#e6ffea",
            fg="#000000",
            next_callback=self._finalize_trial_and_continue,
        )

    def _finalize_trial_and_continue(self):
        self.logical_ms += self.trial_logs[-1]["total_ms"]
        self._start_next_trial()

    # ------- 显示与计时 -------
    def _show_stage(self, text, seconds, bg, fg, next_stage=None, show_cross=False):
        self._apply_bg(bg)
        self._apply_fg(fg)
        self.stage_label.setText(text)
        self.stage_label.show()
        self.countdown_label.hide()
        if not show_cross:
            self.cross_label.hide()
        QtCore.QTimer.singleShot(int(seconds * 1000), next_stage)

    def _show_fullscreen_message(
        self,
        template,
        seconds,
        bg=None,
        fg=None,
        plain=False,
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
        self.task_count_label.hide()
        self.cross_label.hide()
        self.countdown_label.show()
        self._countdown_value = int(seconds)
        self._countdown_template = template
        self.countdown_label.setText(template.format(n=self._countdown_value))
        self._countdown_updater = QtCore.QTimer(self)
        self._countdown_updater.timeout.connect(
            lambda: self._tick(next_callback)
        )
        self._countdown_updater.start(1000)

    def _tick(self, next_callback):
        self._countdown_value -= 1
        if self._countdown_value > 0:
            self.countdown_label.setText(
                self._countdown_template.format(n=self._countdown_value)
            )
        else:
            self._countdown_updater.stop()
            self.countdown_label.hide()
            if callable(next_callback):
                next_callback()

    def _apply_bg(self, color):
        self.setStyleSheet(f"background-color:{color};")

    def _apply_fg(self, color):
        self.stage_label.setStyleSheet(f"color:{color};")
        self.countdown_label.setStyleSheet(f"color:{color};")
        self.cross_label.setStyleSheet(f"color:{color};")
        self.task_count_label.setStyleSheet(f"color:{color};")

    def _clear_styles(self):
        self.setStyleSheet("")
        self.stage_label.setStyleSheet("")
        self.countdown_label.setStyleSheet("")
        self.cross_label.setStyleSheet("")
        self.task_count_label.setStyleSheet("")

    def _stop_assess_timer(self):
        if self._assess_timer is not None:
            try:
                self._assess_timer.stop()
                self._assess_timer.deleteLater()
            except Exception:
                pass
            self._assess_timer = None

    def _stop_task_timer(self):
        if self._task_timer is not None:
            try:
                self._task_timer.stop()
                self._task_timer.deleteLater()
            except Exception:
                pass
            self._task_timer = None

    def _shortcut_record(self, val: int):
        if 1 <= val <= self.scale_points:
            self.record_rating(val)

    def record_rating(self, value: int):
        if (
            self.is_assessing
            and self.pending_rating is None
            and 1 <= value <= self.scale_points
        ):
            self.pending_rating = int(value)
            for b in self.rating_btns:
                b.setVisible(False)
            label = self.scale_labels.get(value, "")
            self.stage_label.setText(
                f"已记录自我评分: {value}" + (f" - {label}" if label else "")
            )

    # ------- 与 Page2 的时间戳交互 -------
    def _get_hw_timestamp_from_eeg(self):
        """
        从 Page2 获取当前最新的片上时间戳（秒），若失败则返回 None。
        """
        eeg_page = getattr(self, "eeg_page", None)
        if eeg_page is None:
            return None
        getter = getattr(eeg_page, "get_last_hardware_timestamp", None)
        if getter is None:
            return None
        try:
            return getter()
        except Exception:
            return None

    def _record_task_start_hw_for_current_trial(self):
        """在 Task 阶段开始时调用，记录当前 trial 的片上开始时间。"""
        hw = self._get_hw_timestamp_from_eeg()
        if hw is None:
            return
        idx = self.trial_index
        if 0 <= idx < len(self.trial_logs):
            self.trial_logs[idx]["task_start_hw"] = hw
            if self.hw_exp_start is None:
                self.hw_exp_start = hw

    def _record_task_end_hw_for_current_trial(self):
        """在 Task 阶段结束（进入自评前）调用，记录当前 trial 的片上结束时间。"""
        hw = self._get_hw_timestamp_from_eeg()
        if hw is None:
            return
        idx = self.trial_index
        if 0 <= idx < len(self.trial_logs):
            self.trial_logs[idx]["task_end_hw"] = hw
            self.hw_exp_end = hw

    # ------- 结束与中断 -------
    def _finish_and_save(self):
        """
        正常完成所有 trial + 结束倒计时后调用：
        - 停止 EEG 保存
        - 写入报告
        - 重置 UI
        """
        eeg_page = getattr(self, "eeg_page", None)
        if eeg_page is not None:
            last_hw = self._get_hw_timestamp_from_eeg()
            if last_hw is not None:
                self.hw_exp_end = last_hw
            if hasattr(eeg_page, "stop_saving"):
                try:
                    eeg_page.stop_saving()
                except Exception:
                    pass

        self._save_report()
        self._reset_ui()

    def abort_and_finalize(self):
        """
        ESC 中断：
        - 尝试停止 EEG 保存
        - 写 ABORT 日志
        """
        eeg_page = getattr(self, "eeg_page", None)
        if eeg_page is not None:
            last_hw = self._get_hw_timestamp_from_eeg()
            if last_hw is not None:
                self.hw_exp_end = last_hw
            if hasattr(eeg_page, "stop_saving"):
                try:
                    eeg_page.stop_saving()
                except Exception:
                    pass

        self._save_report(aborted=True)
        self._reset_ui()

    def _reset_ui(self):
        self._clear_styles()
        self.stage_label.hide()
        self.countdown_label.hide()
        self.cross_label.hide()
        self.task_count_label.hide()
        for b in self.rating_btns:
            b.setVisible(False)
        self.instruction.show()
        self.start_btn.show()
        self.name_input.parent().show()
        self.name_input.setFocus()

        self.trial_index = -1
        self.trial_plan = []
        self.trial_logs = []
        self.pending_rating = None
        self.is_assessing = False
        self.logical_ms = 0
        self._stop_assess_timer()
        self._stop_task_timer()

        # 重置目录信息
        self.current_user_name = None
        self.user_dir = None
        self.run_dir = None
        self.run_timestamp = None

        # 重置时间信息
        self.hw_exp_start = None
        self.hw_exp_end = None

    # ------- 日志 -------
    def _save_report(self, aborted: bool = False):
        """
        每一行：
          task_start_hw,task_end_hw,condition,detail

        其中 detail 包含：
          prompt / task / assess / break 的逻辑秒数、
          量表点数、评分数值、评分文字。

        报告文件保存到：
          data/arm/<Name>/<YYYYMMDDHHMMSS>/EEGMI_*.txt
        """
        # 确定名称
        name = (
            self.current_user_name
            or self.name
            or self.name_input.text().strip()
            or "unknown"
        )

        flag = "ABORT" if aborted else "DONE"

        # 确定目录：优先 run_dir，其次 user_dir，最后 arm_root
        base_dir = self.run_dir or self.user_dir or self.arm_root
        os.makedirs(base_dir, exist_ok=True)

        # 文件名里的时间戳：优先 run_timestamp，兜底当前时间
        ts_for_name = self.run_timestamp or datetime.now().strftime("%Y%m%d%H%M%S")

        fname = os.path.join(
            base_dir,
            f"EEGMIUL_{name}_{ts_for_name}_trials{len(self.trial_logs)}_{flag}.txt",
        )

        try:
            with open(fname, "w", encoding="utf-8") as f:
                for rec in self.trial_logs:
                    start_hw = rec.get("task_start_hw")
                    end_hw = rec.get("task_end_hw")

                    if isinstance(start_hw, (int, float)):
                        t0 = float(start_hw)
                    else:
                        t0 = float("nan")

                    if isinstance(end_hw, (int, float)):
                        t1 = float(end_hw)
                    else:
                        t1 = float("nan")

                    cond = rec["condition"]
                    d = rec["durations"]
                    rating = rec["rating"] if rec["rating"] is not None else "None"
                    rating_label = rec.get("rating_label", "None")
                    detail = (
                        f"prompt={d['prompt']}|task={d['task']}|"
                        f"assess={d['assess']}|break={d['break']}|"
                        f"scale={rec.get('scale_points','NA')}|"
                        f"rating={rating}|rating_label={rating_label}"
                    )
                    f.write(f"{t0:.6f},{t1:.6f},{cond},{detail}\n")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"写入日志失败：{e}")

    @staticmethod
    def _make_balanced_plan(total_trials: int, conditions: list[str]) -> list[str]:
        """分块均衡随机：每个 block 含每个条件一次，block 内随机顺序。"""
        if not conditions:
            return []
        n = len(conditions)
        if total_trials % n != 0:
            raise ValueError(
                "total_trials must be a multiple of the number of conditions."
            )
        blocks = total_trials // n
        plan = []
        for _ in range(blocks):
            block = conditions[:]
            random.shuffle(block)
            plan.extend(block)
        return plan


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = Page8Widget()
    w.show()
    sys.exit(app.exec())
