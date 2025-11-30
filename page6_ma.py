# import os
# import sys
# import random
# from datetime import datetime
# from PyQt6 import QtCore, QtGui, QtWidgets
# from PyQt6.QtWidgets import (
#     QApplication,
#     QWidget,
#     QVBoxLayout,
#     QFormLayout,
#     QLabel,
#     QLineEdit,
#     QSpinBox,
#     QDoubleSpinBox,
#     QPushButton,
#     QMessageBox,
# )
# from PyQt6.QtGui import QKeySequence, QShortcut

# # 支持的运算符
# OPERATIONS = ['+', '-']


# class Page6Widget(QWidget):
#     """
#     心算实验页面（Page6）

#     时间记录逻辑：
#       - 使用 Page2 提供的 get_last_eeg_time()，获取与 CSV Time 列一致的
#         “校准后的电脑时间轴”（秒）；
#       - 每个 loop 的开始/结束时间，记录在 loop_eeg_start / loop_eeg_end；
#       - save_report() 中每一行第 1、2 列就是该 loop 的开始/结束时间，
#         可直接在 CSV 中用 Time 范围切片。
#     """

#     def __init__(self, parent=None):
#         super().__init__(parent)
#         self.setWindowTitle("心算实验")

#         # ====== Mental Calc 数据根目录：data/ma ======
#         self.data_root = "data"
#         self.ma_root = os.path.join(self.data_root, "ma")
#         os.makedirs(self.ma_root, exist_ok=True)

#         # 当前被试 & 本次实验 run 的目录
#         self.current_user_name: str | None = None
#         self.user_dir: str | None = None       # data/ma/<name>
#         self.run_dir: str | None = None        # data/ma/<name>/<timestamp>
#         self.run_timestamp: str | None = None  # YYYYMMDDHHMMSS

#         # 默认参数
#         self.name = ""
#         self.loops = 6
#         self.trials = 10
#         self.delay = 4.0  # 单个阶段时长（展示期 / 判断期）
#         self.max_operand = 100
#         self.initial_countdown = 10  # 实验开始前倒计时
#         self.rest_duration = 10      # 循环间休息倒计时
#         self.separate_phases = False  # 是否分离展示与判断

#         # 状态变量
#         self.current_loop = 0
#         self.current_index = 0
#         self.sequence = []  # (expr, disp, actual_flag)
#         # 每题记录: (expr, disp, actual_flag, user_input_flag or None)
#         self.results_per_loop = []
#         self.response_recorded = False
#         self.input_enabled = False  # 控制输入是否有效

#         # 与 EEG 采集页面（Page2）联动
#         # 需要在主程序中设置：page6.eeg_page = page2
#         self.eeg_page = None
#         # 整个实验的开始/结束时间（与 CSV Time 使用同一“校准电脑时间”轴）
#         self.eeg_exp_start = None
#         self.eeg_exp_end = None
#         # 每个 loop 的开始/结束时间（写入 txt）
#         self.loop_eeg_start = []
#         self.loop_eeg_end = []

#         # ===== 布局 =====
#         root_layout = QVBoxLayout(self)
#         root_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

#         self.main_container = QWidget()
#         self.main_container.setFixedWidth(600)
#         layout = QVBoxLayout(self.main_container)
#         layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
#         root_layout.addWidget(self.main_container, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

#         # 操作提示标签
#         self.instruction_label = QLabel(
#             "请按左方向键表示算式【正确】，按右方向键表示算式【错误】。\n"
#             "算式格式如 “1 + 1 = 2”，请在规定时间内完成判断。"
#         )
#         instr_font = self.instruction_label.font()
#         instr_font.setPointSize(14)
#         self.instruction_label.setFont(instr_font)
#         self.instruction_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
#         self.instruction_label.setWordWrap(True)
#         self.instruction_label.setFixedWidth(500)
#         fm = QtGui.QFontMetrics(instr_font)
#         self.instruction_label.setMinimumHeight(fm.lineSpacing() * 2 + 8)
#         layout.addWidget(self.instruction_label)

#         # 设置区
#         settings = QWidget()
#         settings.setMaximumWidth(400)
#         form = QFormLayout(settings)
#         form.setFormAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

#         self.name_input = QLineEdit()
#         form.addRow("Name:", self.name_input)

#         self.loops_spin = QSpinBox()
#         self.loops_spin.setRange(1, 20)
#         self.loops_spin.setValue(self.loops)
#         form.addRow("Runs:", self.loops_spin)

#         self.trials_spin = QSpinBox()
#         self.trials_spin.setRange(1, 200)
#         self.trials_spin.setValue(self.trials)
#         form.addRow("Trials:", self.trials_spin)

#         self.delay_spin = QDoubleSpinBox()
#         self.delay_spin.setRange(0.2, 10.0)
#         self.delay_spin.setSingleStep(0.2)
#         self.delay_spin.setValue(self.delay)
#         form.addRow("Delay / phase (s):", self.delay_spin)

#         self.operand_spin = QSpinBox()
#         self.operand_spin.setRange(1, 999)
#         self.operand_spin.setValue(self.max_operand)
#         form.addRow("Max Operand:", self.operand_spin)

#         # 是否分离展示与操作
#         self.split_checkbox = QtWidgets.QCheckBox("是（先展示，后作答）")
#         self.split_checkbox.setChecked(False)
#         form.addRow("展示/操作分离:", self.split_checkbox)

#         self.start_btn = QPushButton("Start Calculation")
#         self.start_btn.clicked.connect(self.start_experiment)
#         layout.addWidget(settings)
#         layout.addWidget(self.start_btn, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

#         # 倒计时标签
#         self.countdown_label = QLabel("")
#         font_cd = self.countdown_label.font()
#         font_cd.setPointSize(24)
#         self.countdown_label.setFont(font_cd)
#         self.countdown_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
#         self.countdown_label.hide()
#         layout.addWidget(self.countdown_label)

#         # 题目标签
#         self.task_label = QLabel("")
#         font_task = self.task_label.font()
#         font_task.setPointSize(48)
#         self.task_label.setFont(font_task)
#         self.task_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
#         self.task_label.setFixedWidth(500)
#         self.task_label.hide()
#         layout.addWidget(self.task_label)

#         # 固定高度按钮容器，保证布局稳定
#         self.btn_container = QWidget()
#         self.btn_container.setFixedHeight(80)
#         self.btn_container.setFixedWidth(400)
#         btn_layout = QtWidgets.QHBoxLayout(self.btn_container)
#         btn_layout.setContentsMargins(0, 0, 0, 0)
#         btn_layout.setSpacing(40)
#         btn_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

#         self.btn_true = QPushButton("正确")
#         self.btn_false = QPushButton("错误")
#         for btn in (self.btn_true, self.btn_false):
#             btn.setCheckable(True)
#             btn.setFixedSize(120, 50)

