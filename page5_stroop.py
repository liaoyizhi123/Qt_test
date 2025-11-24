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

# 中文颜色与对应英文色值
COLOR_OPTIONS = [
    ("红", "red"),
    ("黄", "yellow"),
    ("蓝", "blue"),
    ("绿", "green"),
    ("黑", "black"),
    ("白", "white"),
]

# 英文色值 -> 中文名（用于日志里把 'black' 转回 '黑'）
COLOR_NAME_MAP = {
    "red": "红",
    "yellow": "黄",
    "blue": "蓝",
    "green": "绿",
    "black": "黑",
    "white": "白",
}


class Page5Widget(QWidget):
    """
    Stroop 实验页面（Page5）

    时间记录逻辑：
      - 使用 Page2 提供的 get_last_eeg_time()，获取与 CSV 中 Time 列一致的
        “校准后的电脑时间轴”（秒）；
      - 每个 loop 的开始/结束时间，记录在 loop_eeg_start / loop_eeg_end；
      - save_report() 中每一行第 1、2 列就是该 loop 的开始/结束时间，便于在 CSV 中对齐切片。

    Stroop tag 规则：
      - 每个 trial 写入时的 tag 为两个字符：
          第一个字符：T / F
              T = 原题为一致（congruent）
              F = 原题为不一致（incongruent）
          第二个字符：T / F / N
              T = 被试判断正确
              F = 被试判断错误
              N = 被试未作答
      - 例如：TT / TF / TN / FT / FF / FN
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Stroop 实验")

        self.setMinimumSize(800, 600)

        # ====== Stroop 数据根目录：data/stroop ======
        self.data_root = "data"
        self.stroop_root = os.path.join(self.data_root, "stroop")
        os.makedirs(self.stroop_root, exist_ok=True)

        # 当前被试 & 本次实验 run 的目录
        self.current_user_name: str | None = None
        self.user_dir: str | None = None       # data/stroop/<name>
        self.run_dir: str | None = None        # data/stroop/<name>/<timestamp>
        self.run_timestamp: str | None = None  # YYYYMMDDHHMMSS

        # 默认参数
        self.name = ""
        self.loops = 6
        self.trials = 10
        self.delay = 2.0  # 展示期时长（秒）
        self.colors_count = 6
        self.initial_countdown = 10
        self.rest_duration = 10
        self.separate_phases = False  # 是否分离展示与作答
        self.response_window = 2.0    # 分离模式下作答窗口（秒）

        # 实验状态
        self.current_loop = 0
        self.current_index = 0
        self.sequence = []
        self.results_per_loop = []   # 每轮：布尔是否答对
        self.details_per_loop = []   # 每轮：[(word_cn, color_en, tag2), ...]  tag 是 "TT"/"FN" 等
        self.responded = False       # 本 trial 是否已作答

        # 与 EEG 采集页面（Page2）联动
        # 需要在主程序中设置：page5.eeg_page = page2
        self.eeg_page = None
        # 整个实验的开始/结束时间（与 CSV Time 使用同一“校准电脑时间”轴）
        self.eeg_exp_start = None
        self.eeg_exp_end = None
        # 每个 loop 的开始/结束时间（写入 txt）
        self.loop_eeg_start = []
        self.loop_eeg_end = []

        # ===== 外层布局：只负责把 main_container 居中 =====
        root_layout = QVBoxLayout(self)
        root_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        # 中间固定宽度容器：所有实验元素都放这里，宽度不变
        self.main_container = QWidget()
        self.main_container.setFixedWidth(600)
        layout = QVBoxLayout(self.main_container)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        root_layout.addWidget(self.main_container, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        # 操作提示标签
        self.instruction_label = QLabel("按方向键左键表示【字意】与【颜色】一致，右键表示不一致。")
        instr_font = self.instruction_label.font()
        instr_font.setPointSize(14)
        self.instruction_label.setFont(instr_font)
        self.instruction_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.instruction_label.setWordWrap(True)
        self.instruction_label.setMaximumWidth(400)
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
        self.trials_spin.setRange(5, 100)
        self.trials_spin.setValue(self.trials)
        form.addRow("Trials:", self.trials_spin)

        # delay：原始模式=总时长；分离模式=展示期时长
        self.delay_spin = QDoubleSpinBox()
        self.delay_spin.setRange(0.1, 10.0)
        self.delay_spin.setSingleStep(0.1)
        self.delay_spin.setValue(self.delay)
        form.addRow("展示期 Delay (s):", self.delay_spin)

        self.colors_spin = QSpinBox()
        self.colors_spin.setRange(2, len(COLOR_OPTIONS))
        self.colors_spin.setValue(self.colors_count)
        form.addRow("Colors (max 6):", self.colors_spin)

        # 是否分离展示与操作
        self.split_checkbox = QtWidgets.QCheckBox("是（先展示，后作答）")
        self.split_checkbox.setChecked(False)  # 默认“否”
        form.addRow("展示/操作分离:", self.split_checkbox)

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
        # 固定宽度让单字符居中更稳定（可按实际调整）
        self.stim_label.setFixedWidth(400)
        layout.addWidget(self.stim_label)

        # 按钮容器：固定高度 + 固定宽度，位置不变
        self.btn_container = QWidget()
        self.btn_container.setFixedHeight(80)
        self.btn_container.setFixedWidth(400)
        btn_layout = QVBoxLayout(self.btn_container)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        inner_row = QtWidgets.QHBoxLayout()
        inner_row.setContentsMargins(0, 0, 0, 0)
        inner_row.setSpacing(40)

        self.btn_left = QPushButton("← 一致")
        self.btn_right = QPushButton("→ 不一致")
        for btn in (self.btn_left, self.btn_right):
            btn.setCheckable(True)
            btn.setFixedSize(120, 50)

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

        inner_row.addWidget(self.btn_left)
        inner_row.addWidget(self.btn_right)
        btn_layout.addLayout(inner_row)

        self.btn_container.hide()  # 实验开始前不显示按钮区
        layout.addWidget(self.btn_container, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        # 提示标签 (固定高度 + 固定宽度)
        self.hint_label = QLabel("")
        font_hint = self.hint_label.font()
        font_hint.setPointSize(16)
        self.hint_label.setFont(font_hint)
        self.hint_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.hint_label.setStyleSheet("border:none;")
        self.hint_label.setFixedHeight(40)
        self.hint_label.setFixedWidth(400)
        self.hint_label.hide()
        layout.addWidget(self.hint_label)

        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)

    # ---------------- EEG 时间工具 ----------------

    def _get_eeg_time_from_page(self):
        """
        从 Page2 获取当前最新的 EEG 时间（秒），
        使用的是与 CSV Time 列一致的“校准后的电脑时间轴”。
        若未能获取则返回 None。
        """
        eeg_page = getattr(self, "eeg_page", None)
        if eeg_page is None:
            return None
        getter = getattr(eeg_page, "get_last_eeg_time", None)
        if getter is None:
            return None
        try:
            return getter()
        except Exception:
            return None

    def _record_loop_start_time(self, loop_index: int):
        """
        记录第 loop_index 个 loop 的开始时间（校准后的电脑时间）。
        在 show_stimulus() 中，当 current_index == 0 时调用。
        """
        t = self._get_eeg_time_from_page()
        if t is None:
            return
        if 0 <= loop_index < self.loops:
            self.loop_eeg_start[loop_index] = t
            # 若整体起始时间尚未记录，则用第一次 loop start 作为备选
            if self.eeg_exp_start is None:
                self.eeg_exp_start = t

    def _record_loop_end_time(self, loop_index: int):
        """
        记录第 loop_index 个 loop 的结束时间（校准后的电脑时间）。
        在 end_loop() 中调用。
        """
        t = self._get_eeg_time_from_page()
        if t is None:
            return
        if 0 <= loop_index < self.loops:
            self.loop_eeg_end[loop_index] = t
            self.eeg_exp_end = t

    # ---------------- Stroop 判定工具 ----------------

    def _is_congruent(self, w: str, c: str) -> bool:
        """
        判断当前刺激是否“字意与颜色一致”。
        w: 中文颜色字  e.g. "红"
        c: 显示颜色英文值 e.g. "red"
        """
        return (
            (w == "红" and c == "red") or
            (w == "黄" and c == "yellow") or
            (w == "蓝" and c == "blue") or
            (w == "绿" and c == "green") or
            (w == "黑" and c == "black") or
            (w == "白" and c == "white")
        )

    # ---------------- 核心流程 ----------------

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
                "确保已经开始接收EEG数据后，再启动 Stroop 实验。"
            )
            return

        # 2. 构建目录结构：data/stroop/<name>/<timestamp>/
        self.current_user_name = name
        self.user_dir = os.path.join(self.stroop_root, self.current_user_name)
        os.makedirs(self.user_dir, exist_ok=True)

        self.run_timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        self.run_dir = os.path.join(self.user_dir, self.run_timestamp)
        os.makedirs(self.run_dir, exist_ok=True)

        # 3. 读取参数 & 初始化状态
        self.name = name
        self.loops = self.loops_spin.value()
        self.trials = self.trials_spin.value()
        self.delay = self.delay_spin.value()
        self.colors_count = self.colors_spin.value()
        self.separate_phases = self.split_checkbox.isChecked()

        self.current_loop = 1
        self.results_per_loop = [[] for _ in range(self.loops)]
        self.details_per_loop = [[] for _ in range(self.loops)]

        # 初始化时间记录（统一使用“校准后的电脑时间”）
        self.eeg_exp_start = None
        self.eeg_exp_end = None
        self.loop_eeg_start = [None] * self.loops
        self.loop_eeg_end = [None] * self.loops

        # ==== 关键：在“有效点击 Start Stroop”后立刻开始保存 EEG CSV ====
        if hasattr(eeg_page, "start_saving"):
            try:
                # 把本次实验的 run_dir 传给 Page2，让 EEG CSV & markers.csv 写到同一目录
                eeg_page.start_saving(self.run_dir)
            except Exception:
                # Page2 内部会处理错误，这里不中断 Stroop 实验
                pass

        # 尝试记录实验整体起始时间（校准后的 EEG 时间轴）
        first_time = self._get_eeg_time_from_page()
        if first_time is not None:
            self.eeg_exp_start = first_time

        # 隐藏设置区
        self.name_input.parent().hide()
        self.start_btn.hide()

        # 初始倒计时（仅界面提示，不参与时间计算）
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
        # 生成序列：颜色均匀 + 相邻颜色不重复；一半 congruent 一半 incongruent
        opts = COLOR_OPTIONS[: self.colors_count]
        mapping = {w: c for w, c in opts}
        words = list(mapping.keys())
        colors = list(mapping.values())

        full = self.trials // len(colors)
        rem = self.trials % len(colors)
        clist = colors * full + random.sample(colors, rem)
        while any(clist[i] == clist[i + 1] for i in range(len(clist) - 1)):
            random.shuffle(clist)

        half = self.trials // 2
        congruent_flags = [True] * half + [False] * (self.trials - half)
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
        self.btn_container.show()   # 从本轮开始按钮区域位置固定
        self.hint_label.show()
        self.show_stimulus()

    def show_stimulus(self):
        if self.current_index >= len(self.sequence):
            self.end_loop()
            return

        # 若是本轮第一个 trial，记录本轮开始时间（校准后的 EEG 时间）
        if self.current_index == 0:
            self._record_loop_start_time(self.current_loop - 1)

        self.hint_label.clear()
        self.btn_left.setChecked(False)
        self.btn_right.setChecked(False)
        self.responded = False

        w, c = self.sequence[self.current_index]
        self.stim_label.setText(w)
        self.stim_label.setStyleSheet(f"background-color:lightgray;color:{c};")
        self.stim_label.show()
        self.activateWindow()
        self.setFocus()

        if self.separate_phases:
            # 展示期：仅刺激 & 提示，按钮隐藏，但按钮容器存在，宽高固定
            self.btn_left.hide()
            self.btn_right.hide()
            self.hint_label.setText("请注视刺激")
            self.hint_label.setStyleSheet("color:black;border:none;")
            QtCore.QTimer.singleShot(int(self.delay * 1000), self.start_response_phase)
        else:
            # 原始模式：展示+作答合一
            self.btn_left.show()
            self.btn_right.show()
            self.btn_left.setEnabled(True)
            self.btn_right.setEnabled(True)
            self.hint_label.setText("")
            self.hint_label.setStyleSheet("border:none;")
            QtCore.QTimer.singleShot(int(self.delay * 1000), self.next_stimulus)

    def start_response_phase(self):
        if self.current_index >= len(self.sequence):
            return

        # 展示结束，进入作答期：按钮出现
        self.btn_left.show()
        self.btn_right.show()
        self.btn_left.setEnabled(True)
        self.btn_right.setEnabled(True)
        self.hint_label.setText("现在判断：← 一致，→ 不一致")
        self.hint_label.setStyleSheet("color:black;border:none;")

        QtCore.QTimer.singleShot(int(self.response_window * 1000), self.finish_trial)

    def finish_trial(self):
        if self.current_index >= len(self.sequence):
            return

        # 分离模式下：作答期结束仍未响应，记为未作答
        if not self.responded:
            w, c = self.sequence[self.current_index]
            is_congruent = self._is_congruent(w, c)
            gt_char = 'T' if is_congruent else 'F'
            tag = gt_char + 'N'  # 未作答

            self.results_per_loop[self.current_loop - 1].append(False)
            self.details_per_loop[self.current_loop - 1].append((w, c, tag))

        self.current_index += 1
        self.show_stimulus()

    def record_response(self, user_cong: bool):
        """
        user_cong: True = 被试认为一致；False = 被试认为不一致
        """
        if self.responded or self.current_index >= len(self.sequence):
            return

        w, c = self.sequence[self.current_index]
        is_congruent = self._is_congruent(w, c)
        is_correct = (user_cong == is_congruent)

        # 正确率统计用
        self.results_per_loop[self.current_loop - 1].append(is_correct)

        # tag: 第一个字母是题目真值 T/F；第二个字母是被试表现 T/F
        gt_char = 'T' if is_congruent else 'F'
        resp_char = 'T' if is_correct else 'F'
        tag = gt_char + resp_char

        self.details_per_loop[self.current_loop - 1].append((w, c, tag))

        self.btn_left.setEnabled(False)
        self.btn_right.setEnabled(False)
        if user_cong:
            self.btn_left.setChecked(True)
        else:
            self.btn_right.setChecked(True)

        mark = "✔" if is_correct else "❌"
        color = "green" if is_correct else "red"
        self.hint_label.setText(mark)
        self.hint_label.setStyleSheet(f"color:{color};border:none;")
        QApplication.processEvents()

        self.responded = True

    def next_stimulus(self):
        # 原始模式：delay 结束切下一 trial，未作答也算一次
        if self.separate_phases:
            return

        if not self.responded and self.current_index < len(self.sequence):
            w, c = self.sequence[self.current_index]
            is_congruent = self._is_congruent(w, c)
            gt_char = 'T' if is_congruent else 'F'
            tag = gt_char + 'N'  # 未作答

            self.results_per_loop[self.current_loop - 1].append(False)
            self.details_per_loop[self.current_loop - 1].append((w, c, tag))

        self.current_index += 1
        self.show_stimulus()

    def end_loop(self):
        # 记录本轮结束时的时间（校准后的 EEG 时间）
        self._record_loop_end_time(self.current_loop - 1)

        self.stim_label.hide()
        self.btn_left.hide()
        self.btn_right.hide()
        self.btn_container.hide()
        self.hint_label.hide()

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
            self.countdown_label.show()
            QtCore.QTimer.singleShot(1000, self.update_end_countdown)
        else:
            self.countdown_label.hide()

            # ==== 实验整体结束：先停止 EEG 保存，再写 txt ====
            eeg_page = getattr(self, "eeg_page", None)
            if eeg_page is not None:
                last_time = self._get_eeg_time_from_page()
                if last_time is not None:
                    self.eeg_exp_end = last_time
                if hasattr(eeg_page, "stop_saving"):
                    try:
                        eeg_page.stop_saving()
                    except Exception:
                        pass

            self.save_report()
            self.reset_ui()

    # ========== 报告与复位 ==========

    def save_report(self):
        """
        将本次 Stroop 实验写入 txt 报告。

        每一行格式：
            loop_start_time,loop_end_time,stroop,accuracy,seq_str

        其中：
          - loop_start_time / loop_end_time 为该 loop 的开始/结束时间（秒），
            使用的是与 CSV Time 列一致的“校准后的电脑时间轴”；
          - accuracy 为该轮正确率；
          - seq_str 为该轮 trial 序列，形如：
              字‘红’颜色‘黄’TF|字‘蓝’颜色‘绿’TN|...
            其中 tag 为两个字符：
              第 1 个：T/F 表示题目是否一致
              第 2 个：T/F/N 表示被试是否判断正确/错误/未作答
        """
        # 确定被试名称
        name = (
            self.current_user_name
            or self.name
            or self.name_input.text().strip()
            or "unknown"
        )
        mode = "split" if self.separate_phases else "normal"

        # 优先使用本次 run 的目录：data/stroop/<name>/<timestamp>
        base_dir = self.run_dir or self.user_dir or self.stroop_root
        os.makedirs(base_dir, exist_ok=True)

        # 文件名里的时间戳：优先用 run_timestamp，兜底用当前时间
        ts_for_name = self.run_timestamp or datetime.now().strftime('%Y%m%d%H%M%S')

        fname = os.path.join(
            base_dir,
            f"Stroop_{name}_{ts_for_name}_"
            f"loops{self.loops}_trials{self.trials}_delay{self.delay}_{mode}.txt"
        )

        with open(fname, "w", encoding="utf-8") as f:
            for i in range(self.loops):
                # 计算该轮正确率
                if self.trials:
                    acc = sum(self.results_per_loop[i]) / self.trials
                else:
                    acc = 0.0

                # 序列明细
                seq_items = []
                for w, c, tag in self.details_per_loop[i]:
                    c_cn = COLOR_NAME_MAP.get(c, c)
                    seq_items.append(f"字‘{w}’颜色‘{c_cn}’{tag}")
                seq_str = "|".join(seq_items)

                # 该轮开始/结束时间（校准后的 EEG 时间）
                start_t = self.loop_eeg_start[i] if i < len(self.loop_eeg_start) else None
                end_t = self.loop_eeg_end[i] if i < len(self.loop_eeg_end) else None
                start_val = start_t if isinstance(start_t, (int, float)) else float('nan')
                end_val = end_t if isinstance(end_t, (int, float)) else float('nan')

                f.write(
                    f"{start_val:.6f},{end_val:.6f},"
                    f"stroop,{acc:.2f},{seq_str}\n"
                )

    def reset_ui(self):
        self.current_loop = 0
        self.current_index = 0
        self.sequence = []
        self.results_per_loop = []
        self.details_per_loop = []

        # 重置时间记录
        self.eeg_exp_start = None
        self.eeg_exp_end = None
        self.loop_eeg_start = []
        self.loop_eeg_end = []

        # 重置目录相关（不清空界面上的姓名输入框）
        self.current_user_name = None
        self.user_dir = None
        self.run_dir = None
        self.run_timestamp = None

        self.stim_label.hide()
        self.btn_left.hide()
        self.btn_right.hide()
        self.btn_container.hide()
        self.hint_label.hide()
        self.countdown_label.hide()

        self.name_input.parent().show()
        self.start_btn.show()
        self.name_input.setFocus()

    def keyPressEvent(self, event):
        if (
            event.key() in (QtCore.Qt.Key.Key_Left, QtCore.Qt.Key.Key_Right)
            and self.btn_left.isVisible()
            and self.btn_left.isEnabled()
        ):
            if event.key() == QtCore.Qt.Key.Key_Left:
                self.record_response(True)
            elif event.key() == QtCore.Qt.Key.Key_Right:
                self.record_response(False)
        super().keyPressEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = Page5Widget()
    w.show()
    sys.exit(app.exec())
