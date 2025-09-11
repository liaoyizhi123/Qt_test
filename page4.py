import random
import string
import datetime
from PyQt6 import QtCore, QtWidgets
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QFormLayout, QLabel, QSpinBox, QDoubleSpinBox, QPushButton, QComboBox, QLineEdit, QMessageBox


class Page4Widget(QWidget):
    """
    页面4：根据设置的循环次数（Loops）、试次数（Trials）、间隔（Delay）和难度等级
    连续展示字符。难度一：仅数字；难度二：数字+字母。
    确保相邻字符不重复。
    过程：
      1. 验证用户姓名输入
      2. 10秒倒计时
      3. 循环展示指定Trials字符，并在每轮结束后休息10秒
      4. 最后一轮完成后写报告并重置界面
    报告中的时间根据参数手动计算，无需定时器记录。
    第四列记录本轮的字符序列，用空格分隔。
    """

    def __init__(self, parent=None):
        super(Page4Widget, self).__init__(parent)
        # 默认参数
        self.loops = 2
        self.trials = 6
        self.delay = 2.0  # 每个刺激展示时长（秒）
        self.diff = 0
        # 固定倒计时和休息时长（秒）
        self.initial_countdown = 10.0
        self.rest_duration = 10.0
        # 序列及记录
        self.sequence = []
        self.all_sequences = []  # 存储每轮的字符序列
        self.current_loop = 0
        self.current_index = 0

        # 主布局
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        # 操作提示标签
        self.instruction_label = QLabel(
            "2 Back，请在第三个字符出现时，读出往前第2个字符的内容。"
        )
        instr_font = self.instruction_label.font()
        instr_font.setPointSize(14)
        self.instruction_label.setFont(instr_font)
        self.instruction_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.instruction_label.setWordWrap(True)
        self.main_layout.addWidget(self.instruction_label)

        # 设置区：姓名、Loops、Trials、Delay、Difficulty
        settings = QWidget()
        settings.setMaximumWidth(400)
        form = QFormLayout(settings)
        form.setFormAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        self.name_input = QLineEdit()
        self.name_input.setMaximumWidth(200)
        form.addRow("Name:", self.name_input)

        self.loops_spin = QSpinBox()
        self.loops_spin.setRange(1, 10)
        self.loops_spin.setValue(self.loops)
        form.addRow("Loops:", self.loops_spin)

        self.trials_spin = QSpinBox()
        self.trials_spin.setRange(1, 100)
        self.trials_spin.setValue(self.trials)
        form.addRow("Trials:", self.trials_spin)

        self.delay_spin = QDoubleSpinBox()
        self.delay_spin.setRange(0.1, 10.0)
        self.delay_spin.setSingleStep(0.1)
        self.delay_spin.setValue(self.delay)
        form.addRow("Delay (s):", self.delay_spin)

        self.diff_combo = QComboBox()
        self.diff_combo.addItem("Digits Only")
        self.diff_combo.addItem("Digits + Letters")
        form.addRow("Difficulty:", self.diff_combo)

        self.start_btn = QPushButton("Start Sequence")
        self.start_btn.clicked.connect(self.start_sequence)

        self.main_layout.addWidget(settings)
        self.main_layout.addWidget(self.start_btn, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        # 倒计时标签
        self.countdown_label = QLabel("")
        font_cd = self.countdown_label.font()
        font_cd.setPointSize(48)
        self.countdown_label.setFont(font_cd)
        self.countdown_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.countdown_label.hide()
        self.main_layout.addWidget(self.countdown_label)

        # 字符展示标签
        self.char_label = QLabel("")
        font_ch = self.char_label.font()
        font_ch.setPointSize(72)
        self.char_label.setFont(font_ch)
        self.char_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.char_label.hide()
        self.main_layout.addWidget(self.char_label)

    def start_sequence(self):
        # 验证姓名输入
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "错误", "请输入姓名！")
            return
        # 读取设置
        self.loops = self.loops_spin.value()
        self.trials = self.trials_spin.value()
        self.delay = self.delay_spin.value()
        self.diff = self.diff_combo.currentIndex()
        # 隐藏设置区
        settings_widget = self.loops_spin.parent()
        settings_widget.hide()
        self.start_btn.hide()
        # 初始倒计时
        self.countdown_label.setText(f"{int(self.initial_countdown)}秒后将开始实验")
        self.countdown_label.show()
        QtCore.QTimer.singleShot(1000, lambda: self.update_countdown(self.initial_countdown - 1))

    def update_countdown(self, secs):
        if secs > 0:
            self.countdown_label.setText(f"{int(secs)}秒后将开始实验")
            QtCore.QTimer.singleShot(1000, lambda: self.update_countdown(secs - 1))
        else:
            self.countdown_label.hide()
            # 初始化循环
            self.current_loop = 1
            self.current_index = 0
            self.all_sequences.clear()
            self.sequence = []
            self.show_loop()

    def show_loop(self):
        # 开始或继续某一轮
        if not self.sequence:
            self.generate_sequence()
            # 记录本轮序列
            self.all_sequences.append(self.sequence.copy())
        if self.current_index >= self.trials:
            # 一轮结束
            if self.current_loop < self.loops:
                self.current_loop += 1
                self.char_label.hide()
                # 中间休息倒计时
                self.countdown_label.setText(f"请休息，{int(self.rest_duration)}秒后将开始新的实验")
                self.countdown_label.show()
                QtCore.QTimer.singleShot(1000, lambda: self.do_rest(self.rest_duration - 1))
            else:
                self.char_label.hide()
                # 最终休息倒计时，结束后写报告
                self.countdown_label.setText(f"实验结束，{int(self.rest_duration)}秒")
                self.countdown_label.show()
                QtCore.QTimer.singleShot(1000, lambda: self.do_rest_end(self.rest_duration - 1))
            return
        # 正常展示字符
        ch = self.sequence[self.current_index]
        self.char_label.setText(ch)
        self.char_label.show()
        QtCore.QTimer.singleShot(int(self.delay * 1000), self.next_char)

    def generate_sequence(self):
        pool = string.digits if self.diff == 0 else string.digits + string.ascii_uppercase
        prev = None
        self.sequence = []
        for _ in range(self.trials):
            ch = random.choice(pool)
            while ch == prev:
                ch = random.choice(pool)
            self.sequence.append(ch)
            prev = ch
        self.current_index = 0

    def next_char(self):
        self.current_index += 1
        self.show_loop()

    def do_rest(self, secs):
        if secs > 0:
            self.countdown_label.setText(f"请休息，{int(secs)}秒后将开始新的实验")
            QtCore.QTimer.singleShot(1000, lambda: self.do_rest(secs - 1))
        else:
            self.countdown_label.hide()
            self.current_index = 0
            self.sequence = []
            self.show_loop()

    def do_rest_end(self, secs):
        if secs > 0:
            self.countdown_label.setText(f"实验结束，{int(secs)}秒")
            QtCore.QTimer.singleShot(1000, lambda: self.do_rest_end(secs - 1))
        else:
            self.countdown_label.hide()
            self.write_report()
            self.reset_ui()

    def write_report(self):
        # 手动计算并写入报告
        name = self.name_input.text().strip()
        now_str = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
        diff_label = self.diff_combo.currentText()
        filename = f"N_Back_{name}_{now_str}_loops{self.loops}_trials{self.trials}_delay{self.delay}_difficulty{diff_label.replace(' ', '')}.txt"
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                for i in range(self.loops):
                    start = self.initial_countdown + i * (self.trials * self.delay + self.rest_duration)
                    end = start + self.trials * self.delay
                    seq_str = ' '.join(self.all_sequences[i])
                    f.write(f"{start:.4f},{end:.4f},{diff_label},{seq_str}\n")
        except Exception as e:
            print("写入报告失败：", e)

    def reset_ui(self):
        self.char_label.hide()
        self.countdown_label.hide()
        self.start_btn.show()
        settings_widget = self.loops_spin.parent()
        settings_widget.show()
        self.name_input.clear()


if __name__ == '__main__':
    import sys

    app = QtWidgets.QApplication(sys.argv)
    w = Page4Widget()
    w.show()
    sys.exit(app.exec())