#         btn_style = (
#             "QPushButton{background-color:#4caf50;color:white;font-size:16px;}"
#             "QPushButton:checked{background-color:#388e3c;}"
#             "QPushButton:disabled{background-color:gray;}"
#             "QPushButton:disabled:checked{background-color:#388e3c;}"
#         )
#         self.btn_true.setStyleSheet(btn_style)
#         self.btn_false.setStyleSheet(btn_style)

#         self.btn_true.clicked.connect(lambda: self.record_response(True))
#         self.btn_false.clicked.connect(lambda: self.record_response(False))

#         btn_layout.addWidget(self.btn_true)
#         btn_layout.addWidget(self.btn_false)

#         self.btn_container.hide()
#         layout.addWidget(self.btn_container, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

#         # 反馈 / 提示标签
#         self.feedback_label = QLabel("")
#         font_fb = self.feedback_label.font()
#         font_fb.setPointSize(20)
#         self.feedback_label.setFont(font_fb)
#         self.feedback_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
#         self.feedback_label.setFixedHeight(40)
#         self.feedback_label.setFixedWidth(500)
#         self.feedback_label.setStyleSheet("border:none;")
#         self.feedback_label.hide()
#         layout.addWidget(self.feedback_label)

#         # 键盘快捷键
#         self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
#         self.shortcut_left = QShortcut(QKeySequence(QtCore.Qt.Key.Key_Left), self)
#         self.shortcut_left.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
#         self.shortcut_left.activated.connect(lambda: self.record_response(True))
#         self.shortcut_right = QShortcut(QKeySequence(QtCore.Qt.Key.Key_Right), self)
#         self.shortcut_right.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
#         self.shortcut_right.activated.connect(lambda: self.record_response(False))

#     # ============ 与 Page2 的时间交互 ============

#     def _get_eeg_time_from_page(self):
#         """
#         从 Page2 获取当前最新的 EEG 时间（秒），
#         使用的是与 CSV Time 列一致的“校准后的电脑时间轴”。
#         若未能获取则返回 None。
#         """
#         eeg_page = getattr(self, "eeg_page", None)
#         if eeg_page is None:
#             return None
#         getter = getattr(eeg_page, "get_last_eeg_time", None)
#         if getter is None:
#             return None
#         try:
#             return getter()
#         except Exception:
#             return None

#     def _record_loop_start_time(self, loop_index: int):
#         """
#         记录第 loop_index 个 loop 的开始时间（校准后的电脑时间）。
#         在 show_task() 中，当 current_index == 0 时调用。
#         """
#         t = self._get_eeg_time_from_page()
#         if t is None:
#             return
#         if 0 <= loop_index < self.loops:
#             self.loop_eeg_start[loop_index] = t
#             if self.eeg_exp_start is None:
#                 self.eeg_exp_start = t

#     def _record_loop_end_time(self, loop_index: int):
#         """
#         记录第 loop_index 个 loop 的结束时间（校准后的电脑时间）。
#         在 end_loop() 中调用。
#         """
#         t = self._get_eeg_time_from_page()
#         if t is None:
#             return
#         if 0 <= loop_index < self.loops:
#             self.loop_eeg_end[loop_index] = t
#             self.eeg_exp_end = t

#     # ============ 实验流程 ============

#     def start_experiment(self):
#         name = self.name_input.text().strip()
#         if not name:
#             QMessageBox.warning(self, "错误", "请输入姓名！")
#             return

#         # 1. 检查 Page2 是否在监听 EEG 数据
#         eeg_page = getattr(self, "eeg_page", None)
#         if eeg_page is None or not hasattr(eeg_page, "is_listening"):
#             QMessageBox.warning(
#                 self,
#                 "错误",
#                 "未找到 EEG 采集页面，请在主程序中确保已创建并注入 Page2Widget。"
#             )
#             return

#         if not eeg_page.is_listening():
#             QMessageBox.warning(
#                 self,
#                 "提示",
#                 "请先在【首页】点击“开始监测信号”，\n"
#                 "确保已经开始接收EEG数据后，再启动心算实验。"
#             )
#             return

#         # 2. 构建目录结构：data/ma/<name>/<timestamp>/
#         self.current_user_name = name
#         self.user_dir = os.path.join(self.ma_root, self.current_user_name)
#         os.makedirs(self.user_dir, exist_ok=True)

#         self.run_timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
#         self.run_dir = os.path.join(self.user_dir, self.run_timestamp)
#         os.makedirs(self.run_dir, exist_ok=True)

#         # 3. 读取参数 & 初始化状态
#         self.name = name
#         self.loops = self.loops_spin.value()
#         self.trials = self.trials_spin.value()
#         self.delay = self.delay_spin.value()
#         self.max_operand = self.operand_spin.value()
#         self.separate_phases = self.split_checkbox.isChecked()

#         self.current_loop = 1
#         self.results_per_loop = [[] for _ in range(self.loops)]

#         self.sequence = []
#         self.response_recorded = False
#         self.input_enabled = False

#         # 初始化时间记录（统一使用“校准后的电脑时间”）
#         self.eeg_exp_start = None
#         self.eeg_exp_end = None
#         self.loop_eeg_start = [None] * self.loops
#         self.loop_eeg_end = [None] * self.loops

#         # ==== 关键：在“有效点击 Start Calculation”后立刻开始保存 EEG CSV ====
#         if hasattr(eeg_page, "start_saving"):
#             try:
#                 # 把本次实验的 run_dir 传给 Page2，让 EEG CSV & markers.csv 写到同一目录
#                 eeg_page.start_saving(self.run_dir)
#             except Exception:
#                 # Page2 内部处理错误，这里不中断心算实验
#                 pass

#         # 尝试记录实验整体起始时间（校准后的 EEG 时间轴）
#         first_time = self._get_eeg_time_from_page()
#         if first_time is not None:
#             self.eeg_exp_start = first_time

#         self.instruction_label.hide()
#         self.name_input.parent().hide()
#         self.start_btn.hide()

#         # 初始倒计时（仅界面，不再用于时间计算）
#         self.countdown = self.initial_countdown
#         self.countdown_label.setText(f"{self.countdown}秒后开始心算实验")
#         self.countdown_label.show()
#         QtCore.QTimer.singleShot(1000, self.update_initial_countdown)

#     def update_initial_countdown(self):
#         self.countdown -= 1
#         if self.countdown > 0:
#             self.countdown_label.setText(f"{self.countdown}秒后开始心算实验")
#             QtCore.QTimer.singleShot(1000, self.update_initial_countdown)
#         else:
#             self.countdown_label.hide()
#             self.start_loop()

#     def start_loop(self):
#         # 生成本轮题目
#         ops = OPERATIONS
#         correct_flags = [True] * (self.trials // 2) + [False] * (self.trials - self.trials // 2)
#         random.shuffle(correct_flags)

