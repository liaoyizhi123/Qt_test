import random
import string
import datetime
import math
from PyQt6 import QtCore, QtWidgets
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QFormLayout,
    QLabel,
    QSpinBox,
    QDoubleSpinBox,
    QPushButton,
    QComboBox,
    QLineEdit,
    QMessageBox,
    QGraphicsOpacityEffect,
)
from PyQt6.QtGui import QShortcut, QKeySequence


class Page4Widget(QWidget):
    """
    页面4：N-back任务（支持1-back、2-back、3-back）

    根据设置的循环次数（Loops）、试次数（Trials）、间隔（Delay）和难度等级
    连续展示字符。难度一：仅数字；难度二：数字+字母。

    规则：
      - 选择 N-back（1/2/3）。
      - 从第 N 个字符开始，当当前字符与 N 个之前的字符相同：
          => target trial。
      - 被试若认为是 match：
          => 按 “匹配 / Match” 按钮 或 键盘 Left。
      - 按下后按钮置灰禁用，本 trial 不允许重复响应。
      - 不按则视为 non-match。

    生成序列要求：
      - 对非 target trial，避免相邻重复。
      - 对 1-back：target trial 为重复是合理的，允许。
      - 在可成为 target 的位置中（i >= N）：
          target 比例控制在 40%~60%（当有效位置数>=3时）。
    """

    def __init__(self, parent=None):
        super(Page4Widget, self).__init__(parent)

        # 默认参数
        self.loops = 6
        self.trials = 10
        self.delay = 2.0  # 每个刺激展示时长（秒）
        self.diff = 0
        self.n_back = 2  # 默认 2-back

        # 固定倒计时和休息时长（秒）
        self.initial_countdown = 10.0
        self.rest_duration = 10.0

        # 序列及记录
        self.sequence = []  # 当前轮字符序列
        self.all_sequences = []  # 所有轮的字符序列
        # trial_data[loop_idx][trial_idx] = {"char", "target", "response"}
        self.trial_data = []
        self.current_loop = 0  # 当前是第几轮（1-based）
        self.current_index = 0  # 当前轮中的 trial 索引（0-based）

        # 允许接收键盘事件
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)

        # ================== UI ==================
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        # 提示
        self.instruction_label = QLabel(
            "N-back 任务：\n"
            "当当前字符与 N 个之前的字符相同时，请按“匹配”键（或方向键左键）。\n"
            "不按则表示认为不匹配。"
        )
        instr_font = self.instruction_label.font()
        instr_font.setPointSize(14)
        self.instruction_label.setFont(instr_font)
        self.instruction_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.instruction_label.setWordWrap(True)
        self.main_layout.addWidget(self.instruction_label)

        # 设置区
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

        self.diff_combo = QComboBox()
        self.diff_combo.addItem("Digits Only")
        self.diff_combo.addItem("Digits + Letters")
        self.diff_combo.setCurrentIndex(1)
        form.addRow("Difficulty:", self.diff_combo)

        # N-back 级别选择
        self.nback_combo = QComboBox()
        self.nback_combo.addItems(["1-back", "2-back", "3-back"])
        self.nback_combo.setCurrentIndex(1)  # 默认 2-back
        form.addRow("N-back Level:", self.nback_combo)

        self.settings_widget = settings
        self.main_layout.addWidget(settings)

        # Start 按钮
        self.start_btn = QPushButton("Start Sequence")
        self.start_btn.clicked.connect(self.start_sequence)
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
        self.char_label.setStyleSheet("border: 0px;")  # 去掉边框
        self.char_label.hide()
        self.main_layout.addWidget(self.char_label)

        # 为字符添加淡入效果
        self.char_opacity_effect = QGraphicsOpacityEffect(self.char_label)
        self.char_label.setGraphicsEffect(self.char_opacity_effect)
        self.char_fade_anim = QtCore.QPropertyAnimation(self.char_opacity_effect, b"opacity", self)
        self.char_fade_anim.setDuration(200)  # 淡入时长，可微调
        self.char_fade_anim.setStartValue(0.0)
        self.char_fade_anim.setEndValue(1.0)

        # 按钮容器：固定高度，占位用，防止布局跳动
        self.response_container = QWidget()
        rc_layout = QVBoxLayout(self.response_container)
        rc_layout.setContentsMargins(0, 0, 0, 0)
        rc_layout.setSpacing(0)

        # 响应按钮：按下表示“匹配”
        self.response_btn = QPushButton("匹配 / Match")
        self.response_btn.clicked.connect(self.on_response)
        self.response_btn.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        rc_layout.addWidget(self.response_btn, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        # 初始隐藏按钮，但保留容器占位高度
        self.response_btn.hide()
        ph = self.response_btn.sizeHint().height() + 20
        self.response_container.setFixedHeight(ph)

        self.main_layout.addWidget(self.response_container, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        # 保存按钮默认样式，方便恢复
        self.response_default_style = self.response_btn.styleSheet()

        # 键盘快捷键：Left 等价于点击“匹配”
        self.match_shortcut = QShortcut(QKeySequence(QtCore.Qt.Key.Key_Left), self)
        self.match_shortcut.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.match_shortcut.activated.connect(self.on_response)

    # ========== 实验流程控制 ==========

    def start_sequence(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "错误", "请输入姓名！")
            return

        self.loops = self.loops_spin.value()
        self.trials = self.trials_spin.value()
        self.delay = self.delay_spin.value()
        self.diff = self.diff_combo.currentIndex()
        self.n_back = self.nback_combo.currentIndex() + 1  # 1 / 2 / 3-back

        # 重置状态
        self.all_sequences.clear()
        self.trial_data.clear()
        self.current_loop = 0
        self.current_index = 0

        self.settings_widget.hide()
        self.start_btn.hide()

        # 倒计时 / 前 N 个字符都不显示按钮
        self.response_btn.hide()
        self.response_btn.setEnabled(True)
        self.response_btn.setStyleSheet(self.response_default_style)

        self.setFocus()

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
            self.current_loop = 1
            self.current_index = 0
            self.sequence = []
            self.show_loop()

    def show_char_with_animation(self, ch: str):
        """显示单个字符并做淡入动画。"""
        self.char_fade_anim.stop()
        self.char_opacity_effect.setOpacity(0.0)
        self.char_label.setText(ch)
        self.char_label.show()
        self.char_fade_anim.start()

    def show_loop(self):
        self.setFocus()

        # 若当前轮未生成序列，则生成
        if not self.sequence:
            self.generate_sequence()

        # 当前轮结束
        if self.current_index >= self.trials:
            self.response_btn.hide()
            if self.current_loop < self.loops:
                self.current_loop += 1
                self.char_label.hide()
                self.sequence = []
                self.current_index = 0
                self.countdown_label.setText(f"请休息，{int(self.rest_duration)}秒后将开始新的实验")
                self.countdown_label.show()
                QtCore.QTimer.singleShot(1000, lambda: self.do_rest(self.rest_duration - 1))
            else:
                self.char_label.hide()
                self.countdown_label.setText(f"实验结束，{int(self.rest_duration)}秒")
                self.countdown_label.show()
                QtCore.QTimer.singleShot(1000, lambda: self.do_rest_end(self.rest_duration - 1))
            return

        # 当前 trial
        loop_index = self.current_loop - 1
        trial = self.trial_data[loop_index][self.current_index]
        ch = trial["char"]

        # 带淡入动画的展示
        self.show_char_with_animation(ch)

        # 按钮逻辑
        if self.current_index >= self.n_back:
            # 从第 N 个开始，才需要响应按钮
            if trial["response"]:
                self.response_btn.show()
                self.response_btn.setEnabled(False)
                self.response_btn.setStyleSheet("background-color: gray;")
            else:
                self.response_btn.show()
                self.response_btn.setEnabled(True)
                self.response_btn.setStyleSheet(self.response_default_style)
        else:
            # 前 N 个 trial 不显示按钮
            self.response_btn.hide()
            self.response_btn.setEnabled(True)
            self.response_btn.setStyleSheet(self.response_default_style)

        # delay 后进入下一字符
        QtCore.QTimer.singleShot(int(self.delay * 1000), self.next_char)

    def next_char(self):
        self.current_index += 1
        self.show_loop()

    def do_rest(self, secs):
        if secs > 0:
            self.countdown_label.setText(f"请休息，{int(secs)}秒后将开始新的实验")
            QtCore.QTimer.singleShot(1000, lambda: self.do_rest(secs - 1))
        else:
            self.countdown_label.hide()
            self.sequence = []
            self.current_index = 0
            self.response_btn.hide()
            self.show_loop()

    def do_rest_end(self, secs):
        if secs > 0:
            self.countdown_label.setText(f"实验结束，{int(secs)}秒")
            QtCore.QTimer.singleShot(1000, lambda: self.do_rest_end(secs - 1))
        else:
            self.countdown_label.hide()
            self.response_btn.hide()
            self.write_report()
            self.reset_ui()

    # ========== 刺激与记录 ==========

    def generate_sequence(self):
        """
        生成当前轮字符序列。
        """
        pool = string.digits if self.diff == 0 else string.digits + string.ascii_uppercase

        max_attempts = 200
        best_seq = None
        best_flags = None

        for _ in range(max_attempts):
            seq = []
            flags = [False] * self.trials

            for i in range(self.trials):
                if i < self.n_back:
                    ch = random.choice(pool)
                    while i > 0 and ch == seq[i - 1]:
                        ch = random.choice(pool)
                    seq.append(ch)
                    flags[i] = False
                else:
                    want_target = random.random() < 0.5

                    if want_target:
                        ch = seq[i - self.n_back]
                        if self.n_back != 1 and i > 0 and ch == seq[i - 1]:
                            want_target = False

                    if not want_target:
                        while True:
                            ch = random.choice(pool)
                            if ch == seq[i - self.n_back]:
                                continue
                            if i > 0 and ch == seq[i - 1]:
                                continue
                            break

                    is_target = i >= self.n_back and ch == seq[i - self.n_back]
                    seq.append(ch)
                    flags[i] = is_target

            valid_positions = max(self.trials - self.n_back, 0)
            if valid_positions <= 0:
                best_seq, best_flags = seq, flags
                break

            target_count = sum(1 for i in range(self.n_back, self.trials) if flags[i])
            if valid_positions >= 3:
                ratio = target_count / valid_positions
                if 0.4 <= ratio <= 0.6:
                    best_seq, best_flags = seq, flags
                    break
            else:
                best_seq, best_flags = seq, flags
                break

        if best_seq is None:
            best_seq, best_flags = seq, flags

        self.sequence = best_seq
        self.all_sequences.append(self.sequence.copy())

        loop_trials = []
        for i, ch in enumerate(self.sequence):
            loop_trials.append({"char": ch, "target": bool(best_flags[i]), "response": False})
        self.trial_data.append(loop_trials)
        self.current_index = 0

    def on_response(self):
        """
        匹配响应：按钮或 Left 快捷键触发。
        """
        if self.current_loop < 1:
            return
        if self.current_index < self.n_back:
            return

        loop_index = self.current_loop - 1
        trial_index = self.current_index

        if not (0 <= loop_index < len(self.trial_data)):
            return
        if not (0 <= trial_index < len(self.trial_data[loop_index])):
            return

        trial = self.trial_data[loop_index][trial_index]
        if not trial["response"]:
            trial["response"] = True
            self.response_btn.setEnabled(False)
            self.response_btn.setStyleSheet("background-color: gray;")

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key.Key_Left:
            self.on_response()
        else:
            super().keyPressEvent(event)

    # ========== 报告与复位 ==========

    def write_report(self):
        name = self.name_input.text().strip()
        now_str = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
        diff_label = self.diff_combo.currentText()

        filename = (
            f"N_Back_{name}_{now_str}_"
            f"loops{self.loops}_trials{self.trials}_delay{self.delay}_"
            f"difficulty{diff_label.replace(' ', '')}_{self.n_back}back.txt"
        )

        try:
            with open(filename, 'w', encoding='utf-8') as f:

                for loop_idx in range(self.loops):
                    start = self.initial_countdown + loop_idx * (self.trials * self.delay + self.rest_duration)
                    end = start + self.trials * self.delay

                    trials = self.trial_data[loop_idx]
                    seq_str = ' '.join(t["char"] for t in trials)
                    tgt_str = ' '.join('1' if t["target"] else '0' for t in trials)
                    resp_str = ' '.join('1' if t["response"] else '0' for t in trials)

                    f.write(
                        f"{start:.4f},{end:.4f}," f"{diff_label},{self.n_back}," f"{seq_str},{tgt_str},{resp_str}\n"
                    )
        except Exception as e:
            print("写入报告失败：", e)

    def reset_ui(self):
        self.char_label.hide()
        self.countdown_label.hide()

        self.response_btn.hide()
        self.response_btn.setEnabled(True)
        self.response_btn.setStyleSheet(self.response_default_style)

        self.start_btn.show()
        self.settings_widget.show()

        self.name_input.clear()
        self.sequence = []
        self.all_sequences.clear()
        self.trial_data.clear()
        self.current_loop = 0
        self.current_index = 0

        self.name_input.setFocus()


if __name__ == '__main__':
    import sys

    app = QtWidgets.QApplication(sys.argv)
    w = Page4Widget()
    w.show()
    sys.exit(app.exec())
