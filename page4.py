import os
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
      - 从第 N 个字符开始，当当前字符与 N 个之前的字符相同时：
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

    时间记录逻辑（已改为片上时间）：
      - 不再使用 initial_countdown / loops / delay 计算理论时间；
      - 每个 loop 的开始与结束时间，直接从 Page2 的 get_last_hardware_timestamp()
        获取片上时间（硬件时间戳，单位秒）；
      - write_report() 中每一行的 start,end 即为该 loop 的开始/结束片上时间，
        可在 CSV 中找到完全相同的 Time 值，用于截取 EEG 片段。
      - EEG CSV 的写入从“通过校验后有效点击 Start Sequence”起一直持续到
        最后“实验结束，X秒”倒计时结束后才停止。
    """

    def __init__(self, parent=None):
        super(Page4Widget, self).__init__(parent)

        # ====== N-back 数据根目录：data/nback ======
        self.data_root = "data"
        self.nback_root = os.path.join(self.data_root, "nback")
        os.makedirs(self.nback_root, exist_ok=True)

        # 当前被试 & 本次实验 run 的目录
        self.current_user_name: str | None = None
        self.user_dir: str | None = None               # data/nback/<name>
        self.run_dir: str | None = None                # data/nback/<name>/<timestamp>
        self.run_timestamp: str | None = None          # YYYYMMDDHHMMSS

        # 默认参数
        self.loops = 6
        self.trials = 10
        self.delay = 2.0  # 每个刺激展示时长（秒）
        self.diff = 0
        self.n_back = 2  # 默认 2-back

        # 固定倒计时和休息时长（秒）（仅用于界面，不再参与时间计算）
        self.initial_countdown = 10.0
        self.rest_duration = 10.0

        # 序列及记录
        self.sequence = []  # 当前轮字符序列
        self.all_sequences = []  # 所有轮的字符序列
        # trial_data[loop_idx][trial_idx] = {"char", "target", "response"}
        self.trial_data = []
        self.current_loop = 0  # 当前是第几轮（1-based）
        self.current_index = 0  # 当前轮中的 trial 索引（0-based）

        # 与 EEG 采集页面（Page2）联动
        self.eeg_page = None
        # 整个实验的开始/结束片上时间（可选，当前未写入文件）
        self.hw_exp_start = None
        self.hw_exp_end = None
        # 每个 loop 的开始/结束片上时间（写入 txt）
        self.loop_hw_start = []
        self.loop_hw_end = []

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
                "确保已经开始接收EEG数据后，再启动 N-back 实验。"
            )
            return

        # ====== 构建目录结构：data/nback/<name>/<timestamp>/ ======
        self.current_user_name = name
        # data/nback/<name>
        self.user_dir = os.path.join(self.nback_root, self.current_user_name)
        os.makedirs(self.user_dir, exist_ok=True)

        # data/nback/<name>/<YYYYMMDDHHMMSS>
        self.run_timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        self.run_dir = os.path.join(self.user_dir, self.run_timestamp)
        os.makedirs(self.run_dir, exist_ok=True)
        # =======================================================

        # 2. 正式读取本页参数并初始化状态
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

        # 清空时间记录（片上时间）
        self.hw_exp_start = None
        self.hw_exp_end = None
        self.loop_hw_start = [None] * self.loops
        self.loop_hw_end = [None] * self.loops

        # ==== 在“有效点击 Start Sequence”之后立刻开始保存 EEG ====
        if hasattr(eeg_page, "start_saving"):
            try:
                # 把本次实验的 run_dir 传给 Page2，让 EEG CSV & markers.csv 写到同一目录
                eeg_page.start_saving(self.run_dir)
            except Exception:
                # Page2 内部会处理错误，这里不中断实验
                pass

        # 尝试记录整个实验的起始片上时间（若能取到的话）
        first_hw = self._get_hw_timestamp_from_eeg()
        if first_hw is not None:
            self.hw_exp_start = first_hw

        # 之后才隐藏设置区、开始倒计时
        self.settings_widget.hide()
        self.start_btn.hide()

        # 倒计时 / 前 N 个字符都不显示按钮
        self.response_btn.hide()
        self.response_btn.setEnabled(True)
        self.response_btn.setStyleSheet(self.response_default_style)

        self.setFocus()

        # 初始倒计时（仅界面提示，不参与时间计算）
        self.countdown_label.setText(f"{int(self.initial_countdown)}秒后将开始实验")
        self.countdown_label.show()
        QtCore.QTimer.singleShot(1000, lambda: self.update_countdown(self.initial_countdown - 1))

    def update_countdown(self, secs):
        if secs > 0:
            self.countdown_label.setText(f"{int(secs)}秒后将开始实验")
            QtCore.QTimer.singleShot(1000, lambda: self.update_countdown(secs - 1))
        else:
            # 倒计时结束，正式进入第一个 loop（不再在这里调用 start_saving）
            self.countdown_label.hide()
            self.current_loop = 1
            self.current_index = 0
            self.sequence = []
            self.response_btn.hide()
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

        loop_index = self.current_loop - 1

        # 当前轮结束
        if self.current_index >= self.trials:
            # 记录本轮结束时的片上时间
            self._record_loop_end_hw(loop_index)

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

        # 若是本轮的第一个 trial，记录本轮开始的片上时间
        if self.current_index == 0:
            self._record_loop_start_hw(loop_index)

        # 当前 trial
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

            # ==== 关键点：等“实验结束倒计时”结束之后，才停止保存 EEG ====
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
                if 0.4 <= ratio <= 0.45:
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

    # ========== 与 Page2（EEG 页面）的时间戳交互辅助函数 ==========

    def _get_hw_timestamp_from_eeg(self):
        """
        从 Page2 获取当前最新的片上时间戳（秒）。
        若未能获取则返回 None。
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
        在 show_loop() 中，当 current_index == 0 时调用。
        """
        hw = self._get_hw_timestamp_from_eeg()
        if hw is None:
            return
        if 0 <= loop_index < self.loops:
            self.loop_hw_start[loop_index] = hw
            # 如果整个实验的起始时间还没设置，就用第一次 loop start 做总起点（如果之前没成功取到的话）
            if self.hw_exp_start is None:
                self.hw_exp_start = hw

    def _record_loop_end_hw(self, loop_index: int):
        """
        记录第 loop_index 个 loop 的结束片上时间。
        在 show_loop() 中，当 current_index >= trials 时调用。
        """
        hw = self._get_hw_timestamp_from_eeg()
        if hw is None:
            return
        if 0 <= loop_index < self.loops:
            self.loop_hw_end[loop_index] = hw
            # 实验结束时间持续更新为最后一次 loop end
            self.hw_exp_end = hw

    # ========== 报告与复位 ==========

    def write_report(self):
        """
        将本次 N-back 实验写入 txt 报告。

        每一行格式：
            loop_start_hw,loop_end_hw,difficulty_label,n_back,sequence,target_flags,response_flags

        其中：
          - loop_start_hw / loop_end_hw 为该 loop 的开始/结束片上时间（秒）；
          - 后续可以用这两个时间在 CSV 的 Time 列中定位 EEG 片段。
        """
        name = self.current_user_name or self.name_input.text().strip()
        diff_label = self.diff_combo.currentText()

        # 优先使用本次 run 的目录：data/nback/<name>/<timestamp>
        base_dir = self.run_dir or self.user_dir or self.nback_root
        os.makedirs(base_dir, exist_ok=True)

        # 文件名里的时间戳：优先用 run_timestamp，兜底用当前时间
        ts_for_name = self.run_timestamp or datetime.datetime.now().strftime('%Y%m%d%H%M%S')

        filename = os.path.join(
            base_dir,
            f"N_Back_{name}_{ts_for_name}_"
            f"loops{self.loops}_trials{self.trials}_delay{self.delay}_"
            f"difficulty{diff_label.replace(' ', '')}_{self.n_back}back.txt"
        )

        try:
            with open(filename, 'w', encoding='utf-8') as f:
                for loop_idx in range(self.loops):
                    trials = self.trial_data[loop_idx]
                    seq_str = ' '.join(t["char"] for t in trials)
                    tgt_str = ' '.join('1' if t["target"] else '0' for t in trials)
                    resp_str = ' '.join('1' if t["response"] else '0' for t in trials)

                    start_hw = None
                    end_hw = None
                    if 0 <= loop_idx < len(self.loop_hw_start):
                        start_hw = self.loop_hw_start[loop_idx]
                    if 0 <= loop_idx < len(self.loop_hw_end):
                        end_hw = self.loop_hw_end[loop_idx]

                    # 若未成功获取到时间戳，用 NaN 占位，避免格式化报错
                    start_val = start_hw if isinstance(start_hw, (int, float)) else float('nan')
                    end_val = end_hw if isinstance(end_hw, (int, float)) else float('nan')

                    f.write(
                        f"{start_val:.6f},{end_val:.6f},"
                        f"{diff_label},{self.n_back},"
                        f"{seq_str},{tgt_str},{resp_str}\n"
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

        self.sequence = []
        self.all_sequences.clear()
        self.trial_data.clear()
        self.current_loop = 0
        self.current_index = 0

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

        self.name_input.setFocus()


if __name__ == '__main__':
    import sys

    app = QtWidgets.QApplication(sys.argv)
    w = Page4Widget()
    w.show()
    sys.exit(app.exec())