#         self.sequence = []
#         used = set()
#         for flag in correct_flags:
#             while True:
#                 a = random.randint(1, self.max_operand)
#                 b = random.randint(1, self.max_operand)
#                 op = random.choice(ops)
#                 expr = f"{a} {op} {b}"
#                 true_val = eval(expr)
#                 if flag:
#                     disp = true_val
#                 else:
#                     offset_choices = [i for i in range(-3, 4) if i != 0]
#                     disp = true_val + random.choice(offset_choices)
#                     if disp < 0:
#                         continue
#                 if (expr, disp) not in used:
#                     used.add((expr, disp))
#                     self.sequence.append((expr, disp, flag))
#                     break

#         self.current_index = 0
#         self.task_label.show()
#         self.feedback_label.show()
#         self.btn_container.show()
#         self.show_task()

#     def show_task(self):
#         if self.current_index >= len(self.sequence):
#             self.end_loop()
#             return

#         # 若是本轮的第一题，记录 loop 开始时间（校准后的 EEG 时间）
#         if self.current_index == 0:
#             self._record_loop_start_time(self.current_loop - 1)

#         # 重置当前 trial 状态
#         self.response_recorded = False
#         self.input_enabled = False
#         self.btn_true.setChecked(False)
#         self.btn_false.setChecked(False)
#         self.btn_true.setEnabled(False)
#         self.btn_false.setEnabled(False)
#         self.feedback_label.clear()
#         self.feedback_label.setStyleSheet("border:none;")

#         expr, disp, _ = self.sequence[self.current_index]
#         self.task_label.setText(f"{expr} = {disp}")
#         self.activateWindow()
#         self.setFocus()

#         if self.separate_phases:
#             # 展示期：按钮隐藏（容器仍在），禁止输入
#             self.btn_true.hide()
#             self.btn_false.hide()
#             self.feedback_label.setText("请思考")
#             self.feedback_label.setStyleSheet("color:black;border:none;")
#             QtCore.QTimer.singleShot(int(self.delay * 1000), self.start_response_phase)
#         else:
#             # 非分离：整个 delay 内可作答
#             self.btn_true.show()
#             self.btn_false.show()
#             self.feedback_label.setText("")
#             QtCore.QTimer.singleShot(200, self.enable_inputs)
#             QtCore.QTimer.singleShot(int(self.delay * 1000), self.next_task)

#     def start_response_phase(self):
#         # 分离模式：从展示期进入判断期
#         if self.current_index >= len(self.sequence):
#             return

#         self.btn_true.show()
#         self.btn_false.show()
#         self.btn_true.setEnabled(True)
#         self.btn_false.setEnabled(True)
#         self.input_enabled = True

#         self.feedback_label.setText("现在判断：左=正确，右=错误")
#         self.feedback_label.setStyleSheet("color:black;border:none;")

#         # 判断期持续 delay 秒
#         QtCore.QTimer.singleShot(int(self.delay * 1000), self.finish_trial)

#     def enable_inputs(self):
#         # 非分离模式启用输入
#         if not self.separate_phases and self.current_index < len(self.sequence):
#             self.input_enabled = True
#             self.btn_true.setEnabled(True)
#             self.btn_false.setEnabled(True)

#     def record_response(self, user_says_true: bool):
#         if not self.input_enabled or self.response_recorded or self.current_index >= len(self.sequence):
#             return

#         expr, disp, flag = self.sequence[self.current_index]
#         self.results_per_loop[self.current_loop - 1].append((expr, disp, flag, user_says_true))
#         self.response_recorded = True
#         self.input_enabled = False

#         self.btn_true.setEnabled(False)
#         self.btn_false.setEnabled(False)
#         if user_says_true:
#             self.btn_true.setChecked(True)
#         else:
#             self.btn_false.setChecked(True)

#         is_correct = (user_says_true == flag)
#         mark = "✔" if is_correct else "❌"
#         color = "green" if is_correct else "red"
#         self.feedback_label.setText(mark)
#         self.feedback_label.setStyleSheet(f"color:{color};border:none;")

#     def next_task(self):
#         # 非分离模式：delay 结束，若无作答则记 None
#         if self.separate_phases:
#             return

#         if self.current_index < len(self.sequence) and not self.response_recorded:
#             expr, disp, flag = self.sequence[self.current_index]
#             self.results_per_loop[self.current_loop - 1].append((expr, disp, flag, None))

#         self.current_index += 1
#         self.show_task()

#     def finish_trial(self):
#         # 分离模式：判断期结束
#         if not self.separate_phases or self.current_index >= len(self.sequence):
#             return

#         if not self.response_recorded:
#             expr, disp, flag = self.sequence[self.current_index]
#             self.results_per_loop[self.current_loop - 1].append((expr, disp, flag, None))

#         self.current_index += 1
#         self.show_task()

#     def end_loop(self):
#         # 记录本轮结束时的时间（校准后的 EEG 时间）
#         self._record_loop_end_time(self.current_loop - 1)

#         self.task_label.hide()
#         self.btn_container.hide()
#         self.feedback_label.hide()

#         if self.current_loop == self.loops:
#             self.countdown = self.initial_countdown
#             self.countdown_label.setText(f"实验将于{self.countdown}秒后结束")
#             self.countdown_label.show()
#             QtCore.QTimer.singleShot(1000, self.update_end_countdown)
#         else:
#             self.countdown = self.rest_duration
#             self.countdown_label.setText(f"{self.countdown}秒后开始下一次循环")
#             self.countdown_label.show()
#             QtCore.QTimer.singleShot(1000, self.update_rest_countdown)

#     def update_rest_countdown(self):
#         self.countdown -= 1
#         if self.countdown > 0:
#             self.countdown_label.setText(f"{self.countdown}秒后开始下一次循环")
#             QtCore.QTimer.singleShot(1000, self.update_rest_countdown)
#         else:
#             self.countdown_label.hide()
#             self.current_loop += 1
#             self.start_loop()

#     def update_end_countdown(self):
#         self.countdown -= 1
#         if self.countdown > 0:
#             self.countdown_label.setText(f"实验将于{self.countdown}秒后结束")
#             QtCore.QTimer.singleShot(1000, self.update_end_countdown)
#         else:
#             self.countdown_label.hide()

#             # ==== 整个实验结束：先停止 EEG 保存，再写 txt 报告 ====
#             eeg_page = getattr(self, "eeg_page", None)
#             if eeg_page is not None:
#                 last_time = self._get_eeg_time_from_page()
#                 if last_time is not None:
#                     self.eeg_exp_end = last_time
#                 if hasattr(eeg_page, "stop_saving"):
#                     try:
#                         eeg_page.stop_saving()
#                     except Exception:
#                         pass

#             self.save_report()
#             self.reset_ui()

#     # ========== 报告与复位 ==========

#     def save_report(self):
#         """
#         将本次心算实验写入 txt 报告。

#         每一行格式：
#             loop_start_time,loop_end_time,mental_calc,rec_str,acc

#         其中：
#           - loop_start_time / loop_end_time 为该 loop 的开始/结束时间（秒），
#             使用的是与 CSV Time 列一致的“校准后的电脑时间轴”；
#           - rec_str 形如：
#               1+2=3TT|4-1=1FT|5+6=10FN ...
#             其中：
#               第一个 T/F = 题目结果是否正确（ground truth）
#               第二个 T/F/N = 被试判断正确/错误/未作答
#           - acc 为该轮正确率。

