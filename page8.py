# page8.py
import sys
import random
from datetime import datetime
from PyQt6 import QtCore
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QLineEdit, QSpinBox, QDoubleSpinBox, QPushButton, QMessageBox, QComboBox
)
from PyQt6.QtGui import QKeySequence, QShortcut


class Page8Widget(QWidget):  # 这里没有run的概念
    """
    EEG 实验范式（2 条 Task：手臂抬起、静止）。
    - 启动/结束倒计时：无背景，仅文字。
    - 流程：prompt(Tp) → task∈[Tmin,Tmax]（随机整秒）→ self-assessment(Ta，文案倒计时) → break(Tb)。
    - 循环次数必须为 2 的倍数；每个 block 内条件各出现一次并打乱（分块均衡随机）。
    - 自评阶段支持 3 点或 5 点 Likert 量表；可用数字键评分。
    - 日志第1/2列为 Task 激活期开始/结束 的“逻辑时间”（相对首个 trial 的 prompt 开始=0s）。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("EEG 实验范式（手臂抬起/静止）")
        self.setMinimumSize(900, 700)

        # ------- 默认参数 -------
        self.initial_countdown = 10
        self.prompt_duration = 4.0
        self.task_min = 5.0
        self.task_max = 6.0
        self.assess_duration = 5.0
        self.break_duration = 5.0
        self.end_countdown = 10
        self.default_trials = 12          # 必须是 2 的倍数
        self.conditions = ["手臂抬起", "静止"]

        # Likert 标签
        self.likert_labels_3 = {1: "不同意", 2: "一般", 3: "同意"}
        self.likert_labels_5 = {
            1: "非常不同意", 2: "不同意", 3: "一般", 4: "同意", 5: "非常同意"
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
        self.logical_ms = 0

        self.scale_points = 5
        self.scale_labels = self.likert_labels_5

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
        self.trials_spin.setSingleStep(2)     # 只能以 2 步增减
        self.trials_spin.setValue(self.default_trials)
        form.addRow("循环次数(Trials):", self.trials_spin)

        self.prompt_spin = QSpinBox()
        self.prompt_spin.setRange(1, 100)
        self.prompt_spin.setValue(int(self.prompt_duration))
        form.addRow("Prompt 时长 (秒):", self.prompt_spin)

        task_box = QHBoxLayout()
        self.task_min_spin = QSpinBox(); self.task_min_spin.setRange(1, 120); self.task_min_spin.setValue(int(self.task_min))
        self.task_max_spin = QSpinBox(); self.task_max_spin.setRange(1, 120); self.task_max_spin.setValue(int(self.task_max))
        task_box.addWidget(QLabel("Task 区间 (秒):"))
        task_box.addWidget(self.task_min_spin)
        task_box.addWidget(self.task_max_spin)
        form.addRow(task_box)

        self.assess_spin = QDoubleSpinBox()
        self.assess_spin.setDecimals(0); self.assess_spin.setRange(1, 120); self.assess_spin.setValue(self.assess_duration)
        form.addRow("Self-assessment 时长 (秒):", self.assess_spin)

        self.break_spin = QDoubleSpinBox()
        self.break_spin.setDecimals(0); self.break_spin.setRange(1, 300); self.break_spin.setValue(self.break_duration)
        form.addRow("Break 时长 (秒):", self.break_spin)

        self.scale_combo = QComboBox()
        self.scale_combo.addItem("1 - 3（不同意 / 一般 / 同意）", 3)
        self.scale_combo.addItem("1 - 5（非常不同意 → 非常同意）", 5)
        self.scale_combo.setCurrentIndex(1)   # 默认 5 点
        form.addRow("自评量表:", self.scale_combo)

        self.start_btn = QPushButton("开始实验")
        self.start_btn.clicked.connect(self.on_start_clicked)

        root.addWidget(settings)
        root.addWidget(self.start_btn, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        # 大显示区
        self.stage_label = QLabel(""); fs = self.stage_label.font(); fs.setPointSize(42)
        self.stage_label.setFont(fs); self.stage_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter); self.stage_label.hide()
        root.addWidget(self.stage_label)

        self.countdown_label = QLabel(""); fc = self.countdown_label.font(); fc.setPointSize(32)
        self.countdown_label.setFont(fc); self.countdown_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter); self.countdown_label.hide()
        root.addWidget(self.countdown_label)

        self.cross_label = QLabel("+"); fx = self.cross_label.font(); fx.setPointSize(160); fx.setBold(True)
        self.cross_label.setFont(fx); self.cross_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter); self.cross_label.hide()
        root.addWidget(self.cross_label)

        # Task 倒计时标签（已不使用，但保留用于样式统一）
        self.task_count_label = QLabel(""); ft = self.task_count_label.font(); ft.setPointSize(48); ft.setBold(True)
        self.task_count_label.setFont(ft); self.task_count_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter); self.task_count_label.hide()
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
        for key in [QtCore.Qt.Key.Key_1, QtCore.Qt.Key.Key_2, QtCore.Qt.Key.Key_3, QtCore.Qt.Key.Key_4, QtCore.Qt.Key.Key_5]:
            sc = QShortcut(QKeySequence(key), self)
            sc.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
            sc.activated.connect(lambda k=key: self._shortcut_record(int(k) - int(QtCore.Qt.Key.Key_0)))
            self.shortcuts.append(sc)

        # ESC 中断保存
        self.shortcut_esc = QShortcut(QKeySequence(QtCore.Qt.Key.Key_Escape), self)
        self.shortcut_esc.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
        self.shortcut_esc.activated.connect(self.abort_and_finalize)

    # ------- 入口 -------
    def on_start_clicked(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "错误", "请输入姓名！"); return

        trials = self.trials_spin.value()
        if trials % 2 != 0:
            QMessageBox.warning(self, "错误", "循环次数必须为2的倍数！"); return

        p = int(self.prompt_spin.value())
        tmin = int(self.task_min_spin.value()); tmax = int(self.task_max_spin.value())
        ta = int(self.assess_spin.value()); tb = int(self.break_spin.value())
        if tmin > tmax:
            QMessageBox.warning(self, "错误", "Task 区间无效：最小值不能大于最大值。"); return

        self.prompt_duration = p; self.task_min = tmin; self.task_max = tmax
        self.assess_duration = ta; self.break_duration = tb

        self.scale_points = int(self.scale_combo.currentData())
        self.scale_labels = self.likert_labels_3 if self.scale_points == 3 else self.likert_labels_5

        self.name = name; self.total_trials = trials

        # 分块均衡随机（每个 block 含一次“手臂抬起”和一次“静止”，顺序打乱）
        self.trial_plan = self._make_balanced_plan(self.total_trials, self.conditions)

        # UI 切换
        self.instruction.hide(); self.start_btn.hide(); self.name_input.parent().hide()
        self.trial_logs = []; self.trial_index = -1; self.logical_ms = int(self.initial_countdown * 1000)

        # 初始倒计时
        self._show_fullscreen_message("{n}秒后将开始实验", self.initial_countdown, plain=True, next_callback=self._start_next_trial)

    # ------- 流程 -------
    def _start_next_trial(self):
        self.trial_index += 1
        if self.trial_index >= len(self.trial_plan):
            self._show_fullscreen_message("{n}秒后实验结束", self.end_countdown, plain=True, next_callback=self._finish_and_save)
            return

        self.current_condition = self.trial_plan[self.trial_index]
        self.pending_rating = None; self.is_assessing = False
        self._stop_assess_timer(); self._stop_task_timer()

        prompt_ms = int(self.prompt_duration * 1000)
        task_sec = int(random.randint(min(int(self.task_min), int(self.task_max)),
                                      max(int(self.task_min), int(self.task_max))))
        task_ms = task_sec * 1000
        assess_ms = int(self.assess_duration * 1000)
        break_ms = int(self.break_duration * 1000)

        task_start_ms = self.logical_ms + prompt_ms
        task_end_ms = task_start_ms + task_ms

        self.trial_logs.append({
            "condition": self.current_condition,
            "task_start_ms": task_start_ms,
            "task_end_ms": task_end_ms,
            "durations": {"prompt": int(self.prompt_duration), "task": int(task_sec),
                          "assess": int(self.assess_duration), "break": int(self.break_duration)},
            "rating": None, "rating_label": None, "scale_points": self.scale_points,
            "total_ms": prompt_ms + task_ms + assess_ms + break_ms
        })

        # Prompt
        if self.current_condition == "静止":
            prompt_text = "接下来请保持【静止】，不要想象运动"
        else:
            prompt_text = "接下来请想象【手臂抬起】"
        self._show_stage(prompt_text, int(self.prompt_duration), bg="#ffec99", fg="#000000", next_stage=self._stage_task)

    def _stage_task(self):
        if self.current_condition == "静止":
            task_text = "请保持【静止】，不要想象运动"
        else:
            task_text = "请想象【手臂抬起】"

        # 不展示 task 倒计时；仅显示注视十字，时长到点自动进入评估
        self.cross_label.show()
        dur = int(self.trial_logs[-1]["durations"]["task"])
        self._show_stage(task_text, dur, bg="#ffffff", fg="#000000", next_stage=self._enter_assess, show_cross=True)

    def _enter_assess(self):
        self.cross_label.hide(); self.task_count_label.hide(); self._stop_task_timer()
        self._stage_assess()

    def _stage_assess(self):
        self.is_assessing = True
        self._assess_remaining = int(self.assess_duration)
        self._setup_rating_controls()

        self._apply_bg("#bde0fe"); self._apply_fg("#000000")
        self.countdown_label.hide(); self.stage_label.show()
        self._update_assess_text()

        self._stop_assess_timer()
        self._assess_timer = QtCore.QTimer(self)
        self._assess_timer.timeout.connect(self._tick_assess)
        self._assess_timer.start(1000)

    def _setup_rating_controls(self):
        labels = self.scale_labels
        for idx, b in enumerate(self.rating_btns, start=1):
            if idx <= self.scale_points:
                b.setText(f"{idx}. {labels[idx]}"); b.setVisible(True)
            else:
                b.setVisible(False)

    def _tick_assess(self):
        self._assess_remaining -= 1
        if self._assess_remaining > 0:
            if self.pending_rating is None:
                self._update_assess_text()
        else:
            self._stop_assess_timer(); self._stage_break()

    def _current_assess_question(self) -> str:
        if self.current_condition == "手臂抬起":
            return "刚刚是否认真在想象手臂抬起？"
        else:
            return "刚刚是否什么都没想？"

    def _update_assess_text(self):
        assess_text = f"{self._current_assess_question()}\n请在 {self._assess_remaining} 秒内作答"
        self.stage_label.setText(assess_text)

    def _stage_break(self):
        self.is_assessing = False
        for b in self.rating_btns: b.setVisible(False)

        self.trial_logs[-1]["rating"] = self.pending_rating
        if self.pending_rating is not None:
            self.trial_logs[-1]["rating_label"] = self.scale_labels.get(self.pending_rating)

        self._show_fullscreen_message("请休息{n}秒", int(self.break_duration),
                                      bg="#e6ffea", fg="#000000",
                                      next_callback=self._finalize_trial_and_continue)

    def _finalize_trial_and_continue(self):
        self.logical_ms += self.trial_logs[-1]["total_ms"]
        self._start_next_trial()

    # ------- 显示与计时 -------
    def _show_stage(self, text, seconds, bg, fg, next_stage=None, show_cross=False):
        self._apply_bg(bg); self._apply_fg(fg)
        self.stage_label.setText(text); self.stage_label.show()
        self.countdown_label.hide()
        if not show_cross: self.cross_label.hide()
        QtCore.QTimer.singleShot(int(seconds * 1000), next_stage)

    def _show_fullscreen_message(self, template, seconds, bg=None, fg=None, plain=False, next_callback=None):
        if plain:
            self._clear_styles()
        else:
            if bg is not None: self._apply_bg(bg)
            if fg is not None: self._apply_fg(fg)
        self.stage_label.hide(); self.task_count_label.hide(); self.cross_label.hide()
        self.countdown_label.show()
        self._countdown_value = int(seconds); self._countdown_template = template
        self.countdown_label.setText(template.format(n=self._countdown_value))
        self._countdown_updater = QtCore.QTimer(self)
        self._countdown_updater.timeout.connect(lambda: self._tick(next_callback))
        self._countdown_updater.start(1000)

    def _tick(self, next_callback):
        self._countdown_value -= 1
        if self._countdown_value > 0:
            self.countdown_label.setText(self._countdown_template.format(n=self._countdown_value))
        else:
            self._countdown_updater.stop(); self.countdown_label.hide()
            if callable(next_callback): next_callback()

    def _apply_bg(self, color): self.setStyleSheet(f"background-color:{color};")
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
            try: self._assess_timer.stop(); self._assess_timer.deleteLater()
            except Exception: pass
            self._assess_timer = None

    def _stop_task_timer(self):
        if self._task_timer is not None:
            try: self._task_timer.stop(); self._task_timer.deleteLater()
            except Exception: pass
            self._task_timer = None

    def _shortcut_record(self, val: int):
        if 1 <= val <= self.scale_points:
            self.record_rating(val)

    def record_rating(self, value: int):
        if self.is_assessing and self.pending_rating is None and 1 <= value <= self.scale_points:
            self.pending_rating = int(value)
            for b in self.rating_btns: b.setVisible(False)
            label = self.scale_labels.get(value, "")
            self.stage_label.setText(f"已记录自我评分: {value}" + (f" - {label}" if label else ""))

    # ------- 结束与中断 -------
    def _finish_and_save(self):
        self._save_report(); self._reset_ui()

    def abort_and_finalize(self):
        self._save_report(aborted=True); self._reset_ui()

    def _reset_ui(self):
        self._clear_styles()
        self.stage_label.hide(); self.countdown_label.hide(); self.cross_label.hide(); self.task_count_label.hide()
        for b in self.rating_btns: b.setVisible(False)
        self.instruction.show(); self.start_btn.show(); self.name_input.parent().show()
        self.trial_index = -1; self.trial_plan = []; self.trial_logs = []
        self.pending_rating = None; self.is_assessing = False; self.logical_ms = 0
        self._stop_assess_timer(); self._stop_task_timer()

    # ------- 日志 -------
    def _save_report(self, aborted: bool = False):
        ts = datetime.now().strftime('%Y%m%d%H%M%S'); flag = 'ABORT' if aborted else 'DONE'
        fname = f"logs/EEGMI_{self.name}_{ts}_trials{len(self.trial_logs)}_{flag}.txt"
        try:
            with open(fname, 'w', encoding='utf-8') as f:
                for rec in self.trial_logs:
                    t0 = rec['task_start_ms'] / 1000.0; t1 = rec['task_end_ms'] / 1000.0
                    cond = rec['condition']; d = rec['durations']
                    rating = rec['rating'] if rec['rating'] is not None else 'None'
                    rating_label = rec.get('rating_label', 'None')
                    detail = (f"prompt={d['prompt']}|task={d['task']}|assess={d['assess']}|break={d['break']}|"
                              f"scale={rec.get('scale_points','NA')}|rating={rating}|rating_label={rating_label}")
                    f.write(f"{t0:.3f},{t1:.3f},{cond},{detail}\n")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"写入日志失败：{e}")

    @staticmethod
    def _make_balanced_plan(total_trials: int, conditions: list[str]) -> list[str]:
        """分块均衡随机：每个 block 含每个条件一次，block 内随机顺序。"""
        if not conditions: return []
        n = len(conditions)
        if total_trials % n != 0:
            raise ValueError("total_trials must be a multiple of the number of conditions.")
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
