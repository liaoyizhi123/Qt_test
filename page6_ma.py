import os
import sys
import random
from datetime import datetime
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QDoubleSpinBox,
    QPushButton,
    QMessageBox,
)
from PyQt6.QtGui import QKeySequence, QShortcut

# 支持的运算符
OPERATIONS = ['+', '-']


class Page6Widget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("心算实验")

        # ====== Mental Calc 数据根目录：data/ma ======
        self.data_root = "data"
        self.ma_root = os.path.join(self.data_root, "ma")
        os.makedirs(self.ma_root, exist_ok=True)

        # 当前被试 & 本次实验 run 的目录
        self.current_user_name: str | None = None
        self.user_dir: str | None = None       # data/ma/<name>
        self.run_dir: str | None = None        # data/ma/<name>/<timestamp>
        self.run_timestamp: str | None = None  # YYYYMMDDHHMMSS

        # 默认参数
        self.name = ""
        self.loops = 6
        self.trials = 10
        self.delay = 4.0  # 单个阶段时长（展示期 / 判断期）
        self.max_operand = 100
        self.initial_countdown = 10  # 实验开始前倒计时
        self.rest_duration = 10  # 循环间休息倒计时
        self.separate_phases = False  # 是否分离展示与判断

        # 状态变量
        self.current_loop = 0
        self.current_index = 0
        self.sequence = []  # (expr, disp, actual_flag)
        # 每题记录: (expr, disp, actual_flag, user_input_flag or None)
        self.results_per_loop = []
        self.response_recorded = False
        self.input_enabled = False  # 控制输入是否有效

        # 与 EEG 采集页面（Page2）联动
        # 需要在主程序中设置：page6.eeg_page = page2
        self.eeg_page = None
        # 整个实验的开始/结束片上时间（可选）
        self.hw_exp_start = None
        self.hw_exp_end = None
        # 每个 loop 的开始/结束片上时间（写入 txt）
        self.loop_hw_start = []
        self.loop_hw_end = []

        # ===== 布局 =====
        root_layout = QVBoxLayout(self)
        root_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        self.main_container = QWidget()
        self.main_container.setFixedWidth(600)
        layout = QVBoxLayout(self.main_container)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        root_layout.addWidget(self.main_container, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        # 操作提示标签
        self.instruction_label = QLabel(
            "请按左方向键表示算式【正确】，按右方向键表示算式【错误】。\n"
            "算式格式如 “1 + 1 = 2”，请在规定时间内完成判断。"
        )
        instr_font = self.instruction_label.font()
        instr_font.setPointSize(14)
        self.instruction_label.setFont(instr_font)
        self.instruction_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.instruction_label.setWordWrap(True)
        self.instruction_label.setFixedWidth(500)
        fm = QtGui.QFontMetrics(instr_font)
        self.instruction_label.setMinimumHeight(fm.lineSpacing() * 2 + 8)
        layout.addWidget(self.instruction_label)

        # 设置区
        settings = QWidget()
        settings.setMaximumWidth(400)
        form = QFormLayout(settings)
        form.setFormAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        self.name_input = QLineEdit()
        form.addRow("Name:", self.name_input)

        self.loops_spin = QSpinBox()
        self.loops_spin.setRange(1, 20)
        self.loops_spin.setValue(self.loops)
        form.addRow("Runs:", self.loops_spin)

        self.trials_spin = QSpinBox()
        self.trials_spin.setRange(1, 200)
        self.trials_spin.setValue(self.trials)
        form.addRow("Trials:", self.trials_spin)

        self.delay_spin = QDoubleSpinBox()
        self.delay_spin.setRange(0.2, 10.0)
        self.delay_spin.setSingleStep(0.2)
        self.delay_spin.setValue(self.delay)
        form.addRow("Delay / phase (s):", self.delay_spin)

        self.operand_spin = QSpinBox()
        self.operand_spin.setRange(1, 999)
        self.operand_spin.setValue(self.max_operand)
        form.addRow("Max Operand:", self.operand_spin)

        # 是否分离展示与操作
        self.split_checkbox = QtWidgets.QCheckBox("是（先展示，后作答）")
        self.split_checkbox.setChecked(False)
        form.addRow("展示/操作分离:", self.split_checkbox)

        self.start_btn = QPushButton("Start Calculation")
        self.start_btn.clicked.connect(self.start_experiment)
        layout.addWidget(settings)
        layout.addWidget(self.start_btn, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        # 倒计时标签
        self.countdown_label = QLabel("")
        font_cd = self.countdown_label.font()
        font_cd.setPointSize(24)
        self.countdown_label.setFont(font_cd)
        self.countdown_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.countdown_label.hide()
        layout.addWidget(self.countdown_label)

        # 题目标签
        self.task_label = QLabel("")
        font_task = self.task_label.font()
        font_task.setPointSize(48)
        self.task_label.setFont(font_task)
        self.task_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.task_label.setFixedWidth(500)
        self.task_label.hide()
        layout.addWidget(self.task_label)

        # 固定高度按钮容器，保证布局稳定
        self.btn_container = QWidget()
        self.btn_container.setFixedHeight(80)
        self.btn_container.setFixedWidth(400)
        btn_layout = QtWidgets.QHBoxLayout(self.btn_container)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(40)
        btn_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        self.btn_true = QPushButton("正确")
        self.btn_false = QPushButton("错误")
        for btn in (self.btn_true, self.btn_false):
            btn.setCheckable(True)
            btn.setFixedSize(120, 50)

        btn_style = (
            "QPushButton{background-color:#4caf50;color:white;font-size:16px;}"
            "QPushButton:checked{background-color:#388e3c;}"
            "QPushButton:disabled{background-color:gray;}"
            "QPushButton:disabled:checked{background-color:#388e3c;}"
        )
        self.btn_true.setStyleSheet(btn_style)
        self.btn_false.setStyleSheet(btn_style)

        self.btn_true.clicked.connect(lambda: self.record_response(True))
        self.btn_false.clicked.connect(lambda: self.record_response(False))

        btn_layout.addWidget(self.btn_true)
        btn_layout.addWidget(self.btn_false)

        self.btn_container.hide()
        layout.addWidget(self.btn_container, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        # 反馈 / 提示标签
        self.feedback_label = QLabel("")
        font_fb = self.feedback_label.font()
        font_fb.setPointSize(20)
        self.feedback_label.setFont(font_fb)
        self.feedback_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.feedback_label.setFixedHeight(40)
        self.feedback_label.setFixedWidth(500)
        self.feedback_label.setStyleSheet("border:none;")
        self.feedback_label.hide()
        layout.addWidget(self.feedback_label)

        # 键盘快捷键
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.shortcut_left = QShortcut(QKeySequence(QtCore.Qt.Key.Key_Left), self)
        self.shortcut_left.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
        self.shortcut_left.activated.connect(lambda: self.record_response(True))
        self.shortcut_right = QShortcut(QKeySequence(QtCore.Qt.Key.Key_Right), self)
        self.shortcut_right.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
        self.shortcut_right.activated.connect(lambda: self.record_response(False))

    # ============ 实验流程 ============

    def start_experiment(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "错误", "请输入姓名！")
            return

        # 1. 检查 Page2 是否在监听 EEG 数据
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
                "确保已经开始接收EEG数据后，再启动心算实验。"
            )
            return

        # 2. 构建目录结构：data/calc/<name>/<timestamp>/
        self.current_user_name = name
        self.user_dir = os.path.join(self.ma_root, self.current_user_name)
        os.makedirs(self.user_dir, exist_ok=True)

        self.run_timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        self.run_dir = os.path.join(self.user_dir, self.run_timestamp)
        os.makedirs(self.run_dir, exist_ok=True)

        # 3. 读取参数 & 初始化状态
        self.name = name
        self.loops = self.loops_spin.value()
        self.trials = self.trials_spin.value()
        self.delay = self.delay_spin.value()
        self.max_operand = self.operand_spin.value()
        self.separate_phases = self.split_checkbox.isChecked()

        self.current_loop = 1
        self.results_per_loop = [[] for _ in range(self.loops)]

        self.sequence = []
        self.response_recorded = False
        self.input_enabled = False

        # 初始化时间记录
        self.hw_exp_start = None
        self.hw_exp_end = None
        self.loop_hw_start = [None] * self.loops
        self.loop_hw_end = [None] * self.loops

        # ==== 关键：在“有效点击 Start Calculation”后立刻开始保存 EEG CSV ====
        if hasattr(eeg_page, "start_saving"):
            try:
                # 把本次实验的 run_dir 传给 Page2，让 EEG CSV & markers.csv 写到同一目录
                eeg_page.start_saving(self.run_dir)
            except Exception:
                # Page2 内部处理错误，这里不中断心算实验
                pass

        # 尝试记录实验整体起始片上时间
        first_hw = self._get_hw_timestamp_from_eeg()
        if first_hw is not None:
            self.hw_exp_start = first_hw

        self.instruction_label.hide()
        self.name_input.parent().hide()
        self.start_btn.hide()

        # 初始倒计时（仅界面，不再用于时间计算）
        self.countdown = self.initial_countdown
        self.countdown_label.setText(f"{self.countdown}秒后开始心算实验")
        self.countdown_label.show()
        QtCore.QTimer.singleShot(1000, self.update_initial_countdown)

    def update_initial_countdown(self):
        self.countdown -= 1
        if self.countdown > 0:
            self.countdown_label.setText(f"{self.countdown}秒后开始心算实验")
            QtCore.QTimer.singleShot(1000, self.update_initial_countdown)
        else:
            self.countdown_label.hide()
            self.start_loop()

    def start_loop(self):
        # 生成本轮题目
        ops = OPERATIONS
        correct_flags = [True] * (self.trials // 2) + [False] * (self.trials - self.trials // 2)
        random.shuffle(correct_flags)

        self.sequence = []
        used = set()
        for flag in correct_flags:
            while True:
                a = random.randint(1, self.max_operand)
                b = random.randint(1, self.max_operand)
                op = random.choice(ops)
                expr = f"{a} {op} {b}"
                true_val = eval(expr)
                if flag:
                    disp = true_val
                else:
                    offset_choices = [i for i in range(-3, 4) if i != 0]
                    disp = true_val + random.choice(offset_choices)
                    if disp < 0:
                        continue
                if (expr, disp) not in used:
                    used.add((expr, disp))
                    self.sequence.append((expr, disp, flag))
                    break

        self.current_index = 0
        self.task_label.show()
        self.feedback_label.show()
        self.btn_container.show()
        self.show_task()

    def show_task(self):
        if self.current_index >= len(self.sequence):
            self.end_loop()
            return

        # 若是本轮的第一题，记录 loop 开始片上时间
        if self.current_index == 0:
            self._record_loop_start_hw(self.current_loop - 1)

        # 重置当前 trial 状态
        self.response_recorded = False
        self.input_enabled = False
        self.btn_true.setChecked(False)
        self.btn_false.setChecked(False)
        self.btn_true.setEnabled(False)
        self.btn_false.setEnabled(False)
        self.feedback_label.clear()
        self.feedback_label.setStyleSheet("border:none;")

        expr, disp, _ = self.sequence[self.current_index]
        self.task_label.setText(f"{expr} = {disp}")
        self.activateWindow()
        self.setFocus()

        if self.separate_phases:
            # 展示期：按钮隐藏（容器仍在），禁止输入
            self.btn_true.hide()
            self.btn_false.hide()
            self.feedback_label.setText("请思考")
            self.feedback_label.setStyleSheet("color:black;border:none;")
            QtCore.QTimer.singleShot(int(self.delay * 1000), self.start_response_phase)
        else:
            # 非分离：整个 delay 内可作答
            self.btn_true.show()
            self.btn_false.show()
            self.feedback_label.setText("")
            QtCore.QTimer.singleShot(200, self.enable_inputs)
            QtCore.QTimer.singleShot(int(self.delay * 1000), self.next_task)

    def start_response_phase(self):
        # 分离模式：从展示期进入判断期
        if self.current_index >= len(self.sequence):
            return

        self.btn_true.show()
        self.btn_false.show()
        self.btn_true.setEnabled(True)
        self.btn_false.setEnabled(True)
        self.input_enabled = True

        self.feedback_label.setText("现在判断：左=正确，右=错误")
        self.feedback_label.setStyleSheet("color:black;border:none;")

        # 判断期持续 delay 秒
        QtCore.QTimer.singleShot(int(self.delay * 1000), self.finish_trial)

    def enable_inputs(self):
        # 非分离模式启用输入
        if not self.separate_phases and self.current_index < len(self.sequence):
            self.input_enabled = True
            self.btn_true.setEnabled(True)
            self.btn_false.setEnabled(True)

    def record_response(self, user_says_true: bool):
        if not self.input_enabled or self.response_recorded or self.current_index >= len(self.sequence):
            return

        expr, disp, flag = self.sequence[self.current_index]
        self.results_per_loop[self.current_loop - 1].append((expr, disp, flag, user_says_true))
        self.response_recorded = True
        self.input_enabled = False

        self.btn_true.setEnabled(False)
        self.btn_false.setEnabled(False)
        if user_says_true:
            self.btn_true.setChecked(True)
        else:
            self.btn_false.setChecked(True)

        is_correct = user_says_true == flag
        mark = "✔" if is_correct else "❌"
        color = "green" if is_correct else "red"
        self.feedback_label.setText(mark)
        self.feedback_label.setStyleSheet(f"color:{color};border:none;")

    def next_task(self):
        # 非分离模式：delay 结束，若无作答则记 None
        if self.separate_phases:
            return

        if self.current_index < len(self.sequence) and not self.response_recorded:
            expr, disp, flag = self.sequence[self.current_index]
            self.results_per_loop[self.current_loop - 1].append((expr, disp, flag, None))

        self.current_index += 1
        self.show_task()

    def finish_trial(self):
        # 分离模式：判断期结束
        if not self.separate_phases or self.current_index >= len(self.sequence):
            return

        if not self.response_recorded:
            expr, disp, flag = self.sequence[self.current_index]
            self.results_per_loop[self.current_loop - 1].append((expr, disp, flag, None))

        self.current_index += 1
        self.show_task()

    def end_loop(self):
        # 记录本轮结束时的片上时间
        self._record_loop_end_hw(self.current_loop - 1)

        self.task_label.hide()
        self.btn_container.hide()
        self.feedback_label.hide()

        if self.current_loop == self.loops:
            self.countdown = self.initial_countdown
            self.countdown_label.setText(f"实验将于{self.countdown}秒后结束")
            self.countdown_label.show()
            QtCore.QTimer.singleShot(1000, self.update_end_countdown)
        else:
            self.countdown = self.rest_duration
            self.countdown_label.setText(f"{self.countdown}秒后开始下一次循环")
            self.countdown_label.show()
            QtCore.QTimer.singleShot(1000, self.update_rest_countdown)

    def update_rest_countdown(self):
        self.countdown -= 1
        if self.countdown > 0:
            self.countdown_label.setText(f"{self.countdown}秒后开始下一次循环")
            QtCore.QTimer.singleShot(1000, self.update_rest_countdown)
        else:
            self.countdown_label.hide()
            self.current_loop += 1
            self.start_loop()

    def update_end_countdown(self):
        self.countdown -= 1
        if self.countdown > 0:
            self.countdown_label.setText(f"实验将于{self.countdown}秒后结束")
            QtCore.QTimer.singleShot(1000, self.update_end_countdown)
        else:
            self.countdown_label.hide()

            # ==== 整个实验结束：先停止 EEG 保存，再写 txt 报告 ====
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

            self.save_report()
            self.reset_ui()

    # ========== 与 Page2（EEG 页面）的时间戳交互辅助函数 ==========

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

    def _record_loop_start_hw(self, loop_index: int):
        """
        记录第 loop_index 个 loop 的开始片上时间。
        在 show_task() 中，当 current_index == 0 时调用。
        """
        hw = self._get_hw_timestamp_from_eeg()
        if hw is None:
            return
        if 0 <= loop_index < self.loops:
            self.loop_hw_start[loop_index] = hw
            if self.hw_exp_start is None:
                self.hw_exp_start = hw

    def _record_loop_end_hw(self, loop_index: int):
        """
        记录第 loop_index 个 loop 的结束片上时间。
        在 end_loop() 中调用。
        """
        hw = self._get_hw_timestamp_from_eeg()
        if hw is None:
            return
        if 0 <= loop_index < self.loops:
            self.loop_hw_end[loop_index] = hw
            self.hw_exp_end = hw

    # ========== 报告与复位 ==========

    def save_report(self):
        """
        将本次心算实验写入 txt 报告。

        每一行格式：
            loop_start_hw,loop_end_hw,mental_calc,rec_str,acc

        其中：
          - loop_start_hw / loop_end_hw 为该 loop 的开始/结束片上时间（秒）；
          - rec_str 形如：
              1+2=3TT|4-1=1FT|5+6=10FN ...
            （最后的 T/F/N 表示被试作答是否正确 / 未作答）
          - acc 为该轮正确率。

        报告文件保存在：
            data/calc/<Name>/<YYYYMMDDHHMMSS>/Calc_*.txt
        """
        # 确定被试名称
        name = (
            self.current_user_name
            or self.name
            or self.name_input.text().strip()
            or "unknown"
        )
        mode = "split" if self.separate_phases else "normal"

        # 优先使用本次 run 的目录：data/calc/<name>/<timestamp>
        base_dir = self.run_dir or self.user_dir or self.ma_root
        os.makedirs(base_dir, exist_ok=True)

        # 文件名里的时间戳：优先用 run_timestamp，兜底用当前时间
        ts_for_name = self.run_timestamp or datetime.now().strftime('%Y%m%d%H%M%S')

        fname = os.path.join(
            base_dir,
            f"Calc_{name}_{ts_for_name}_"
            f"loops{self.loops}_trials{self.trials}_delay{self.delay}_{mode}.txt"
        )

        with open(fname, 'w', encoding='utf-8') as f:
            for i in range(self.loops):
                records = self.results_per_loop[i]

                rec_str = '|'.join(
                    (
                        # 未作答：在正确答案标记后面加 N
                        f"{expr}={disp}{'T' if flag else 'F'}N"
                        if user_input is None
                        # 有作答：在正确答案标记后面加 T/F（保持原有格式）
                        else f"{expr}={disp}{'T' if flag else 'F'}{'T' if user_input else 'F'}"
                    )
                    for expr, disp, flag, user_input in records
                )

                correct_count = sum(
                    1 for expr, disp, flag, user_input in records
                    if user_input is not None and user_input == flag
                )
                acc = (correct_count / len(records)) if records else 0.0

                # 硬件时间
                start_hw = self.loop_hw_start[i] if i < len(self.loop_hw_start) else None
                end_hw = self.loop_hw_end[i] if i < len(self.loop_hw_end) else None
                start_val = start_hw if isinstance(start_hw, (int, float)) else float('nan')
                end_val = end_hw if isinstance(end_hw, (int, float)) else float('nan')

                f.write(
                    f"{start_val:.6f},{end_val:.6f},"
                    f"mental_calc,{rec_str},{acc:.2f}\n"
                )

    def reset_ui(self):
        self.current_loop = 0
        self.current_index = 0
        self.sequence = []
        self.results_per_loop = []
        self.response_recorded = False
        self.input_enabled = False

        # 重置时间记录
        self.hw_exp_start = None
        self.hw_exp_end = None
        self.loop_hw_start = []
        self.loop_hw_end = []

        # 重置目录相关
        self.current_user_name = None
        self.user_dir = None
        self.run_dir = None
        self.run_timestamp = None

        self.task_label.hide()
        self.btn_container.hide()
        self.feedback_label.hide()
        self.countdown_label.hide()

        self.instruction_label.show()
        self.name_input.parent().show()
        self.start_btn.show()
        self.name_input.setFocus()

    def keyPressEvent(self, event):
        # 实际处理靠 QShortcut，这里保持默认
        super().keyPressEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = Page6Widget()
    w.show()
    sys.exit(app.exec())