#         报告文件保存在：
#             data/ma/<Name>/<YYYYMMDDHHMMSS>/Calc_*.txt
#         """
#         # 确定被试名称
#         name = (
#             self.current_user_name
#             or self.name
#             or self.name_input.text().strip()
#             or "unknown"
#         )
#         mode = "split" if self.separate_phases else "normal"

#         # 优先使用本次 run 的目录：data/ma/<name>/<timestamp>
#         base_dir = self.run_dir or self.user_dir or self.ma_root
#         os.makedirs(base_dir, exist_ok=True)

#         # 文件名里的时间戳：优先用 run_timestamp，兜底用当前时间
#         ts_for_name = self.run_timestamp or datetime.now().strftime('%Y%m%d%H%M%S')

#         fname = os.path.join(
#             base_dir,
#             f"MA_{name}_{ts_for_name}_"
#             f"loops{self.loops}_trials{self.trials}_delay{self.delay}_{mode}.txt"
#         )

#         with open(fname, 'w', encoding='utf-8') as f:
#             for i in range(self.loops):
#                 records = self.results_per_loop[i]

#                 rec_str = '|'.join(
#                     (
#                         # 未作答：题目真值后加 N
#                         f"{expr}={disp}{'T' if flag else 'F'}N"
#                         if user_input is None
#                         # 有作答：题目真值后加 T/F
#                         else f"{expr}={disp}{'T' if flag else 'F'}{'T' if user_input == flag else 'F'}"
#                     )
#                     for expr, disp, flag, user_input in records
#                 )

#                 correct_count = sum(
#                     1 for expr, disp, flag, user_input in records
#                     if user_input is not None and (user_input == flag)
#                 )
#                 acc = (correct_count / len(records)) if records else 0.0

#                 # 本轮开始/结束时间（校准后的 EEG 时间）
#                 start_t = self.loop_eeg_start[i] if i < len(self.loop_eeg_start) else None
#                 end_t = self.loop_eeg_end[i] if i < len(self.loop_eeg_end) else None
#                 start_val = start_t if isinstance(start_t, (int, float)) else float('nan')
#                 end_val = end_t if isinstance(end_t, (int, float)) else float('nan')

#                 f.write(
#                     f"{start_val:.6f},{end_val:.6f},"
#                     f"mental_calc,{rec_str},{acc:.2f}\n"
#                 )

#     def reset_ui(self):
#         self.current_loop = 0
#         self.current_index = 0
#         self.sequence = []
#         self.results_per_loop = []
#         self.response_recorded = False
#         self.input_enabled = False

#         # 重置时间记录
#         self.eeg_exp_start = None
#         self.eeg_exp_end = None
#         self.loop_eeg_start = []
#         self.loop_eeg_end = []

#         # 重置目录相关
#         self.current_user_name = None
#         self.user_dir = None
#         self.run_dir = None
#         self.run_timestamp = None

#         self.task_label.hide()
#         self.btn_container.hide()
#         self.feedback_label.hide()
#         self.countdown_label.hide()

#         self.instruction_label.show()
#         self.name_input.parent().show()
#         self.start_btn.show()
#         self.name_input.setFocus()

#     def keyPressEvent(self, event):
#         # 实际处理靠 QShortcut，这里保持默认
#         super().keyPressEvent(event)


# if __name__ == "__main__":
#     app = QApplication(sys.argv)
#     w = Page6Widget()
#     w.show()
#     sys.exit(app.exec())

import os
import sys
import random
import json
import csv
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
    QHBoxLayout,
)
from PyQt6.QtGui import QKeySequence, QShortcut

# 支持的运算符
OPERATIONS = ['+', '-']


