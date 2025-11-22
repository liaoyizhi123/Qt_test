import os
import sys
import random
from datetime import datetime
from PyQt6 import QtCore, QtGui, QtWidgets
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


class Page7Widget(QWidget):  # 这里没有run的概念·``
    """
    EEG 实验范式单页组件（4 条 Task：慢走、慢跑、快跑、静止）。

    现在的时间记录逻辑：
    - 点击「开始实验」后立刻调用 Page2 开始保存 EEG（4 个 CSV）。
    - 对每个 trial 的 Task 激活阶段，在 Task 开始/结束时从 Page2 获取片上时间，
      写入日志的第 1 / 2 列（单位：秒），可以直接在 CSV 的 Time 列中精确对齐。
    - 实验最后的结束倒计时结束后，调用 Page2 停止保存，再写 txt 报告。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("EEG 实验范式")
        self.setMinimumSize(900, 700)

        # ====== MI 数据根目录：data/mi ======
        self.data_root = "data"
        self.mi_root = os.path.join(self.data_root, "mill")
        os.makedirs(self.mi_root, exist_ok=True)

        # 当前被试 & 本次实验 run 的目录
        self.current_user_name: str | None = None
        self.user_dir: str | None = None  # data/mi/<name>
        self.run_dir: str | None = None  # data/mi/<name>/<timestamp>
        self.run_timestamp: str | None = None  # YYYYMMDDHHMMSS

        # -------------------- 默认参数 --------------------
        self.initial_countdown = 10  # 实验开始前倒计时（秒）
        self.prompt_duration = 4.0  # 默认 Prompt 时长（秒）
        self.task_min = 5.0  # 默认 Task 最小（秒）
        self.task_max = 6.0  # 默认 Task 最大（秒）
        self.assess_duration = 5.0  # 默认自评时长（秒）
        self.break_duration = 5.0  # 默认休息时长（秒）
        self.end_countdown = 10  # 全部结束后的倒计时（秒）
        self.default_trials = 16  # 默认循环次数（4 的倍数）
        self.conditions = ["慢走", "慢跑", "快跑", "静止"]

        # Likert 标签
        self.likert_labels_3 = {1: "不同意", 2: "一般", 3: "同意"}
        self.likert_labels_5 = {
            1: "非常不同意",
            2: "不同意",
            3: "一般",
            4: "同意",
            5: "非常同意",
        }

        # -------------------- 状态量 --------------------
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

        # Task 1s 倒计时
        self._task_timer = None
        self._task_remaining_secs = 0  # 以 1 秒为单位

        # 逻辑时间线（毫秒），现在仅作为内部计数使用，不再写入报告
        self.logical_ms = 0

        # 量表点数（3 或 5），以及当前标签引用
        self.scale_points = 5
        self.scale_labels = self.likert_labels_5

        # ===== 与 EEG 采集页面（Page2）联动相关 =====
        # 主程序中需要手动注入：page7.eeg_page = page2
        self.eeg_page = None
        self.hw_exp_start = None  # 整个实验的起始片上时间（可选）
        self.hw_exp_end = None  # 整个实验的结束片上时间（可选）

        # -------------------- UI --------------------
        root = QVBoxLayout(self)
        root.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        self.instruction = QLabel(
            "填写信息后点击开始。\n" "阶段：提示 → 任务 → 自我评估 → 休息；\n" "自评阶段请使用数字键或点击按钮评分。"
        )
        f = self.instruction.font()
        f.setPointSize(13)
        self.instruction.setFont(f)
        self.instruction.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.instruction.setWordWrap(True)
        root.addWidget(self.instruction)

        # 配置表单
        settings = QWidget()
        settings.setMaximumWidth(520)
        form = QFormLayout(settings)
        form.setFormAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        self.name_input = QLineEdit()
        form.addRow("姓名:", self.name_input)

        self.trials_spin = QSpinBox()
        self.trials_spin.setRange(4, 4000)
        self.trials_spin.setSingleStep(4)  # 只能以 4 步增减
        self.trials_spin.setValue(self.default_trials)
        form.addRow("循环次数(Trials):", self.trials_spin)

        # 可配置时长
        self.prompt_spin = QSpinBox()
        self.prompt_spin.setRange(1, 100)
        self.prompt_spin.setSingleStep(1)
        self.prompt_spin.setValue(int(self.prompt_duration))
        form.addRow("Prompt 时长 (秒):", self.prompt_spin)

        task_box = QHBoxLayout()
        self.task_min_spin = QSpinBox()
        self.task_min_spin.setRange(1, 120)
        self.task_min_spin.setSingleStep(1)
        self.task_min_spin.setValue(int(self.task_min))
        self.task_max_spin = QSpinBox()
        self.task_max_spin.setRange(1, 120)
        self.task_max_spin.setSingleStep(1)
        self.task_max_spin.setValue(int(self.task_max))
        task_box.addWidget(QLabel("Task 区间 (秒):"))
        task_box.addWidget(self.task_min_spin)
        task_box.addWidget(self.task_max_spin)
        form.addRow(task_box)

        self.assess_spin = QDoubleSpinBox()
        self.assess_spin.setDecimals(0)
        self.assess_spin.setRange(1, 120)
        self.assess_spin.setSingleStep(1)
        self.assess_spin.setValue(self.assess_duration)
        form.addRow("Self-assessment 时长 (秒):", self.assess_spin)

        self.break_spin = QDoubleSpinBox()
        self.break_spin.setDecimals(0)
        self.break_spin.setRange(1, 300)
        self.break_spin.setSingleStep(1)
        self.break_spin.setValue(self.break_duration)
        form.addRow("Break 时长 (秒):", self.break_spin)

        # 自评量表选择：3 点或 5 点
        self.scale_combo = QComboBox()
        self.scale_combo.addItem("1 - 3（不同意 / 一般 / 同意）", 3)
        self.scale_combo.addItem("1 - 5（非常不同意 → 非常同意）", 5)
        # 设置默认选中
        self.scale_combo.setCurrentIndex(1)
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

        # fixation cross（大号 "+"）
        self.cross_label = QLabel("+")
        fx = self.cross_label.font()
        fx.setPointSize(160)
        fx.setBold(True)
        self.cross_label.setFont(fx)
        self.cross_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.cross_label.hide()
        root.addWidget(self.cross_label)

        # Task 阶段倒计时（1s 大号数字）
        self.task_count_label = QLabel("")
        ft = self.task_count_label.font()
        ft.setPointSize(48)
        ft.setBold(True)
        self.task_count_label.setFont(ft)
        self.task_count_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.task_count_label.hide()
        root.addWidget(self.task_count_label)

        # 自评按钮（最多 5 个，按量表显示前 N 个）
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

        # 键盘快捷键 1~5
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
            sc.activated.connect(lambda k=key: self._shortcut_record(int(k) - int(QtCore.Qt.Key.Key_0)))
            self.shortcuts.append(sc)

        # ESC 中断保存
        self.shortcut_esc = QShortcut(QKeySequence(QtCore.Qt.Key.Key_Escape), self)
        self.shortcut_esc.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
        self.shortcut_esc.activated.connect(self.abort_and_finalize)

    # -------------------- 入口 --------------------
    def on_start_clicked(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "错误", "请输入姓名！")
            return

        trials = self.trials_spin.value
        trials = self.trials_spin.value()
        if trials % 4 != 0:
            QMessageBox.warning(self, "错误", "循环次数必须为4的倍数（如4/8/12/…）！")
            return

        # ====== 1. 检查 EEG Page2 是否在监听 ======
        eeg_page = getattr(self, "eeg_page", None)
        if eeg_page is None or not hasattr(eeg_page, "is_listening"):
            QMessageBox.warning(self, "错误", "未找到 EEG 采集页面，请在主程序中确保已创建并注入 Page2Widget。")
            return

        if not eeg_page.is_listening():
            QMessageBox.warning(
                self, "提示", "请先在【首页】点击“开始监测信号”，\n" "确保已经开始接收EEG数据后，再启动本实验范式。"
            )
            return

        # 读取用户设置
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

        # 读取量表点数
        self.scale_points = int(self.scale_combo.currentData())
        self.scale_labels = self.likert_labels_3 if self.scale_points == 3 else self.likert_labels_5

        self.name = name
        self.total_trials = trials

        # 生成平均分配的 trial 计划（必为4的倍数，绝对均匀）
        self.trial_plan = self._make_balanced_plan(self.total_trials, self.conditions)

        # ====== 2. 构建目录结构：data/mi/<name>/<timestamp>/ ======
        self.current_user_name = name
        self.user_dir = os.path.join(self.mi_root, self.current_user_name)
        os.makedirs(self.user_dir, exist_ok=True)

        self.run_timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        self.run_dir = os.path.join(self.user_dir, self.run_timestamp)
        os.makedirs(self.run_dir, exist_ok=True)

        # ====== 3. 启动 EEG CSV 记录（从点击“开始实验”这一刻起） ======
        self.hw_exp_start = None
        self.hw_exp_end = None
        try:
            if hasattr(eeg_page, "start_saving"):
                # 把本次实验的 run_dir 传给 Page2，让 EEG CSV & markers.csv 写到同一目录
                eeg_page.start_saving(self.run_dir)
        except Exception:
            # 即使 EEG 保存出错，也不阻断范式本身
            pass

        # 尝试记录实验整体起始片上时间
        first_hw = self._get_hw_timestamp_from_eeg()
        if first_hw is not None:
            self.hw_exp_start = first_hw

        # UI 切换
        self.instruction.hide()
        self.start_btn.hide()
        self.name_input.parent().hide()

        self.trial_logs = []
        self.trial_index = -1
        self.logical_ms = int(self.initial_countdown * 1000)  # 逻辑时间线复位（不再写入报告，仅内部计数）

        # 初始倒计时（无背景色，仅文字提示）
        self._show_fullscreen_message(
            "{n}秒后将开始实验",
            self.initial_countdown,
            plain=True,
            next_callback=self._start_next_trial,
        )

    # -------------------- trial 流程 --------------------
    def _start_next_trial(self):
        self.trial_index += 1
        if self.trial_index >= len(self.trial_plan):
            # 全部结束，收尾倒计时（无背景色）
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

        # ---------- 按范式预计算本 trial 的各阶段时长（ms） ----------
        prompt_ms = int(self.prompt_duration * 1000)

        # 1秒步进随机：闭区间 [tmin, tmax]
        tmin = int(self.task_min)
        tmax = int(self.task_max)
        task_sec = int(random.randint(min(tmin, tmax), max(tmin, tmax)))
        task_ms = task_sec * 1000

        assess_ms = int(self.assess_duration * 1000)
        break_ms = int(self.break_duration * 1000)

        task_start_ms = self.logical_ms + prompt_ms
        task_end_ms = task_start_ms + task_ms

        # 记录日志骨架：新增 task_start_hw / task_end_hw，用于片上时间
        log = {
            "condition": self.current_condition,
            "task_start_ms": task_start_ms,
            "task_end_ms": task_end_ms,
            "task_start_hw": None,  # 由 _stage_task 中记录
            "task_end_hw": None,  # 由 _enter_assess 中记录
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
        self.trial_logs.append(log)

        # ---------- UI：进入 prompt 阶段 ----------
        if self.current_condition == "静止":
            prompt_text = "接下来请保持【静止站立】，不要想象运动"
        else:
            prompt_text = f"接下来请想象【{self.current_condition}】"

        self._show_stage(
            prompt_text,
            int(self.prompt_duration),
            bg="#ffec99",
            fg="#000000",
            next_stage=self._stage_task,
        )

    def _stage_task(self):
        # 任务阶段文本
        if self.current_condition == "静止":
            task_text = "请保持【静止站立】，不要想象运动"
        else:
            task_text = f"请想象【{self.current_condition}】"

        # ===== 在 Task 阶段开始时记录片上时间 =====
        self._record_task_start_hw_for_current_trial()

        # 显示注视十字；显示 Task 倒计时（1s）；结束后直接进入自评
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

    def _tick_task(self):
        self._task_remaining_secs -= 1
        if self._task_remaining_secs > 0:
            self.task_count_label.setText(str(self._task_remaining_secs))
        else:
            self._stop_task_timer()
            self.task_count_label.setText("0")
            self.task_count_label.hide()

    def _enter_assess(self):
        # ===== 在 Task 阶段结束（进入自评前）记录片上时间 =====
        self._record_task_end_hw_for_current_trial()

        self.cross_label.hide()
        self.task_count_label.hide()
        self._stop_task_timer()
        self._stage_assess()

    def _stage_assess(self):
        # 启动“自评倒计时”
        self.is_assessing = True
        self._assess_remaining = int(self.assess_duration)

        # 配置按钮与标签（按量表）
        self._setup_rating_controls()

        # 设置评估阶段样式与首帧文案
        self._apply_bg("#bde0fe")
        self._apply_fg("#000000")
        self.countdown_label.hide()
        self.stage_label.show()
        self._update_assess_text()  # 首次显示

        # 启动每秒计时器
        self._stop_assess_timer()
        self._assess_timer = QtCore.QTimer(self)
        self._assess_timer.timeout.connect(self._tick_assess)
        self._assess_timer.start(1000)

    def _setup_rating_controls(self):
        # 显示前 N 个按钮并设定文案
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
            # 结束自评，进入 break
            self._stop_assess_timer()
            self._stage_break()

    def _current_assess_question(self) -> str:
        """根据当前条件返回对应提问句。"""
        cond = self.current_condition
        if cond == "慢走":
            return "刚刚是否认真在想象慢走？"
        elif cond == "慢跑":
            return "刚刚是否认真在想象慢跑？"
        elif cond == "快跑":
            return "刚刚是否认真在想象快跑？"
        else:
            return "刚刚是否什么都没想？"

    def _update_assess_text(self):
        # 量表范围提示（仅作为说明，不显示范围数字）
        assess_text = f"{self._current_assess_question()}\n请在 {self._assess_remaining} 秒内作答"
        self.stage_label.setText(assess_text)

    def _stage_break(self):
        self.is_assessing = False
        # 确保按钮隐藏
        for b in self.rating_btns:
            b.setVisible(False)

        # 回写评分
        self.trial_logs[-1]["rating"] = self.pending_rating
        if self.pending_rating is not None:
            self.trial_logs[-1]["rating_label"] = self.scale_labels.get(self.pending_rating)

        # 休息阶段逐秒提示：请休息N秒
        self._show_fullscreen_message(
            "请休息{n}秒",
            int(self.break_duration),
            bg="#e6ffea",
            fg="#000000",
            next_callback=self._finalize_trial_and_continue,
        )

    def _finalize_trial_and_continue(self):
        # 推进逻辑时间线到下一个 trial 的 prompt 起点（仅内部计数）
        self.logical_ms += self.trial_logs[-1]["total_ms"]
        self._start_next_trial()

    # -------------------- 显示与计时 --------------------
    def _show_stage(
        self,
        text: str,
        seconds: float,
        bg: str,
        fg: str,
        next_stage=None,
        show_cross: bool = False,
    ):
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
        template: str,
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
        self.task_count_label.hide()
        self.cross_label.hide()
        self.countdown_label.show()
        self._countdown_value = int(seconds)
        self._countdown_template = template
        self.countdown_label.setText(template.format(n=self._countdown_value))
        self._countdown_updater = QtCore.QTimer(self)
        self._countdown_updater.timeout.connect(lambda: self._tick(next_callback))
        self._countdown_updater.start(1000)

    def _tick(self, next_callback):
        self._countdown_value -= 1
        if self._countdown_value > 0:
            self.countdown_label.setText(self._countdown_template.format(n=self._countdown_value))
        else:
            self._countdown_updater.stop()
            self.countdown_label.hide()
            if callable(next_callback):
                next_callback()

    def _apply_bg(self, color: str):
        self.setStyleSheet(f"background-color:{color};")

    def _apply_fg(self, color: str):
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
        # 仅在评估期且 val 在量表范围内时有效
        if 1 <= val <= self.scale_points:
            self.record_rating(val)

    def record_rating(self, value: int):
        if self.is_assessing and self.pending_rating is None and 1 <= value <= self.scale_points:
            self.pending_rating = int(value)
            for b in self.rating_btns:
                b.setVisible(False)
            label = self.scale_labels.get(value, "")
            suffix = f" - {label}" if label else ""
            self.stage_label.setText(f"已记录自我评分: {value}{suffix}")

    # -------------------- 与 Page2 的时间戳交互 --------------------
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

    # -------------------- 结束与中断 --------------------
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

        # 重置目录相关
        self.current_user_name = None
        self.user_dir = None
        self.run_dir = None
        self.run_timestamp = None

        # 重置时间记录
        self.hw_exp_start = None
        self.hw_exp_end = None

    # -------------------- 日志与工具 --------------------
    def _save_report(self, aborted: bool = False):
        """
        报告格式：
        每行：
          task_start_hw,task_end_hw,condition,detail

        其中 detail 含：
          prompt / task / assess / break 各阶段逻辑秒数、
          量表点数、评分数值与文字。

        报告文件保存在：
            data/mi/<Name>/<YYYYMMDDHHMMSS>/EEGMILL_*.txt
        """
        # 确定被试名称
        name = self.current_user_name or self.name or self.name_input.text().strip() or "unknown"

        flag = 'ABORT' if aborted else 'DONE'

        # 优先使用本次 run 的目录：data/mi/<name>/<timestamp>
        base_dir = self.run_dir or self.user_dir or self.mi_root
        os.makedirs(base_dir, exist_ok=True)

        # 文件名里的时间戳：优先用 run_timestamp，兜底用当前时间
        ts_for_name = self.run_timestamp or datetime.now().strftime('%Y%m%d%H%M%S')

        fname = os.path.join(base_dir, f"EEGMILL_{name}_{ts_for_name}_trials{len(self.trial_logs)}_{flag}.txt")

        try:
            with open(fname, 'w', encoding='utf-8') as f:
                for rec in self.trial_logs:
                    # 片上时间（秒）
                    start_hw = rec.get("task_start_hw")
                    end_hw = rec.get("task_end_hw")

                    if isinstance(start_hw, (int, float)):
                        t0 = float(start_hw)
                    else:
                        t0 = float('nan')

                    if isinstance(end_hw, (int, float)):
                        t1 = float(end_hw)
                    else:
                        t1 = float('nan')

                    cond = rec['condition']
                    d = rec['durations']
                    rating = rec['rating'] if rec['rating'] is not None else 'None'
                    rating_label = rec.get('rating_label', 'None')
                    detail = (
                        f"prompt={d['prompt']}|task={d['task']}|"
                        f"assess={d['assess']}|break={d['break']}|"
                        f"scale={rec.get('scale_points', 'NA')}|"
                        f"rating={rating}|rating_label={rating_label}"
                    )
                    f.write(f"{t0:.6f},{t1:.6f},{cond},{detail}\n")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"写入日志失败：{e}")

    @staticmethod
    def _make_balanced_plan(total_trials: int, conditions: list[str]) -> list[str]:
        """
        生成“分块均衡随机”的 trial 序列：
        - total_trials 必须是 len(conditions) 的倍数（这里就是 4 的倍数）
        - 每个 block（长度 = len(conditions)）中包含一次每个条件，但 block 内部顺序随机
        - 拼接所有 block 后返回
        """
        if not conditions:
            return []
        n = len(conditions)
        if total_trials % n != 0:
            # 按你的 UI 已经限制是 4 的倍数，这里做个保护
            raise ValueError("total_trials must be a multiple of the number of conditions.")

        blocks = total_trials // n
        plan = []
        for _ in range(blocks):
            block = conditions[:]  # 拷贝一份
            random.shuffle(block)  # 只对当前 block 随机
            plan.extend(block)  # 追加到总计划
        return plan


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = Page7Widget()
    w.show()
    sys.exit(app.exec())
