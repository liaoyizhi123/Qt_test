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

    新版时间 & 文件记录逻辑（对齐 Page7 / Page6）：
      - 被试与参数设置页面为“卡片”布局，点击【开始实验】后：
          * 检查 Page2 是否已开始监测信号（is_listening）；
          * 在 data/stroop/<Name>/<YYYYMMDDHHMMSS>/ 下创建本次 run 目录；
          * 调用 Page2.start_saving(run_dir)，开始写 EEG CSV 和 triggers.csv。
      - 每个 loop（Run）：
          * 在 loop 开始时通过 Page2.set_trigger(loop_start_code) 写入一次 trigger；
          * 在 loop 结束时通过 Page2.set_trigger(loop_end_code) 写入一次 trigger；
      - 实验自然结束或 ESC 中断时：
          * 调用 Page2.stop_saving() 关闭 EEG 与 trigger 文件；
          * Page5 读取本次 run_dir 下的 triggers.csv，筛选出属于 Stroop 的
            loop_start / loop_end trigger，按出现顺序为每个 loop 回填
            loop_start_time / loop_end_time；
          * save_report() 中，每一行第 1、2 列即为该 loop 的 EEG 时间范围，
            可对齐 EEG CSV 做切片。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Stroop 实验")
        self.setMinimumSize(900, 700)

        # 当前系统类型（用于全屏窗口策略）
        self._is_macos = sys.platform.startswith("darwin")
        self._is_windows = sys.platform.startswith("win")
        self.fullscreen_win: QtWidgets.QWidget | None = None
        self._fs_esc_shortcut: QShortcut | None = None

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
        self.delay = 2.0            # 展示期时长（秒）
        self.colors_count = 6
        self.initial_countdown = 10
        self.rest_duration = 10
        self.separate_phases = False  # 是否分离展示与作答
        self.response_window = 2.0    # 分离模式下作答窗口（秒）

        # 实验状态
        self.current_loop = 0
        self.current_index = 0
        # sequence: list[(word_cn, color_en)]
        self.sequence: list[tuple[str, str]] = []
        # 每轮：正确(True)/错误(False) 的列表
        self.results_per_loop: list[list[bool]] = []
        # 每轮：[(word_cn, color_en, tag2), ...]  tag 是 "TT"/"FN" 等
        self.details_per_loop: list[list[tuple[str, str, str]]] = []
        self.response_recorded = False   # 本 trial 是否已作答
        self.input_enabled = False
        self.is_running = False

        # 与 EEG 采集页面（Page2）联动
        # 需要在主程序中设置：page5.eeg_page = page2
        self.eeg_page = None
        self.eeg_exp_start: float | None = None
        self.eeg_exp_end: float | None = None
        self.loop_eeg_start: list[float | None] = []
        self.loop_eeg_end: list[float | None] = []

        # ===== 触发器（trigger）相关（专用于 Stroop） =====
        # 这里使用 1 / 2 标记 Stroop 每个 loop 的开始 / 结束
        self.triggers_filename = "triggers.csv"
        self.trigger_codes: dict[str, int] = {
            "loop_start": 1,
            "loop_end": 2,
        }
        self.trigger_code_labels: dict[int, str] = {
            0: "baseline",
            1: "stroop_loop_start",
            2: "stroop_loop_end",
        }

        # =====  UI 构建  =====
        self._build_main_ui()
        self._build_screen_ui()
        self._build_shortcuts()

    # ==================== 首页：表单 + 按钮（卡片布局） ====================
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
            "任务：判断【字意】与【颜色】是否一致。\n"
            "按【← 左方向键】表示“一致”，按【→ 右方向键】表示“不一致”。"
        )
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
        self.trials_spin.setRange(5, 200)
        self.trials_spin.setValue(self.trials)
        form.addRow("Trials per Run:", self.trials_spin)

        # 展示期 delay（秒）
        self.delay_spin = QDoubleSpinBox()
        self.delay_spin.setRange(0.1, 10.0)
        self.delay_spin.setSingleStep(0.1)
        self.delay_spin.setValue(self.delay)
        form.addRow("展示期 Delay (s):", self.delay_spin)

        # 分离模式下作答窗口（秒）
        self.response_spin = QDoubleSpinBox()
        self.response_spin.setRange(0.1, 10.0)
        self.response_spin.setSingleStep(0.1)
        self.response_spin.setValue(self.response_window)
        form.addRow("作答窗口 (s):", self.response_spin)

        self.colors_spin = QSpinBox()
        self.colors_spin.setRange(2, len(COLOR_OPTIONS))
        self.colors_spin.setValue(self.colors_count)
        form.addRow("Colors (max 6):", self.colors_spin)

        # 是否分离展示与操作
        self.split_checkbox = QtWidgets.QCheckBox("是（先展示，后作答）")
        self.split_checkbox.setChecked(False)  # 默认“否”
        form.addRow("展示/操作分离:", self.split_checkbox)

        card_layout.addWidget(self.settings_widget)

        # 开始按钮
        self.start_btn = QPushButton("开始 Stroop 实验")
        self.start_btn.clicked.connect(self.start_experiment)
        card_layout.addWidget(self.start_btn, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        root.addStretch()
        root.addWidget(self.center_card, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)
        root.addStretch()

    # ==================== 实验显示界面（全屏内容） ====================
    def _build_screen_ui(self):
        self.screen_container = QtWidgets.QWidget(self)
        self.screen_container.setObjectName("full_screen")
        self.screen_container.hide()

        screen_layout = QVBoxLayout(self.screen_container)
        screen_layout.setContentsMargins(40, 40, 40, 40)
        screen_layout.setSpacing(18)

        screen_layout.addStretch()

        # 主刺激文字区域（用于显示 Stroop 字符）
        self.stage_label = QLabel("", self.screen_container)
        fs = self.stage_label.font()
        fs.setPointSize(72)
        self.stage_label.setFont(fs)
        self.stage_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.stage_label.setWordWrap(True)
        self.stage_label.setMinimumWidth(600)
        self.stage_label.hide()

        stage_wrapper = QtWidgets.QWidget(self.screen_container)
        h = QHBoxLayout(stage_wrapper)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addStretch()
        h.addWidget(self.stage_label)
        h.addStretch()
        screen_layout.addWidget(stage_wrapper)

        # 倒计时 / 提示文字
        self.countdown_label = QLabel("", self.screen_container)
        fc = self.countdown_label.font()
        fc.setPointSize(36)
        self.countdown_label.setFont(fc)
        self.countdown_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.countdown_label.hide()
        screen_layout.addWidget(self.countdown_label, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        # 按钮容器（判断“一致 / 不一致”）
        self.btn_container = QtWidgets.QWidget(self.screen_container)
        self.btn_container.setFixedHeight(80)
        self.btn_container.setFixedWidth(400)
        btn_layout = QtWidgets.QHBoxLayout(self.btn_container)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(40)
        btn_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        self.btn_cong = QPushButton("← 一致", self.screen_container)
        self.btn_incong = QPushButton("→ 不一致", self.screen_container)
        for btn in (self.btn_cong, self.btn_incong):
            btn.setCheckable(True)
            btn.setFixedSize(140, 50)

        style = (
            "QPushButton{background-color:#4caf50;color:white;font-size:18px;}"
            "QPushButton:checked{background-color:#388e3c;}"
            "QPushButton:disabled{background-color:gray;}"
            "QPushButton:disabled:checked{background-color:#388e3c;}"
        )
        self.btn_cong.setStyleSheet(style)
        self.btn_incong.setStyleSheet(style)

        self.btn_cong.clicked.connect(lambda: self.record_response(True))
        self.btn_incong.clicked.connect(lambda: self.record_response(False))

        btn_layout.addWidget(self.btn_cong)
        btn_layout.addWidget(self.btn_incong)

        self.btn_container.hide()
        screen_layout.addWidget(self.btn_container, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        # 反馈标签（✔ / ❌ 或提示）
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

    # ==================== Stroop 判定工具 ====================
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

    # ==================== 入口：开始实验 ====================
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
        self.response_window = self.response_spin.value()
        self.colors_count = self.colors_spin.value()
        self.separate_phases = self.split_checkbox.isChecked()

        self.current_loop = 0  # 将在 _start_first_loop 中变为 1
        self.current_index = 0
        self.sequence = []
        self.results_per_loop = [[] for _ in range(self.loops)]
        self.details_per_loop = [[] for _ in range(self.loops)]
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
                # Page2 内部处理错误，这里不中断 Stroop 实验
                pass

        # 切换到全屏界面
        self.center_card.hide()
        self._enter_fullscreen()

        # 初始倒计时（仅界面提示，不参与时间计算）
        self._show_fullscreen_message(
            "{n}秒后将开始 Stroop 实验",
            self.initial_countdown,
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
        生成本轮 Stroop 刺激列表，发送 loop_start trigger，然后进入第一 trial。
        """
        if not self.is_running:
            return
        if self.current_loop < 1 or self.current_loop > self.loops:
            return

        # 生成序列：颜色均匀 + 相邻颜色不重复；一半 congruent 一半 incongruent
        opts = COLOR_OPTIONS[: self.colors_count]
        mapping = {w: c for w, c in opts}
        words = list(mapping.keys())
        colors = list(mapping.values())

        if not colors or not words:
            QMessageBox.critical(self, "配置错误", "颜色数量为 0，无法生成 Stroop 序列。")
            self.abort_and_finalize()
            return

        # 构造颜色列表，让每种颜色出现次数尽量均衡
        full = self.trials // len(colors)
        rem = self.trials % len(colors)
        clist = colors * full + random.sample(colors, rem) if rem > 0 else colors * full
        if not clist:
            clist = random.choices(colors, k=self.trials)

        # 打乱，并确保相邻颜色尽量不重复
        random.shuffle(clist)
        for _ in range(50):
            if all(clist[i] != clist[i + 1] for i in range(len(clist) - 1)):
                break
            random.shuffle(clist)

        # 一半 congruent，一半 incongruent
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
                if not cands:
                    cands = [x for x in words if x != inv[col]]
                w = random.choice(cands)
            self.sequence.append((w, col))
            prev_word = w

        self.current_index = 0
        self.response_recorded = False
        self.input_enabled = False

        # 显示区域
        self.stage_label.show()
        self.feedback_label.show()
        self.btn_container.show()
        self.countdown_label.hide()

        # 发送 loop_start trigger
        self._send_loop_trigger("loop_start")

        # 进入第一 trial
        self._show_stimulus()

    def _show_stimulus(self):
        if not self.is_running:
            return

        if self.current_index >= len(self.sequence):
            self._end_loop()
            return

        self.response_recorded = False
        self.input_enabled = False
        self.btn_cong.setChecked(False)
        self.btn_incong.setChecked(False)
        self.btn_cong.setEnabled(False)
        self.btn_incong.setEnabled(False)
        self.feedback_label.clear()
        self.feedback_label.setStyleSheet("border:none;")

        w, c = self.sequence[self.current_index]
        self.stage_label.setText(w)
        self.stage_label.setStyleSheet(
            f"background-color: lightgray; color: {c}; padding: 18px 36px; border-radius: 8px;"
        )
        if self.fullscreen_win is not None:
            self.fullscreen_win.raise_()
            self.fullscreen_win.activateWindow()
        else:
            self.activateWindow()
            self.setFocus()

        if self.separate_phases:
            # 展示期：按钮隐藏
            self.btn_cong.hide()
            self.btn_incong.hide()
            self.feedback_label.setText("请注视刺激")
            self.feedback_label.setStyleSheet("color:black;border:none;")
            QtCore.QTimer.singleShot(int(self.delay * 1000), self._start_response_phase)
        else:
            # 原始模式：展示+作答合一
            self.btn_cong.show()
            self.btn_incong.show()
            self.feedback_label.setText("")
            QtCore.QTimer.singleShot(200, self._enable_inputs)
            QtCore.QTimer.singleShot(int(self.delay * 1000), self._next_stimulus)

    def _start_response_phase(self):
        if not self.is_running:
            return
        if self.current_index >= len(self.sequence):
            return

        self.btn_cong.show()
        self.btn_incong.show()
        self.btn_cong.setEnabled(True)
        self.btn_incong.setEnabled(True)
        self.input_enabled = True

        self.feedback_label.setText("现在判断：左=一致，右=不一致")
        self.feedback_label.setStyleSheet("color:black;border:none;")

        QtCore.QTimer.singleShot(int(self.response_window * 1000), self._finish_trial)

    def _enable_inputs(self):
        if not self.is_running:
            return
        if not self.separate_phases and self.current_index < len(self.sequence):
            self.input_enabled = True
            self.btn_cong.setEnabled(True)
            self.btn_incong.setEnabled(True)

    def record_response(self, user_cong: bool):
        """
        user_cong: True = 被试认为一致；False = 被试认为不一致
        """
        if (
            not self.is_running
            or not self.input_enabled
            or self.response_recorded
            or self.current_index >= len(self.sequence)
        ):
            return

        w, c = self.sequence[self.current_index]
        is_cong = self._is_congruent(w, c)
        is_correct = (user_cong == is_cong)

        # 正确率统计用
        self.results_per_loop[self.current_loop - 1].append(is_correct)

        # tag: 第一个字符是题目真值 T/F；第二个字符是被试表现 T/F
        gt_char = "T" if is_cong else "F"
        resp_char = "T" if is_correct else "F"
        tag = gt_char + resp_char

        self.details_per_loop[self.current_loop - 1].append((w, c, tag))

        self.btn_cong.setEnabled(False)
        self.btn_incong.setEnabled(False)
        if user_cong:
            self.btn_cong.setChecked(True)
        else:
            self.btn_incong.setChecked(True)

        mark = "✔" if is_correct else "❌"
        color = "green" if is_correct else "red"
        self.feedback_label.setText(mark)
        self.feedback_label.setStyleSheet(f"color:{color};border:none;")
        QApplication.processEvents()

        self.response_recorded = True
        self.input_enabled = False

    def _next_stimulus(self):
        # 非分离模式：delay 结束切下一 trial，未作答也算一次
        if not self.is_running:
            return
        if self.separate_phases:
            return

        if not self.response_recorded and self.current_index < len(self.sequence):
            w, c = self.sequence[self.current_index]
            is_cong = self._is_congruent(w, c)
            gt_char = "T" if is_cong else "F"
            tag = gt_char + "N"  # 未作答

            self.results_per_loop[self.current_loop - 1].append(False)
            self.details_per_loop[self.current_loop - 1].append((w, c, tag))

        self.current_index += 1
        self._show_stimulus()

    def _finish_trial(self):
        # 分离模式：作答窗口结束
        if not self.is_running:
            return
        if (not self.separate_phases) or self.current_index >= len(self.sequence):
            return

        if not self.response_recorded:
            w, c = self.sequence[self.current_index]
            is_cong = self._is_congruent(w, c)
            gt_char = "T" if is_cong else "F"
            tag = gt_char + "N"  # 未作答

            self.results_per_loop[self.current_loop - 1].append(False)
            self.details_per_loop[self.current_loop - 1].append((w, c, tag))

        self.current_index += 1
        self._show_stimulus()

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
                next_callback=self._finish_and_save,
            )
        else:
            # 循环间休息
            self._show_fullscreen_message(
                "{n}秒后将开始下一次实验",
                self.rest_duration,
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
                header = next(reader, None)  # 跳过表头
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
        将本次 Stroop 实验写入 txt 报告。

        每一行格式：
            loop_start_time,loop_end_time,stroop,accuracy,seq_str

        其中：
          - loop_start_time / loop_end_time 为该 loop 的开始/结束时间（秒），
            使用的是由 triggers.csv 回填的 EEG 时间轴；
          - accuracy 为该轮正确率；
          - seq_str 为该轮 trial 序列，形如：
              字‘红’颜色‘黄’TF|字‘蓝’颜色‘绿’TN|...
            其中 tag 为两个字符：
              第 1 个：T/F 表示题目是否一致
              第 2 个：T/F/N 表示被试是否判断正确/错误/未作答
        """
        name = (
            self.current_user_name
            or self.name
            or self.name_input.text().strip()
            or "unknown"
        )
        mode = "split" if self.separate_phases else "normal"
        flag = "ABORT" if aborted else "DONE"

        base_dir = self.run_dir or self.user_dir or self.stroop_root
        os.makedirs(base_dir, exist_ok=True)

        ts_for_name = self.run_timestamp or datetime.now().strftime("%Y%m%d%H%M%S")

        fname = os.path.join(
            base_dir,
            f"Stroop_{name}_{ts_for_name}_"
            f"loops{self.loops}_trials{self.trials}_delay{self.delay}_{mode}_{flag}.txt"
        )

        try:
            with open(fname, "w", encoding="utf-8") as f:
                for i in range(self.loops):
                    results = self.results_per_loop[i] if i < len(self.results_per_loop) else []
                    details = self.details_per_loop[i] if i < len(self.details_per_loop) else []

                    if results:
                        acc = sum(1 for r in results if r) / len(results)
                    else:
                        acc = 0.0

                    seq_items = []
                    for w, c, tag in details:
                        c_cn = COLOR_NAME_MAP.get(c, c)
                        seq_items.append(f"字‘{w}’颜色‘{c_cn}’{tag}")
                    seq_str = "|".join(seq_items)

                    start_t = self.loop_eeg_start[i] if i < len(self.loop_eeg_start) else None
                    end_t = self.loop_eeg_end[i] if i < len(self.loop_eeg_end) else None

                    if isinstance(start_t, (int, float)):
                        start_val = float(start_t)
                    else:
                        start_val = float("nan")

                    if isinstance(end_t, (int, float)):
                        end_val = float(end_t)
                    else:
                        end_val = float("nan")

                    f.write(
                        f"{start_val:.6f},{end_val:.6f},"
                        f"stroop,{acc:.2f},{seq_str}\n"
                    )
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"写入 Stroop 日志失败：{e}")

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
                  "word_cn": "红",
                  "color_en": "red",
                  "color_cn": "红",
                  "is_congruent": true,
                  "user_response": "congruent" / "incongruent" / null,
                  "tag": "TT",
                  "correct": true
                },
                ...
              ]
            },
            ...
          ]
        }
        """
        base_dir = self.run_dir or self.user_dir or self.stroop_root
        os.makedirs(base_dir, exist_ok=True)

        name = (
            self.current_user_name
            or self.name
            or self.name_input.text().strip()
            or "unknown"
        )

        timing = {
            "initial_countdown": int(self.initial_countdown),
            "delay_exposure": float(self.delay),
            "response_window": float(self.response_window),
            "rest_duration": int(self.rest_duration),
            "separate_phases": bool(self.separate_phases),
            "loops": int(self.loops),
            "trials_per_loop": int(self.trials),
        }

        loops_json: list[dict] = []
        for i in range(self.loops):
            results = self.results_per_loop[i] if i < len(self.results_per_loop) else []
            details = self.details_per_loop[i] if i < len(self.details_per_loop) else []

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

            if results:
                acc = sum(1 for r in results if r) / len(results)
            else:
                acc = 0.0

            trials_json = []
            for (w, c, tag) in details:
                is_cong = self._is_congruent(w, c)
                # tag[0] 应与 is_cong 一致（T/F）
                resp_flag = tag[1] if len(tag) > 1 else "N"
                if resp_flag == "N":
                    user_resp = None
                    correct = False
                elif resp_flag == "T":  # 回答正确
                    user_resp = "congruent" if is_cong else "incongruent"
                    correct = True
                else:  # "F" 回答错误
                    user_resp = "incongruent" if is_cong else "congruent"
                    correct = False

                trials_json.append(
                    {
                        "word_cn": w,
                        "color_en": c,
                        "color_cn": COLOR_NAME_MAP.get(c, c),
                        "is_congruent": bool(is_cong),
                        "user_response": user_resp,
                        "tag": tag,
                        "correct": correct,
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
    def _show_fullscreen_message(self, template: str, seconds: int, next_callback=None):
        """
        在全屏界面中央显示一个带倒计时的提示信息。
        """
        # 隐藏主文字 / 按钮 / 反馈
        self.stage_label.hide()
        self.btn_container.hide()
        self.feedback_label.hide()

        # 样式：简洁文字
        self.countdown_label.setStyleSheet("color:black;")
        self.countdown_label.show()

        self._countdown_value = int(seconds)
        self._countdown_template = template
        self.countdown_label.setText(template.format(n=self._countdown_value))

        if hasattr(self, "_countdown_timer") and self._countdown_timer is not None:
            try:
                self._countdown_timer.stop()
                self._countdown_timer.deleteLater()
            except Exception:
                pass

        self._countdown_timer = QtCore.QTimer(self)
        self._countdown_timer.timeout.connect(lambda: self._tick(next_callback))
        self._countdown_timer.start(1000)

    def _tick(self, next_callback):
        if not self.is_running:
            if hasattr(self, "_countdown_timer") and self._countdown_timer is not None:
                self._countdown_timer.stop()
            self.countdown_label.hide()
            return

        self._countdown_value -= 1
        if self._countdown_value > 0:
            self.countdown_label.setText(
                self._countdown_template.format(n=self._countdown_value)
            )
        else:
            if hasattr(self, "_countdown_timer") and self._countdown_timer is not None:
                self._countdown_timer.stop()
            self.countdown_label.hide()
            if callable(next_callback):
                next_callback()

    def reset_ui(self):
        """
        复位到首页状态。
        """
        if hasattr(self, "_countdown_timer") and self._countdown_timer is not None:
            try:
                self._countdown_timer.stop()
                self._countdown_timer.deleteLater()
            except Exception:
                pass
            self._countdown_timer = None

        self.stage_label.hide()
        self.countdown_label.hide()
        self.btn_container.hide()
        self.feedback_label.hide()

        # 重置实验状态
        self.current_loop = 0
        self.current_index = 0
        self.sequence = []
        self.results_per_loop = []
        self.details_per_loop = []
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

    # ==================== 全屏相关 ====================
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
    w = Page5Widget()
    w.show()
    sys.exit(app.exec())