class Page6Widget(QWidget):
    """
    心算实验页面（Page6）

    时间 & 文件记录逻辑（新版，对齐 Page7）：
      - 被试与参数设置页面为“卡片”布局，点击【开始实验】后：
          * 检查 Page2 是否已开始监测信号（is_listening）；
          * 在 data/ma/<Name>/<YYYYMMDDHHMMSS>/ 下创建本次 run 目录；
          * 调用 Page2.start_saving(run_dir)，开始写 EEG CSV 和 triggers.csv。
      - 每个 loop（Run）：
          * 在 loop 开始时通过 Page2.set_trigger(loop_start_code) 写入一次 trigger；
          * 在 loop 结束时通过 Page2.set_trigger(loop_end_code) 写入一次 trigger；
      - 实验自然结束或 ESC 中断时：
          * 调用 Page2.stop_saving() 关闭 EEG 与 trigger 文件；
          * Page6 读取本次 run_dir 下的 triggers.csv，筛选出属于心算实验的
            loop_start / loop_end trigger，按出现顺序为每个 loop 回填
            loop_start_time / loop_end_time；
          * save_report() 中，每一行的第 1、2 列即为该 loop 的 EEG 时间范围，
            可用来在 EEG CSV 中做切片。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("心算实验")
        self.setMinimumSize(900, 700)

        # 当前系统类型（用于全屏窗口策略）
        self._is_macos = sys.platform.startswith("darwin")
        self._is_windows = sys.platform.startswith("win")
        self.fullscreen_win: QtWidgets.QWidget | None = None
        self._fs_esc_shortcut: QShortcut | None = None

        # ====== Mental Calc 数据根目录：data/ma ======
        self.data_root = "data"
        self.ma_root = os.path.join(self.data_root, "ma")
        os.makedirs(self.ma_root, exist_ok=True)

        # 当前被试 & 本次实验 run 的目录
        self.current_user_name: str | None = None
        self.user_dir: str | None = None       # data/ma/<name>
        self.run_dir: str | None = None        # data/ma/<name>/<timestamp>
        self.run_timestamp: str | None = None  # YYYYMMDDHHMMSS

        # ===== 默认参数（可在首页调整） =====
        self.name = ""
        self.loops = 6          # 循环次数（Runs）
        self.trials = 10        # 每个 loop 内的题目数
        self.delay = 4.0        # 单个阶段时长（展示期 / 判断期）
        self.max_operand = 100  # 操作数上限
        self.initial_countdown = 10  # 实验开始前倒计时（秒）
        self.rest_duration = 10      # 循环间休息倒计时（秒）
        self.separate_phases = False  # 是否分离展示与判断

        # ===== 触发器（trigger）相关（专用于心算实验） =====
        # 这里只使用 2 个 code 标记每个 loop 的区间：
        #   1: loop_start   第 n 个 loop 开始
        #   2: loop_end     第 n 个 loop 结束
        self.triggers_filename = "triggers.csv"
        self.trigger_codes: dict[str, int] = {
            "loop_start": 1,
            "loop_end": 2,
        }
        # 仅用于写 meta.json，方便后续统一解释
        self.trigger_code_labels: dict[int, str] = {
            0: "baseline",
            1: "loop_start",
            2: "loop_end",
        }

        # ===== 状态变量 =====
        self.current_loop = 0
        self.current_index = 0           # 当前 loop 中题目的索引
        self.sequence: list[tuple[str, int, bool]] = []  # (expr, disp, actual_flag)
        # 每题记录: (expr, disp, actual_flag, user_input_flag or None)
        self.results_per_loop: list[list[tuple[str, int, bool, bool | None]]] = []
        self.response_recorded = False
        self.input_enabled = False
        self.is_running = False          # 是否处于一次完整实验流程中

        # 与 EEG 采集页面（Page2）联动
        # 需要在主程序中设置：page6.eeg_page = page2
        self.eeg_page = None
        self.eeg_exp_start: float | None = None
        self.eeg_exp_end: float | None = None
        self.loop_eeg_start: list[float | None] = []
        self.loop_eeg_end: list[float | None] = []

        # ====== UI 相关状态 ======
        self._current_bg: str | None = None  # stage_label 的背景色
        self._current_fg: str = "#000000"
        self._countdown_updater: QtCore.QTimer | None = None
        self._countdown_value: int = 0
        self._countdown_template: str = ""

        # 实际 UI 构建
        self._build_main_ui()
        self._build_screen_ui()
        self._build_shortcuts()

    # ==================== 首页：表单 + 按钮（与 Page7 风格统一） ====================
    def _build_main_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 30, 40, 30)
        root.setSpacing(20)
        root.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.root_layout = root

        # 中心卡片：放说明 + 表单 + 按钮
        self.center_card = QtWidgets.QWidget(self)
        self.center_card.setObjectName("centerCard")
        self.center_card.setMaximumWidth(640)

        card_layout = QVBoxLayout(self.center_card)
        card_layout.setContentsMargins(40, 30, 40, 30)
        card_layout.setSpacing(20)
        card_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        # 顶部说明
        self.instruction_label = QLabel(
            "填写信息后点击开始。\n"
            "任务：判断算式是否正确。\n"
            "按【← 左方向键】表示算式“正确”，按【→ 右方向键】表示算式“错误”。"
        )
        self.instruction_label.setObjectName("instructionLabel")
        f = self.instruction_label.font()
        f.setPointSize(13)
        self.instruction_label.setFont(f)
        self.instruction_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.instruction_label.setWordWrap(True)
        card_layout.addWidget(self.instruction_label)

        # 配置表单区域
        self.settings_widget = QtWidgets.QWidget(self.center_card)
        form = QFormLayout(self.settings_widget)
        form.setFormAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        form.setLabelAlignment(
            QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)

        self.name_input = QLineEdit()
        form.addRow("Name:", self.name_input)

        self.loops_spin = QSpinBox()
        self.loops_spin.setRange(1, 20)
        self.loops_spin.setValue(self.loops)
        form.addRow("Runs:", self.loops_spin)

        self.trials_spin = QSpinBox()
        self.trials_spin.setRange(1, 200)
        self.trials_spin.setValue(self.trials)
        form.addRow("Trials per Run:", self.trials_spin)

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

        card_layout.addWidget(self.settings_widget)

        # 开始按钮
        self.start_btn = QPushButton("开始心算实验")
        self.start_btn.setObjectName("startButton")
        self.start_btn.clicked.connect(self.on_start_clicked)
        card_layout.addWidget(self.start_btn, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        root.addStretch()
        root.addWidget(self.center_card, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)
        root.addStretch()

    # ==================== 实验显示界面（全屏窗口内容，与 Page7 风格统一） ====================
    def _build_screen_ui(self):
        self.screen_container = QtWidgets.QWidget(self)
        self.screen_container.setObjectName("full_screen")
        self.screen_container.hide()

        screen_layout = QVBoxLayout(self.screen_container)
        screen_layout.setContentsMargins(40, 40, 40, 40)
        screen_layout.setSpacing(18)

        screen_layout.addStretch()

        # 主文字区域（用于显示算式或提示）
        self.stage_label = QLabel("", self.screen_container)
        fs = self.stage_label.font()
        fs.setPointSize(48)
        self.stage_label.setFont(fs)
        self.stage_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.stage_label.setWordWrap(True)
        self.stage_label.setMinimumWidth(800)
        self.stage_label.hide()

        stage_wrapper = QtWidgets.QWidget(self.screen_container)
        h = QHBoxLayout(stage_wrapper)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addStretch()
        h.addWidget(self.stage_label)
        h.addStretch()
        screen_layout.addWidget(stage_wrapper)

        # 倒计时文字（初始 / 休息 / 结束提示）
        self.countdown_label = QLabel("", self.screen_container)
        fc = self.countdown_label.font()
        fc.setPointSize(42)
        self.countdown_label.setFont(fc)
        self.countdown_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.countdown_label.hide()
        screen_layout.addWidget(self.countdown_label, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        # 按钮容器（判断“正确 / 错误”）
        self.btn_container = QtWidgets.QWidget(self.screen_container)
        self.btn_container.setFixedHeight(80)
        self.btn_container.setFixedWidth(400)
        btn_layout = QtWidgets.QHBoxLayout(self.btn_container)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(40)
        btn_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        self.btn_true = QPushButton("正确", self.screen_container)
        self.btn_false = QPushButton("错误", self.screen_container)
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
        screen_layout.addWidget(self.btn_container, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        # 反馈标签（✔ / ❌）
        self.feedback_label = QLabel("", self.screen_container)
        font_fb = self.feedback_label.font()
        font_fb.setPointSize(20)
        self.feedback_label.setFont(font_fb)
        self.feedback_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.feedback_label.setFixedHeight(40)
        self.feedback_label.setFixedWidth(500)
        self.feedback_label.setStyleSheet("border:none;")
        self.feedback_label.hide()
        screen_layout.addWidget(self.feedback_label, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        screen_layout.addStretch()

    # ==================== 全局快捷键 ====================
    def _build_shortcuts(self):
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)

        # 左 / 右 方向键判断
        self.shortcut_left = QShortcut(QKeySequence(QtCore.Qt.Key.Key_Left), self)
        self.shortcut_left.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
        self.shortcut_left.activated.connect(lambda: self.record_response(True))

        self.shortcut_right = QShortcut(QKeySequence(QtCore.Qt.Key.Key_Right), self)
        self.shortcut_right.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
        self.shortcut_right.activated.connect(lambda: self.record_response(False))

        # ESC 中断本次实验
        self.shortcut_esc = QShortcut(QKeySequence(QtCore.Qt.Key.Key_Escape), self)
        self.shortcut_esc.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
        self.shortcut_esc.activated.connect(self.abort_and_finalize)

    # ==================== 与 Page2 的 trigger 交互 ====================
    def _send_trigger(self, code: int):
        """
        将 trigger 发送给 Page2，由 Page2 决定在 triggers.csv 的哪个时间点写入。
        """
        if code is None or code <= 0:
            return
        eeg_page = getattr(self, "eeg_page", None)
        if eeg_page is None:
            return
        setter = getattr(eeg_page, "set_trigger", None)
        if setter is None:
            return
        try:
            setter(int(code))
        except Exception:
            pass

    def _send_loop_trigger(self, stage: str):
        """
        根据 stage = 'loop_start' / 'loop_end' 发送对应 trigger。
        """
        code = self.trigger_codes.get(stage)
        if not code:
            return
        self._send_trigger(code)

    # ==================== 入口：开始实验 ====================
    def on_start_clicked(self):
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

        # 2. 构建目录结构：data/ma/<name>/<timestamp>/
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

        self.current_loop = 0        # 将在 _start_first_loop 中设为 1
        self.current_index = 0
        self.sequence = []
        self.results_per_loop = [[] for _ in range(self.loops)]
        self.response_recorded = False
        self.input_enabled = False
        self.is_running = True

        # 初始化时间记录（稍后由 triggers.csv 回填）
        self.eeg_exp_start = None
        self.eeg_exp_end = None
        self.loop_eeg_start = [None] * self.loops
        self.loop_eeg_end = [None] * self.loops

        # 4. 在有效点击 Start 后立刻开始保存 EEG CSV + triggers
        if hasattr(eeg_page, "start_saving"):
            try:
                eeg_page.start_saving(self.run_dir)
            except Exception:
                # Page2 内部处理错误，这里不中断心算实验
                pass

        # ===== UI 切换到全屏实验界面 =====
        self.center_card.hide()
        self._enter_fullscreen()

        # 初始倒计时（仅界面，不再用作时间计算）
        self._show_fullscreen_message(
            "{n}秒后开始心算实验",
            self.initial_countdown,
            bg="#e6ffea",
            fg="#000000",
            plain=False,
            next_callback=self._start_first_loop,
        )

    def _start_first_loop(self):
        if not self.is_running:
            return
        self.current_loop = 1
        self._start_loop()

    # ==================== Loop & Trial 流程 ====================
    def _start_loop(self):
        """
        开始当前 self.current_loop。
        生成本轮题目，发送 loop_start trigger，然后进入第一题。
        """
        if not self.is_running:
            return

        if self.current_loop < 1 or self.current_loop > self.loops:
            return

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
        self.response_recorded = False
        self.input_enabled = False

        # UI 显示区域
        self.stage_label.show()
        self.feedback_label.show()
        self.btn_container.show()
        self.countdown_label.hide()

        # 发送 loop_start trigger
        self._send_loop_trigger("loop_start")

        # 进入第一题
        self._show_task()

    def _show_task(self):
        if not self.is_running:
            return

        if self.current_index >= len(self.sequence):
            self._end_loop()
            return

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
        self.stage_label.setText(f"{expr} = {disp}")
        self.activateWindow()
        self.setFocus()

        if self.separate_phases:
            # 展示期：按钮隐藏，禁止输入
            self.btn_true.hide()
            self.btn_false.hide()
            self.feedback_label.setText("请思考")
            self.feedback_label.setStyleSheet("color:black;border:none;")
            QtCore.QTimer.singleShot(int(self.delay * 1000), self._start_response_phase)
        else:
            # 非分离：整个 delay 内可作答
            self.btn_true.show()
            self.btn_false.show()
            self.feedback_label.setText("")
            QtCore.QTimer.singleShot(200, self._enable_inputs)
            QtCore.QTimer.singleShot(int(self.delay * 1000), self._next_task)

    def _start_response_phase(self):
        # 分离模式：从展示期进入判断期
        if not self.is_running:
            return
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
        QtCore.QTimer.singleShot(int(self.delay * 1000), self._finish_trial)

    def _enable_inputs(self):
        # 非分离模式启用输入
        if not self.is_running:
            return
        if not self.separate_phases and self.current_index < len(self.sequence):
            self.input_enabled = True
            self.btn_true.setEnabled(True)
            self.btn_false.setEnabled(True)

    def record_response(self, user_says_true: bool):
        if not self.is_running:
            return
        if (not self.input_enabled) or self.response_recorded or self.current_index >= len(self.sequence):
            return

        expr, disp, flag = self.sequence[self.current_index]
        # 记录到结果列表
        self.results_per_loop[self.current_loop - 1].append((expr, disp, flag, user_says_true))
        self.response_recorded = True
        self.input_enabled = False

        self.btn_true.setEnabled(False)
        self.btn_false.setEnabled(False)
        if user_says_true:
            self.btn_true.setChecked(True)
        else:
            self.btn_false.setChecked(True)

        is_correct = (user_says_true == flag)
        mark = "✔" if is_correct else "❌"
        color = "green" if is_correct else "red"
        self.feedback_label.setText(mark)
        self.feedback_label.setStyleSheet(f"color:{color};border:none;")

    def _next_task(self):
        # 非分离模式：delay 结束，若无作答则记 None
        if not self.is_running:
            return
        if self.separate_phases:
            return

        if self.current_index < len(self.sequence) and not self.response_recorded:
            expr, disp, flag = self.sequence[self.current_index]
            self.results_per_loop[self.current_loop - 1].append((expr, disp, flag, None))

        self.current_index += 1
        self._show_task()

    def _finish_trial(self):
        # 分离模式：判断期结束
        if not self.is_running:
            return
        if (not self.separate_phases) or self.current_index >= len(self.sequence):
            return

        if not self.response_recorded:
            expr, disp, flag = self.sequence[self.current_index]
            self.results_per_loop[self.current_loop - 1].append((expr, disp, flag, None))

        self.current_index += 1
        self._show_task()

    def _end_loop(self):
        if not self.is_running:
            return

        # 隐藏本轮显示
        self.stage_label.hide()
        self.btn_container.hide()
        self.feedback_label.hide()

        # 发送 loop_end trigger
        self._send_loop_trigger("loop_end")

        if self.current_loop >= self.loops:
            # 最后一轮结束，进入结束倒计时
            self._show_fullscreen_message(
                "实验将于{n}秒后结束",
                self.initial_countdown,
                bg="#e6ffea",
                fg="#000000",
                plain=False,
                next_callback=self._finish_and_save,
            )
        else:
            # 循环间休息
            self._show_fullscreen_message(
                "{n}秒后开始下一次循环",
                self.rest_duration,
                bg="#e6ffea",
                fg="#000000",
                plain=False,
                next_callback=self._start_next_loop,
            )

    def _start_next_loop(self):
        if not self.is_running:
            return
        self.current_loop += 1
        self._start_loop()

    # ========== 实验结束 / 中断 & triggers.csv → loop 时间回填 ==========
    def _update_loop_times_from_triggers(self):
        """
        从当前 run_dir 下的 triggers.csv 中读取 loop_start / loop_end trigger，
        为每个 loop 回填 EEG 时间（秒）。
        """
        self.eeg_exp_start = None
        self.eeg_exp_end = None

        if not self.run_dir:
            return

        path = os.path.join(self.run_dir, self.triggers_filename)
        if not os.path.exists(path):
            return

        events: list[tuple[float, int]] = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                # 跳过表头
                header = next(reader, None)
                for row in reader:
                    if len(row) < 2:
                        continue
                    try:
                        t = float(row[0])
                        code = int(float(row[1]))
                    except Exception:
                        continue
                    if code != 0:
                        events.append((t, code))
        except Exception:
            return

        if not events:
            return

        start_code = self.trigger_codes.get("loop_start")
        end_code = self.trigger_codes.get("loop_end")
        if not start_code or not end_code:
            return

        start_times = [t for (t, c) in events if c == start_code]
        end_times = [t for (t, c) in events if c == end_code]

        # 槽位不够时，未匹配到的设为 NaN
        self.loop_eeg_start = [float("nan")] * self.loops
        self.loop_eeg_end = [float("nan")] * self.loops

        for i in range(self.loops):
            if i < len(start_times):
                self.loop_eeg_start[i] = start_times[i]
            if i < len(end_times):
                self.loop_eeg_end[i] = end_times[i]

        # 计算整体 EEG 实验起止时间
        valid_starts = [t for t in self.loop_eeg_start if isinstance(t, (int, float)) and not (t != t)]
        valid_ends = [t for t in self.loop_eeg_end if isinstance(t, (int, float)) and not (t != t)]
        if valid_starts:
            self.eeg_exp_start = min(valid_starts)
        if valid_ends:
            self.eeg_exp_end = max(valid_ends)

    def _finish_and_save(self):
        """
        实验自然结束：停止 EEG 保存、回填 loop 时间，并写入报告。
        """
        if not self.is_running:
            # 防止重复调用
            return

        self.is_running = False

        eeg_page = getattr(self, "eeg_page", None)
        if eeg_page is not None and hasattr(eeg_page, "stop_saving"):
            try:
                eeg_page.stop_saving()
            except Exception:
                pass

        self._update_loop_times_from_triggers()
        self._save_report(aborted=False)
        self._save_meta_json(aborted=False)
        self.reset_ui()

    def abort_and_finalize(self):
        """
        ESC 中断：尽量停止 EEG 保存、回填已有 loop 时间，并写入 ABORT 报告。
        """
        if not self.is_running:
            return

        self.is_running = False

        eeg_page = getattr(self, "eeg_page", None)
        if eeg_page is not None and hasattr(eeg_page, "stop_saving"):
            try:
                eeg_page.stop_saving()
            except Exception:
                pass

        self._update_loop_times_from_triggers()
        self._save_report(aborted=True)
        self._save_meta_json(aborted=True)
        self.reset_ui()

    # ========== 报告与 meta.json ==========
    def _save_report(self, aborted: bool = False):
        """
        将本次心算实验写入 txt 报告。

        每一行格式：
            loop_start_time,loop_end_time,mental_calc,rec_str,acc

        其中：
          - loop_start_time / loop_end_time 为该 loop 的开始/结束时间（秒），
            使用的是由 triggers.csv 回填的 EEG 时间轴；
          - rec_str 形如：
              1+2=3TT|4-1=1FT|5+6=10FN ...
            其中：
              第一个 T/F = 题目结果是否正确（ground truth）
              第二个 T/F/N = 被试判断正确/错误/未作答
          - acc 为该轮正确率。
        """
        # 确定被试名称
        name = (
            self.current_user_name
            or self.name
            or self.name_input.text().strip()
            or "unknown"
        )
        mode = "split" if self.separate_phases else "normal"
        flag = "ABORT" if aborted else "DONE"

        # 优先使用本次 run 的目录：data/ma/<name>/<timestamp>
        base_dir = self.run_dir or self.user_dir or self.ma_root
        os.makedirs(base_dir, exist_ok=True)

        # 文件名里的时间戳：优先用 run_timestamp，兜底用当前时间
        ts_for_name = self.run_timestamp or datetime.now().strftime('%Y%m%d%H%M%S')

        fname = os.path.join(
            base_dir,
            f"MA_{name}_{ts_for_name}_"
            f"loops{self.loops}_trials{self.trials}_delay{self.delay}_{mode}_{flag}.txt"
        )

        try:
            with open(fname, 'w', encoding='utf-8') as f:
                for i in range(self.loops):
                    records = self.results_per_loop[i] if i < len(self.results_per_loop) else []

                    rec_str = '|'.join(
                        (
                            # 未作答：题目真值后加 N
                            f"{expr}={disp}{'T' if flag else 'F'}N"
                            if user_input is None
                            # 有作答：题目真值后加 T/F
                            else f"{expr}={disp}{'T' if flag else 'F'}{'T' if user_input == flag else 'F'}"
                        )
                        for expr, disp, flag, user_input in records
                    )

                    correct_count = sum(
                        1 for expr, disp, flag, user_input in records
                        if user_input is not None and (user_input == flag)
                    )
                    acc = (correct_count / len(records)) if records else 0.0

                    # 本轮开始/结束时间（由 triggers.csv 回填）
                    start_t = self.loop_eeg_start[i] if i < len(self.loop_eeg_start) else None
                    end_t = self.loop_eeg_end[i] if i < len(self.loop_eeg_end) else None

                    if isinstance(start_t, (int, float)):
                        start_val = float(start_t)
                    else:
                        start_val = float('nan')

                    if isinstance(end_t, (int, float)):
                        end_val = float(end_t)
                    else:
                        end_val = float('nan')

                    f.write(
                        f"{start_val:.6f},{end_val:.6f},"
                        f"mental_calc,{rec_str},{acc:.2f}\n"
                    )
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"写入心算日志失败：{e}")

    def _save_meta_json(self, aborted: bool = False):
        """
        额外保存一份 meta.json，结构大致为：

        {
          "subject_name": "...",
          "aborted": false,
          "timing": {...},
          "trigger_code_labels": {...},
          "loops": [
            {
              "loop_index": 1,
              "loop_start_time": ...,
              "loop_end_time": ...,
              "accuracy": ...,
              "trials": [
                {
                  "expr": "1 + 2",
                  "display_value": 3,
                  "ground_truth": true,
                  "user_response": true,
                  "correct": true
                },
                ...
              ]
            },
            ...
          ]
        }
        """
        base_dir = self.run_dir or self.user_dir or self.ma_root
        os.makedirs(base_dir, exist_ok=True)

        name = (
            self.current_user_name
            or self.name
            or self.name_input.text().strip()
            or "unknown"
        )

        timing = {
            "initial_countdown": int(self.initial_countdown),
            "delay_per_phase": float(self.delay),
            "rest_duration": int(self.rest_duration),
            "separate_phases": bool(self.separate_phases),
            "loops": int(self.loops),
            "trials_per_loop": int(self.trials),
        }

        loops_json: list[dict] = []
        for i in range(self.loops):
            records = self.results_per_loop[i] if i < len(self.results_per_loop) else []

            start_t = self.loop_eeg_start[i] if i < len(self.loop_eeg_start) else None
            end_t = self.loop_eeg_end[i] if i < len(self.loop_eeg_end) else None

            if isinstance(start_t, (int, float)):
                start_val = float(start_t)
            else:
                start_val = None

            if isinstance(end_t, (int, float)):
                end_val = float(end_t)
            else:
                end_val = None

            correct_count = sum(
                1 for expr, disp, flag, user_input in records
                if user_input is not None and (user_input == flag)
            )
            acc = (correct_count / len(records)) if records else 0.0

            trials_json = []
            for expr, disp, flag, user_input in records:
                trials_json.append(
                    {
                        "expr": expr,
                        "display_value": disp,
                        "ground_truth": bool(flag),
                        "user_response": None if user_input is None else bool(user_input),
                        "correct": None if user_input is None else bool(user_input == flag),
                    }
                )

            loops_json.append(
                {
                    "loop_index": i + 1,
                    "loop_start_time": start_val,
                    "loop_end_time": end_val,
                    "accuracy": acc,
                    "trials": trials_json,
                }
            )

        meta = {
            "subject_name": name,
            "aborted": bool(aborted),
            "timing": timing,
            "trigger_code_labels": {str(k): v for k, v in self.trigger_code_labels.items()},
            "loops": loops_json,
        }

        path = os.path.join(base_dir, "meta.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"写入 meta.json 失败：{e}")

    # ========== UI 状态与全屏控制 ==========
    def _show_fullscreen_message(
        self,
        template: str,
        seconds: int,
        bg: str | None = None,
        fg: str | None = None,
        plain: bool = False,
        next_callback=None,
    ):
        """
        在全屏界面中央显示一个带倒计时的提示信息（与 Page7 相同风格）。
        """
        # 隐藏主文字 / 按钮 / 反馈
        self.stage_label.hide()
        self.btn_container.hide()
        self.feedback_label.hide()

        # 设置样式
        if plain or bg is None:
            self.countdown_label.setStyleSheet("color: black;")
        else:
            fg_color = fg or "#000000"
            style = (
                f"color:{fg_color};"
                f"background-color:{bg};"
                "padding: 12px 28px; border-radius: 8px;"
            )
            self.countdown_label.setStyleSheet(style)

        self.countdown_label.show()
        self._countdown_value = int(seconds)
        self._countdown_template = template
        self.countdown_label.setText(template.format(n=self._countdown_value))

        if self._countdown_updater is not None:
            try:
                self._countdown_updater.stop()
                self._countdown_updater.deleteLater()
            except Exception:
                pass

        self._countdown_updater = QtCore.QTimer(self)
        self._countdown_updater.timeout.connect(lambda: self._tick(next_callback))
        self._countdown_updater.start(1000)

    def _tick(self, next_callback):
        if not self.is_running:
            if self._countdown_updater is not None:
                self._countdown_updater.stop()
            self.countdown_label.hide()
            return

        self._countdown_value -= 1
        if self._countdown_value > 0:
            self.countdown_label.setText(
                self._countdown_template.format(n=self._countdown_value)
            )
        else:
            if self._countdown_updater is not None:
                self._countdown_updater.stop()
            self.countdown_label.hide()
            if callable(next_callback):
                next_callback()

    def _apply_bg(self, color: str | None):
        self._current_bg = color
        if color:
            self.stage_label.setStyleSheet(
                f"background-color:{color}; color:{self._current_fg};"
                "padding: 18px 36px; border-radius: 8px;"
            )
        else:
            self.stage_label.setStyleSheet(f"color:{self._current_fg};")

    def _apply_fg(self, color: str):
        self._current_fg = color
        if self._current_bg:
            self.stage_label.setStyleSheet(
                f"background-color:{self._current_bg}; color:{color};"
                "padding: 18px 36px; border-radius: 8px;"
            )
        else:
            self.stage_label.setStyleSheet(f"color:{color};")
        self.countdown_label.setStyleSheet(f"color:{color};")

    def _clear_styles(self):
        self._current_bg = None
        self._current_fg = "#000000"
        self.stage_label.setStyleSheet("")
        self.countdown_label.setStyleSheet("")

    def reset_ui(self):
        """
        复位到首页状态。
        """
        # 停止倒计时计时器
        if self._countdown_updater is not None:
            try:
                self._countdown_updater.stop()
                self._countdown_updater.deleteLater()
            except Exception:
                pass
            self._countdown_updater = None

        self._clear_styles()

        self.stage_label.hide()
        self.countdown_label.hide()
        self.btn_container.hide()
        self.feedback_label.hide()

        # 重置实验状态
        self.current_loop = 0
        self.current_index = 0
        self.sequence = []
        self.results_per_loop = []
        self.response_recorded = False
        self.input_enabled = False
        self.is_running = False

        self.eeg_exp_start = None
        self.eeg_exp_end = None
        self.loop_eeg_start = []
        self.loop_eeg_end = []

        self.current_user_name = None
        self.user_dir = None
        self.run_dir = None
        self.run_timestamp = None

        # 回到首页卡片
        self.center_card.show()
        self.name_input.setFocus()

        # 退出全屏
        self._exit_fullscreen()

    # ==================== 全屏相关（与 Page7 基本一致） ====================
    def _enter_fullscreen(self):
        if self.fullscreen_win is not None:
            return

        if self._is_macos:
            self.fullscreen_win = QtWidgets.QWidget()
            self.fullscreen_win.setWindowFlags(
                QtCore.Qt.WindowType.FramelessWindowHint | QtCore.Qt.WindowType.Window
            )
            self.fullscreen_win.setWindowState(QtCore.Qt.WindowState.WindowFullScreen)
        else:
            self.fullscreen_win = QtWidgets.QWidget()
            self.fullscreen_win.setWindowFlags(
                QtCore.Qt.WindowType.FramelessWindowHint | QtCore.Qt.WindowType.Window
            )

        layout = QVBoxLayout(self.fullscreen_win)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.screen_container.setParent(self.fullscreen_win)
        self.screen_container.show()
        layout.addWidget(self.screen_container)

        # 在全屏窗口上再绑定一次 ESC（防止焦点问题）
        self._fs_esc_shortcut = QShortcut(
            QKeySequence(QtCore.Qt.Key.Key_Escape),
            self.fullscreen_win
        )
        self._fs_esc_shortcut.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
        self._fs_esc_shortcut.activated.connect(self.abort_and_finalize)

        if self._is_macos:
            self.fullscreen_win.show()
        else:
            self.fullscreen_win.showFullScreen()
            self.fullscreen_win.raise_()
            self.fullscreen_win.activateWindow()

    def _exit_fullscreen(self):
        if self.fullscreen_win is None:
            return

        if self._fs_esc_shortcut is not None:
            try:
                self._fs_esc_shortcut.deleteLater()
            except Exception:
                pass
            self._fs_esc_shortcut = None

        self.screen_container.hide()
        self.screen_container.setParent(self)

        self.fullscreen_win.close()
        self.fullscreen_win = None

    def keyPressEvent(self, event):
        # 实际处理靠 QShortcut，这里保持默认
        super().keyPressEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = Page6Widget()
    w.show()
    sys.exit(app.exec())
