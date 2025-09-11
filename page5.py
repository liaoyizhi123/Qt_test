# page5.py

import sys
import random
from datetime import datetime
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QFormLayout, QLabel,
    QLineEdit, QSpinBox, QDoubleSpinBox, QPushButton, QMessageBox
)

# 中文颜色与对应英文色值
COLOR_OPTIONS = [
    ("红", "red"),
    ("黄", "yellow"),
    ("蓝", "blue"),
    ("绿", "green"),
    ("黑", "black"),
    ("白", "white"),
]

class Page5Widget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Stroop 实验")

        # 默认参数
        self.name = ""
        self.loops = 2
        self.trials = 5
        self.delay = 2.0
        self.colors_count = 6
        self.initial_countdown = 10
        self.rest_duration = 10
        # 实验状态
        self.current_loop = 0
        self.current_index = 0
        self.sequence = []
        self.results_per_loop = []

        # 主布局
        layout = QVBoxLayout(self)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        # 操作提示标签
        self.instruction_label = QLabel(
            "按方向键左键表示【字意】与【颜色】一致，"
            "右键表示不一致。"
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
        form.addRow("Loops:", self.loops_spin)

        self.trials_spin = QSpinBox()
        self.trials_spin.setRange(5, 100)
        self.trials_spin.setValue(self.trials)
        form.addRow("Trials:", self.trials_spin)

        self.delay_spin = QDoubleSpinBox()
        self.delay_spin.setRange(0.1, 10.0)
        self.delay_spin.setSingleStep(0.1)
        self.delay_spin.setValue(self.delay)
        form.addRow("Delay (s):", self.delay_spin)

        self.colors_spin = QSpinBox()
        self.colors_spin.setRange(2, len(COLOR_OPTIONS))
        self.colors_spin.setValue(self.colors_count)
        form.addRow("Colors (max 6):", self.colors_spin)

        self.start_btn = QPushButton("Start Stroop")
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

        # 刺激标签
        self.stim_label = QLabel("")
        font_st = self.stim_label.font()
        font_st.setPointSize(72)
        self.stim_label.setFont(font_st)
        self.stim_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.stim_label.setStyleSheet("background-color: lightgray;")
        self.stim_label.hide()
        layout.addWidget(self.stim_label)

        # 左右按钮
        btn_layout = QtWidgets.QHBoxLayout()
        self.btn_left = QPushButton("←")
        self.btn_right = QPushButton("→")
        for btn in (self.btn_left, self.btn_right):
            btn.setCheckable(True)
            btn.setFixedSize(100, 50)
            btn.hide()
        style = (
            "QPushButton{background-color:#4caf50;color:white;font-size:18px;}"
            "QPushButton:checked{background-color:#388e3c;}"
            "QPushButton:disabled{background-color:gray;}"
            "QPushButton:disabled:checked{background-color:#388e3c;}"
        )
        self.btn_left.setStyleSheet(style)
        self.btn_right.setStyleSheet(style)
        self.btn_left.clicked.connect(lambda: self.record_response(True))
        self.btn_right.clicked.connect(lambda: self.record_response(False))
        btn_layout.addWidget(self.btn_left)
        btn_layout.addWidget(self.btn_right)
        layout.addLayout(btn_layout)

        # 提示标签 (固定高度)
        self.hint_label = QLabel("")
        font_hint = self.hint_label.font()
        font_hint.setPointSize(16)
        self.hint_label.setFont(font_hint)
        self.hint_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.hint_label.setStyleSheet("border:none;")
        self.hint_label.setFixedHeight(40)
        self.hint_label.hide()
        layout.addWidget(self.hint_label)

        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)

    def start_experiment(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "错误", "请输入姓名！")
            return
        self.name = name
        self.loops = self.loops_spin.value()
        self.trials = self.trials_spin.value()
        self.delay = self.delay_spin.value()
        self.colors_count = self.colors_spin.value()

        # 初始化
        self.current_loop = 1
        self.results_per_loop = [[] for _ in range(self.loops)]

        # 进入初始倒计时
        self.name_input.parent().hide()
        self.start_btn.hide()
        self.countdown_secs = self.initial_countdown
        self.countdown_label.setText(f"{self.countdown_secs}秒后将开始实验")
        self.countdown_label.show()
        QtCore.QTimer.singleShot(1000, self.update_initial_countdown)

    def update_initial_countdown(self):
        self.countdown_secs -= 1
        if self.countdown_secs > 0:
            self.countdown_label.setText(f"{self.countdown_secs}秒后将开始实验")
            QtCore.QTimer.singleShot(1000, self.update_initial_countdown)
        else:
            self.countdown_label.hide()
            self.start_loop()

    def start_loop(self):
        # 序列生成...
        opts = COLOR_OPTIONS[:self.colors_count]
        mapping = {w: c for w, c in opts}
        words = list(mapping.keys())
        colors = list(mapping.values())
        full = self.trials // len(colors)
        rem = self.trials % len(colors)
        clist = colors * full + random.sample(colors, rem)
        while any(clist[i] == clist[i+1] for i in range(len(clist)-1)):
            random.shuffle(clist)
        half = self.trials // 2
        congruent_flags = [True]*half + [False]*(self.trials-half)
        random.shuffle(congruent_flags)
        self.sequence = []
        prev_word = None
        inv = {v: k for k, v in mapping.items()}
        for col, cong in zip(clist, congruent_flags):
            if cong:
                w = inv[col]
            else:
                cands = [x for x in words if x != inv[col] and x != prev_word]
                w = random.choice(cands)
            self.sequence.append((w, col))
            prev_word = w
        self.current_index = 0
        self.btn_left.show(); self.btn_right.show(); self.hint_label.show(); self.stim_label.show()
        self.show_stimulus()

    def show_stimulus(self):
        self.hint_label.clear()
        self.btn_left.setChecked(False); self.btn_left.setEnabled(True)
        self.btn_right.setChecked(False); self.btn_right.setEnabled(True)
        if self.current_index >= len(self.sequence):
            self.end_loop()
            return
        w, c = self.sequence[self.current_index]
        self.stim_label.setText(w)
        self.stim_label.setStyleSheet(f"background-color:lightgray;color:{c};")
        self.stim_label.show(); self.activateWindow(); self.setFocus()
        QtCore.QTimer.singleShot(int(self.delay*1000), self.next_stimulus)

    def record_response(self, user_cong: bool):
        w, c = self.sequence[self.current_index]
        correct = ((w=="红" and c=="red") or (w=="黄" and c=="yellow") or
                   (w=="蓝" and c=="blue") or (w=="绿" and c=="green") or
                   (w=="黑" and c=="black") or (w=="白" and c=="white"))
        self.results_per_loop[self.current_loop-1].append(user_cong==correct)
        # 更新按钮样式
        self.btn_left.setEnabled(False); self.btn_right.setEnabled(False)
        if user_cong: self.btn_left.setChecked(True)
        else:         self.btn_right.setChecked(True)
        # 显示提示并强制刷新
        mark = "✔" if user_cong==correct else "❌"
        color = "green" if user_cong==correct else "red"
        self.hint_label.setText(mark)
        self.hint_label.setStyleSheet(f"color:{color};border:none;")
        QApplication.processEvents()

    def next_stimulus(self):
        self.current_index += 1
        self.show_stimulus()

    def end_loop(self):
        self.stim_label.hide(); self.btn_left.hide(); self.btn_right.hide(); self.hint_label.hide()
        # 最后一轮结束倒计时
        if self.current_loop == self.loops:
            self.countdown_secs = self.initial_countdown
            self.countdown_label.setText(f"实验将于{self.countdown_secs}秒后结束")
            self.countdown_label.show()
            QtCore.QTimer.singleShot(1000, self.update_end_countdown)
        else:
            self.countdown_secs = self.rest_duration
            self.countdown_label.setText(f"{self.countdown_secs}秒后将开始下一次实验")
            self.countdown_label.show()
            QtCore.QTimer.singleShot(1000, self.update_rest_countdown)

    def update_rest_countdown(self):
        self.countdown_secs -= 1
        if self.countdown_secs > 0:
            self.countdown_label.setText(f"{self.countdown_secs}秒后将开始下一次实验")
            QtCore.QTimer.singleShot(1000, self.update_rest_countdown)
        else:
            self.countdown_label.hide()
            self.current_loop += 1
            self.start_loop()

    def update_end_countdown(self):
        self.countdown_secs -= 1
        if self.countdown_secs > 0:
            self.countdown_label.setText(f"实验将于{self.countdown_secs}秒后结束")
            QtCore.QTimer.singleShot(1000, self.update_end_countdown)
        else:
            self.countdown_label.hide()
            self.save_report()
            self.reset_ui()

    def save_report(self):
        nowstr = datetime.now().strftime('%Y%m%d%H%M%S')
        fname = f"Stroop_{self.name}_{nowstr}_loops{self.loops}_trials{self.trials}_delay{self.delay}.txt"
        with open(fname, 'w', encoding='utf-8') as f:
            for i in range(self.loops):
                start = self.initial_countdown + i*(self.trials*self.delay + self.rest_duration)
                end = start + self.trials*self.delay
                acc = sum(self.results_per_loop[i]) / self.trials
                f.write(f"{start:.4f},{end:.4f},stroop,{acc:.2f}\n")

    def reset_ui(self):
        self.current_loop = 0; self.current_index = 0
        self.name_input.parent().show(); self.start_btn.show()

    def keyPressEvent(self, event):
        if event.key() in (QtCore.Qt.Key.Key_Left, QtCore.Qt.Key.Key_Right) and self.btn_left.isVisible():
            if event.key()==QtCore.Qt.Key.Key_Left and self.btn_left.isEnabled(): self.record_response(True)
            if event.key()==QtCore.Qt.Key.Key_Right and self.btn_right.isEnabled(): self.record_response(False)
        super().keyPressEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = Page5Widget()
    w.show()
    sys.exit(app.exec())
