# page6.py

import sys
import random
from datetime import datetime
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QFormLayout, QLabel,
    QLineEdit, QSpinBox, QDoubleSpinBox, QPushButton, QMessageBox
)
from PyQt6.QtGui import QKeySequence, QShortcut

# 支持的运算符
OPERATIONS = ['+', '-']

class Page6Widget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("心算实验")

        # 默认参数
        self.name = ""
        self.loops = 6
        self.trials = 10
        self.delay = 4.0
        self.max_operand = 100
        self.initial_countdown = 10  # 实验开始前倒计时
        self.rest_duration = 10      # 循环间休息倒计时

        # 状态变量
        self.current_loop = 0
        self.current_index = 0
        self.sequence = []
        # 存储每题: (expr, disp, actual_flag, user_input_flag or None)
        self.results_per_loop = []
        self.response_recorded = False
        self.input_enabled = True  # 控制输入的可用性

        # 主布局
        layout = QVBoxLayout(self)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        # 操作提示标签
        self.instruction_label = QLabel(
            "请按左方向键表示此算式正确，\n"
            "按右方向键表示此算式错误。\n"
            "每题将在屏幕上显示如“1 + 1 = 2”的格式\n"
            "请在规定时间内完成判断。"
        )
        instr_font = self.instruction_label.font()
        instr_font.setPointSize(14)
        self.instruction_label.setFont(instr_font)
        self.instruction_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.instruction_label.setWordWrap(True)
        layout.addWidget(self.instruction_label)

        # 设置区
        settings = QWidget()
        settings.setMaximumWidth(400)
        form = QFormLayout(settings)
        form.setFormAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        self.name_input = QLineEdit()
        form.addRow("Name:", self.name_input)

        self.loops_spin = QSpinBox()
        self.loops_spin.setRange(1, 10)
        self.loops_spin.setValue(self.loops)
        form.addRow("Runs:", self.loops_spin)

        self.trials_spin = QSpinBox()
        self.trials_spin.setRange(1, 100)
        self.trials_spin.setValue(self.trials)
        form.addRow("Trials:", self.trials_spin)

        self.delay_spin = QDoubleSpinBox()
        self.delay_spin.setRange(0.1, 10.0)
        self.delay_spin.setSingleStep(0.1)
        self.delay_spin.setValue(self.delay)
        form.addRow("Delay (s):", self.delay_spin)

        self.operand_spin = QSpinBox()
        self.operand_spin.setRange(1, 100)
        self.operand_spin.setValue(self.max_operand)
        form.addRow("Max Operand:", self.operand_spin)

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
        self.task_label.hide()
        layout.addWidget(self.task_label)

        # 按钮：正确 / 错误
        btn_layout = QtWidgets.QHBoxLayout()
        self.btn_true = QPushButton("正确")
        self.btn_false = QPushButton("错误")
        for btn in (self.btn_true, self.btn_false):
            btn.setCheckable(True)
            btn.setFixedSize(100, 50)
            btn.hide()
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
        layout.addLayout(btn_layout)

        # 反馈标签
        self.feedback_label = QLabel("")
        font_fb = self.feedback_label.font()
        font_fb.setPointSize(20)
        self.feedback_label.setFont(font_fb)
        self.feedback_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.feedback_label.setFixedHeight(40)
        self.feedback_label.setStyleSheet("border:none;")
        self.feedback_label.hide()
        layout.addWidget(self.feedback_label)

        # 键盘快捷键，设置为ApplicationShortcut以确保首次响应无延迟
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.shortcut_left = QShortcut(QKeySequence(QtCore.Qt.Key.Key_Left), self)
        self.shortcut_left.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
        self.shortcut_left.activated.connect(lambda: self.record_response(True))
        self.shortcut_right = QShortcut(QKeySequence(QtCore.Qt.Key.Key_Right), self)
        self.shortcut_right.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
        self.shortcut_right.activated.connect(lambda: self.record_response(False))

    def start_experiment(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "错误", "请输入姓名！")
            return
        self.name = name
        self.loops = self.loops_spin.value()
        self.trials = self.trials_spin.value()
        self.delay = self.delay_spin.value()
        self.max_operand = self.operand_spin.value()

        # 隐藏提示标签
        self.instruction_label.hide()

        self.current_loop = 1
        self.results_per_loop = [[] for _ in range(self.loops)]

        self.name_input.parent().hide()
        self.start_btn.hide()
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
        ops = OPERATIONS
        correct_flags = [True]*(self.trials//2) + [False]*(self.trials - self.trials//2)
        random.shuffle(correct_flags)
        self.sequence = []
        used = set()
        for flag in correct_flags:
            a = random.randint(1, self.max_operand)
            b = random.randint(1, self.max_operand)
            op = random.choice(ops)
            expr = f"{a} {op} {b}"
            true_val = eval(expr)
            disp = true_val if flag else true_val + random.choice([i for i in range(-3,4) if i])
            if (expr, disp) in used:
                continue
            used.add((expr, disp))
            self.sequence.append((expr, disp, flag))
            if len(self.sequence) >= self.trials:
                break

        self.current_index = 0
        self.btn_true.show(); self.btn_false.show(); self.feedback_label.show(); self.task_label.show()
        self.show_task()

    def show_task(self):
        # 禁用输入，防止误操作
        self.input_enabled = False
        self.btn_true.setEnabled(False)
        self.btn_false.setEnabled(False)
        # 0.5秒后启用输入
        QtCore.QTimer.singleShot(200, self.enable_inputs)

        # 重置状态
        self.feedback_label.clear()
        self.btn_true.setChecked(False)
        self.btn_false.setChecked(False)
        self.response_recorded = False

        if self.current_index >= len(self.sequence):
            self.end_loop()
            return

        expr, disp, _ = self.sequence[self.current_index]
        self.task_label.setText(f"{expr} = {disp}")
        self.task_label.show()
        self.activateWindow()
        self.setFocus()
        QtCore.QTimer.singleShot(int(self.delay * 1000), self.next_task)

    def enable_inputs(self):
        self.input_enabled = True
        self.btn_true.setEnabled(True)
        self.btn_false.setEnabled(True)

    def record_response(self, user_says_true: bool):
        if not self.input_enabled or self.response_recorded:
            return
        expr, disp, flag = self.sequence[self.current_index]
        # 用户输入记录
        self.results_per_loop[self.current_loop-1].append((expr, disp, flag, user_says_true))
        self.response_recorded = True
        # 更新按钮状态
        self.btn_true.setEnabled(False)
        self.btn_false.setEnabled(False)
        if user_says_true:
            self.btn_true.setChecked(True)
        else:
            self.btn_false.setChecked(True)
        # 显示反馈
        is_correct = (user_says_true == flag)
        mark = "✔" if is_correct else "❌"
        color = "green" if is_correct else "red"
        self.feedback_label.setText(mark)
        self.feedback_label.setStyleSheet(f"color:{color};border:none;")
        # QApplication.processEvents()

    def next_task(self):
        # 超时处理
        if not self.response_recorded:
            expr, disp, flag = self.sequence[self.current_index]
            self.results_per_loop[self.current_loop-1].append((expr, disp, flag, None))
        self.current_index += 1
        self.show_task()

    def end_loop(self):
        self.task_label.hide()
        self.btn_true.hide()
        self.btn_false.hide()
        self.feedback_label.hide()
        # 循环结束倒计时或结束实验
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
            self.save_report()
            self.reset_ui()

    def save_report(self):
        nowstr = datetime.now().strftime('%Y%m%d%H%M%S')
        fname = f"Calc_{self.name}_{nowstr}_loops{self.loops}_trials{self.trials}_delay{self.delay}.txt"
        with open(fname, 'w', encoding='utf-8') as f:
            for i in range(self.loops):
                start = self.initial_countdown + i*(self.trials*self.delay + self.rest_duration)
                end = start + self.trials*self.delay
                records = self.results_per_loop[i]
                rec_str = '|'.join(
                    # 超时时 only actual_flag
                    f"{expr}={disp}{'T' if flag else 'F'}" if user_input is None else 
                    f"{expr}={disp}{'T' if flag else 'F'}{'T' if user_input else 'F'}"
                    for expr, disp, flag, user_input in records
                )
                # 准确率：仅当 user_input equals flag 才计正确
                correct_count = sum(1 for expr, disp, flag, user_input in records if user_input == flag)
                acc = correct_count / len(records) if records else 0
                f.write(f"{start:.4f},{end:.4f},mental_calc,{rec_str},{acc:.2f}\n")

    def reset_ui(self):
        self.current_loop = 0; self.current_index = 0
        self.name_input.parent().show(); self.start_btn.show(); self.countdown_label.hide()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = Page6Widget()
    w.show()
    sys.exit(app.exec())
