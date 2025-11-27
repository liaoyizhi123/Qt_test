import os
import math
from datetime import datetime
import sys

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QDoubleSpinBox,
    QPushButton,
    QMessageBox,
    QComboBox,
)
from PyQt6.QtGui import QShortcut, QKeySequence


class Page11Widget(QWidget):
    """
    页面11：瞳孔光刺激范式（灰色基线 + 黑白正弦闪烁）

    流程：
      0. 填姓名 & Trials、基线/刺激/休息参数，点击“开始实验”；
         - 检查 EEG Page2 是否在监听；
         - 调用 Page2.start_saving(run_dir) 开始写 EEG CSV + markers.csv。
      1. 准备期 10 秒：
         - 灰色 RGB(128,128,128) 背景；
         - 中央圆形注视点 RGB(64,64,64)；
         - 底部文字：“10秒后将开始实验”，数字动态递减。
      2. Trial 循环，每个 trial：
         (a) 基线期（默认 3 秒，可设置）：
             - 灰背景 + 中央注视点；
             - 下方文字：“请注视圆点”；
             - 记录 baseline_start / baseline_end（校准电脑时间）。
         (b) 刺激期（默认 6 秒，可设置）：
             - 全屏亮度按正弦在黑白之间平滑变化（从黑开始）；
             - 频率只能为 0.5 / 1 / 2 Hz（下拉选择）；
             - 公式：L(t) = 0.5 * (1 - cos(2π f t))，0=最黑，1=最白；
             - 周期：T = 1/f，完整周期：黑→白→黑；
             - 记录 stim_start / stim_end。
         (c) 休息期（默认 6 秒，可设置）：
             - 灰背景；
             - 下方文字：“请休息N秒”，N 倒计时；
             - 记录 rest_start / rest_end。
      3. 全部 trials 完成：
         - 灰背景 + “实验结束，N秒”倒计时 10 秒；
         - 调用 Page2.stop_saving() 停止写 EEG；
         - 写 txt 报告后退出全屏，恢复原界面。

    txt 报告格式（按“半周期”写行）：
        start_time,end_time,label
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pupil Flicker Paradigm (Page11)")

        # 当前系统类型
        self._is_macos = sys.platform.startswith("darwin")
        self._is_windows = sys.platform.startswith("win")

        # ====== 数据根目录：data/pupil ======
        self.data_root = "data"
        self.pupil_root = os.path.join(self.data_root, "pupil")
        os.makedirs(self.pupil_root, exist_ok=True)

        # 当前被试 & 本次实验 run 的目录
        self.current_user_name: str | None = None
        self.user_dir: str | None = None  # data/pupil/<name>
        self.run_dir: str | None = None  # data/pupil/<name>/<timestamp>
        self.run_timestamp: str | None = None  # YYYYMMDDHHMMSS

        # -------------------- 默认参数 --------------------
        self.initial_countdown = 10  # 准备期倒计时（秒）
        self.final_countdown = 10  # 结束倒计时（秒）
        self.default_trials = 10  # 默认 trial 数

        self.baseline_duration = 3.0  # 基线时长（秒）
        self.stim_duration = 6.0  # 刺激时长（秒）
        self.rest_duration = 6.0  # 休息时长（秒）
        self.stim_freq_hz = 0.5  # 刺激频率（Hz）

        # -------------------- 状态量 --------------------
        self.total_trials = self.default_trials
        self.trial_index = -1  # 当前 trial 索引（0-based）
        self.trial_logs: list[dict] = []  # trial 日志列表

        # 与 EEG 采集页面（Page2）联动
        self.eeg_page = None
        self.eeg_exp_start = None
        self.eeg_exp_end = None

        # 刺激期计时器（正弦亮度更新）
        self._stim_timer: QtCore.QTimer | None = None
        self._stim_elapsed_ms: int = 0

        # 各阶段倒计时计时器
        self._initial_timer: QtCore.QTimer | None = None
        self._rest_timer: QtCore.QTimer | None = None
        self._final_timer: QtCore.QTimer | None = None

        self._initial_remaining: int = 0
        self._rest_remaining: int = 0
        self._final_remaining: int = 0

        # 全屏专用窗口（只显示实验画面）
        self.fullscreen_win: QtWidgets.QWidget | None = None
        self._fs_esc_shortcut: QShortcut | None = None  # 全屏窗口里的 ESC

        # -------------------- UI --------------------
        self._build_ui()

        # ESC 中断快捷键（在主窗口中也生效）
        self.shortcut_esc = QShortcut(QKeySequence(QtCore.Qt.Key.Key_Escape), self)
        self.shortcut_esc.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
        self.shortcut_esc.activated.connect(self.abort_and_finalize)

    # ==================== UI 构建 ====================
    def _build_ui(self):
        # 整体布局：上下有 stretch，中间一个块（说明+设置+按钮）整体居中
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)
        root.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.root_layout = root

        # 中心块
        self.center_widget = QWidget()
        center_layout = QVBoxLayout(self.center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(16)
        center_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        # 顶部说明
        self.instruction_label = QLabel(
            "瞳孔光刺激范式：\n"
            "灰色基线 + 黑白正弦闪烁刺激。\n"
            "填写信息后点击“开始实验”，实验过程将在单独的全屏窗口中展示。"
        )
        f = self.instruction_label.font()
        f.setPointSize(13)
        self.instruction_label.setFont(f)
        self.instruction_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.instruction_label.setWordWrap(True)
        center_layout.addWidget(self.instruction_label)

        # ---- 设置区 ----
        settings = QWidget()
        settings.setMaximumWidth(520)
        form = QFormLayout(settings)
        form.setFormAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        self.name_input = QLineEdit()
        form.addRow("姓名:", self.name_input)

        self.trials_spin = QSpinBox()
        self.trials_spin.setRange(1, 1000)
        self.trials_spin.setValue(self.default_trials)
        form.addRow("Trials 数:", self.trials_spin)

        # 基线时长
        self.baseline_spin = QDoubleSpinBox()
        self.baseline_spin.setDecimals(1)
        self.baseline_spin.setRange(0.5, 120.0)
        self.baseline_spin.setSingleStep(0.5)
        self.baseline_spin.setValue(self.baseline_duration)
        form.addRow("基线时长 (秒):", self.baseline_spin)

        # 刺激频率：只能 0.5 / 1 / 2 Hz
        self.freq_combo = QComboBox()
        self.freq_combo.addItem("0.5 Hz", 0.5)
        self.freq_combo.addItem("1 Hz", 1.0)
        self.freq_combo.addItem("2 Hz", 2.0)
        self.freq_combo.setCurrentIndex(0)  # 默认 0.5 Hz
        form.addRow("刺激频率 (Hz):", self.freq_combo)

        # 刺激时长
        self.stim_spin = QDoubleSpinBox()
        self.stim_spin.setDecimals(1)
        self.stim_spin.setRange(0.5, 600.0)
        self.stim_spin.setSingleStep(0.5)
        self.stim_spin.setValue(self.stim_duration)
        form.addRow("刺激时长 (秒):", self.stim_spin)

        # 休息时长
        self.rest_spin = QDoubleSpinBox()
        self.rest_spin.setDecimals(1)
        self.rest_spin.setRange(0.5, 600.0)
        self.rest_spin.setSingleStep(0.5)
        self.rest_spin.setValue(self.rest_duration)
        form.addRow("休息时长 (秒):", self.rest_spin)

        self.settings_widget = settings
        center_layout.addWidget(settings)

        # 开始按钮
        self.start_btn = QPushButton("开始实验")
        self.start_btn.clicked.connect(self.on_start_clicked)
        center_layout.addWidget(self.start_btn, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        # 把中心块上下居中
        root.addStretch()
        root.addWidget(self.center_widget, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)
        root.addStretch()

        # ---- 实验显示区（只在全屏窗口中使用）----
        self.screen_container = QWidget()
        self.screen_container.hide()  # 初始不显示

        screen_layout = QVBoxLayout(self.screen_container)
        screen_layout.setContentsMargins(0, 0, 0, 0)
        screen_layout.setSpacing(20)

        # 中央区域：始终占满屏幕，用于固定注视点位置
        central_area = QWidget()
        central_layout = QVBoxLayout(central_area)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addStretch()

        # 中央圆形注视点 —— 始终在 central_area 的几何中心
        self.fixation_label = QLabel()
        fixation_size = 40
        self.fixation_label.setFixedSize(fixation_size, fixation_size)
        self.fixation_label.setStyleSheet("background-color: rgb(64,64,64); border-radius: 20px;")
        self.fixation_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.fixation_label.hide()
        central_layout.addWidget(self.fixation_label, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)

        central_layout.addStretch()
        screen_layout.addWidget(central_area, stretch=1)

        # 底部文字提示：改为“悬浮”在圆点下方，不参与布局
        self.message_label = QLabel(self.screen_container)
        fm = self.message_label.font()
        fm.setPointSize(40)
        self.message_label.setFont(fm)
        self.message_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.message_label.setWordWrap(True)
        # 文本颜色改为白色
        self.message_label.setStyleSheet("color: white;")
        self.message_label.hide()

    # 让窗口 resize 时，文字跟着保持在圆点下方
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_message_label_position()

    def _update_message_label_position(self):
        """根据当前圆点位置，把 message_label 移动到圆点正下方，但不改变圆点布局。"""
        if not self.screen_container.isVisible():
            return
        if not self.message_label.isVisible():
            # 文字隐藏时不必计算
            return

        # 圆点中心在 screen_container 坐标系中的位置
        center_in_container = self.fixation_label.mapTo(
            self.screen_container, self.fixation_label.rect().center()
        )

        margin = 20  # 圆点和文字之间的垂直间距
        label_height = self.message_label.sizeHint().height()
        width = self.screen_container.width()

        x = 0
        y = center_in_container.y() + self.fixation_label.height() // 2 + margin

        # 防止超出底部，必要时往上抬一点
        if y + label_height > self.screen_container.height():
            y = self.screen_container.height() - label_height - 10

        self.message_label.setGeometry(x, y, width, label_height)

    # ==================== 与 Page2 的时间交互 ====================
    def _get_eeg_time_from_page(self):
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

    # ==================== 入口：开始实验 ====================
    def on_start_clicked(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "错误", "请输入姓名！")
            return

        trials = self.trials_spin.value()
        if trials <= 0:
            QMessageBox.warning(self, "错误", "Trials 数必须大于 0！")
            return

        # ====== 检查 EEG Page2 是否在监听 ======
        eeg_page = getattr(self, "eeg_page", None)
        if eeg_page is None or not hasattr(eeg_page, "is_listening"):
            QMessageBox.warning(self, "错误", "未找到 EEG 采集页面，请在主程序中确保已创建并注入 Page2Widget。")
            return

        if not eeg_page.is_listening():
            QMessageBox.warning(
                self,
                "提示",
                "请先在【首页】点击“开始监测信号”，\n"
                "确保已经开始接收EEG数据后，再启动本实验范式。"
            )
            return

        # ====== 读取参数 ======
        baseline = float(self.baseline_spin.value())
        stim_dur = float(self.stim_spin.value())
        rest_dur = float(self.rest_spin.value())
        freq = float(self.freq_combo.currentData())

        if freq <= 0:
            QMessageBox.warning(self, "错误", "刺激频率必须大于 0！")
            return

        self.baseline_duration = baseline
        self.stim_duration = stim_dur
        self.rest_duration = rest_dur
        self.stim_freq_hz = freq

        self.total_trials = trials

        # ====== 构建目录结构：data/pupil/<name>/<timestamp>/ ======
        self.current_user_name = name
        self.user_dir = os.path.join(self.pupil_root, self.current_user_name)
        os.makedirs(self.user_dir, exist_ok=True)

        self.run_timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        self.run_dir = os.path.join(self.user_dir, self.run_timestamp)
        os.makedirs(self.run_dir, exist_ok=True)

        # ====== 启动 EEG CSV 记录 ======
        self.eeg_exp_start = None
        self.eeg_exp_end = None
        try:
            if hasattr(eeg_page, "start_saving"):
                eeg_page.start_saving(self.run_dir)
        except Exception:
            pass

        first_time = self._get_eeg_time_from_page()
        if first_time is not None:
            self.eeg_exp_start = first_time

        # ====== 初始化 trial 状态 ======
        self.trial_logs = []
        self.trial_index = -1

        # ====== UI：隐藏设置区，弹出全屏窗口 ======
        self.instruction_label.hide()
        self.settings_widget.hide()
        self.start_btn.hide()

        self._enter_fullscreen()
        self._start_initial_countdown()

    # ==================== 准备期（10秒） ====================
    def _start_initial_countdown(self):
        self._set_background_color(128, 128, 128)
        self.fixation_label.show()
        self.message_label.show()
        self._update_message_label_position()

        self._initial_remaining = int(self.initial_countdown)
        self.message_label.setText(f"{self._initial_remaining}秒后将开始实验")

        self._stop_initial_timer()
        self._initial_timer = QtCore.QTimer(self)
        self._initial_timer.timeout.connect(self._tick_initial_countdown)
        self._initial_timer.start(1000)

    def _tick_initial_countdown(self):
        self._initial_remaining -= 1
        if self._initial_remaining > 0:
            self.message_label.setText(f"{self._initial_remaining}秒后将开始实验")
        else:
            self._stop_initial_timer()
            self._start_next_trial()

    # ==================== Trial 流程 ====================
    def _start_next_trial(self):
        self.trial_index += 1
        if self.trial_index >= self.total_trials:
            self._start_final_countdown()
            return

        log = {
            "trial": self.trial_index + 1,
            "baseline_start": None,
            "baseline_end": None,
            "stim_start": None,
            "stim_end": None,
            "rest_start": None,
            "rest_end": None,
            "params": {
                "baseline": self.baseline_duration,
                "stim": self.stim_duration,
                "rest": self.rest_duration,
                "freq": self.stim_freq_hz,
            },
        }
        self.trial_logs.append(log)
        self._start_baseline()

    # ------ 基线期 ------
    def _start_baseline(self):
        self._set_background_color(128, 128, 128)
        self.fixation_label.show()
        self.message_label.show()
        self.message_label.setText("请注视圆点")
        self._update_message_label_position()

        t = self._get_eeg_time_from_page()
        if t is not None:
            self.trial_logs[self.trial_index]["baseline_start"] = t
            if self.eeg_exp_start is None:
                self.eeg_exp_start = t

        QtCore.QTimer.singleShot(
            int(self.baseline_duration * 1000),
            self._end_baseline_and_start_stimulus
        )

    def _end_baseline_and_start_stimulus(self):
        t = self._get_eeg_time_from_page()
        if t is not None:
            self.trial_logs[self.trial_index]["baseline_end"] = t
        self._start_stimulus()

    # ------ 刺激期：黑白正弦闪烁 ------
    def _start_stimulus(self):
        # 刺激期不再隐藏文字标签，只清空文本，保证位置始终在圆点下方
        self.message_label.show()
        self.message_label.setText("")
        self._update_message_label_position()
        self.fixation_label.show()  # 如不想保留注视点可改为 hide()

        t = self._get_eeg_time_from_page()
        if t is not None:
            self.trial_logs[self.trial_index]["stim_start"] = t
            if self.eeg_exp_start is None:
                self.eeg_exp_start = t

        self._stim_elapsed_ms = 0
        self._stop_stim_timer()
        self._stim_timer = QtCore.QTimer(self)
        self._stim_timer.setInterval(16)  # ~60Hz
        self._stim_timer.timeout.connect(self._update_stimulus)
        self._stim_timer.start()

    def _update_stimulus(self):
        if self._stim_timer is None:
            return

        self._stim_elapsed_ms += self._stim_timer.interval()
        total_ms = int(self.stim_duration * 1000)

        t_sec = self._stim_elapsed_ms / 1000.0
        omega = 2.0 * math.pi * self.stim_freq_hz
        val = 0.5 * (1.0 - math.cos(omega * t_sec))  # 0..1
        val = max(0.0, min(1.0, val))
        brightness = int(round(255 * val))
        self._set_background_color(brightness, brightness, brightness)

        if self._stim_elapsed_ms >= total_ms:
            self._stop_stim_timer()
            self._end_stimulus()

    def _end_stimulus(self):
        t = self._get_eeg_time_from_page()
        if t is not None:
            self.trial_logs[self.trial_index]["stim_end"] = t
            self.eeg_exp_end = t
        self._start_rest()

    # ------ 休息期 ------
    def _start_rest(self):
        self._set_background_color(128, 128, 128)
        self.fixation_label.hide()
        self.message_label.show()

        t = self._get_eeg_time_from_page()
        if t is not None:
            self.trial_logs[self.trial_index]["rest_start"] = t

        self._rest_remaining = int(self.rest_duration)
        self.message_label.setText(f"请休息{self._rest_remaining}秒")
        self._update_message_label_position()

        self._stop_rest_timer()
        self._rest_timer = QtCore.QTimer(self)
        self._rest_timer.timeout.connect(self._tick_rest)
        self._rest_timer.start(1000)

    def _tick_rest(self):
        self._rest_remaining -= 1
        if self._rest_remaining > 0:
            self.message_label.setText(f"请休息{self._rest_remaining}秒")
        else:
            self._stop_rest_timer()
            t = self._get_eeg_time_from_page()
            if t is not None:
                self.trial_logs[self.trial_index]["rest_end"] = t
                self.eeg_exp_end = t
            self._start_next_trial()

    # ==================== 结束倒计时 & 收尾 ====================
    def _start_final_countdown(self):
        self._set_background_color(128, 128, 128)
        self.fixation_label.hide()
        self.message_label.show()

        self._final_remaining = int(self.final_countdown)
        self.message_label.setText(f"实验结束，{self._final_remaining}秒")
        self._update_message_label_position()

        self._stop_final_timer()
        self._final_timer = QtCore.QTimer(self)
        self._final_timer.timeout.connect(self._tick_final)
        self._final_timer.start(1000)

    def _tick_final(self):
        self._final_remaining -= 1
        if self._final_remaining > 0:
            self.message_label.setText(f"实验结束，{self._final_remaining}秒")
        else:
            self._stop_final_timer()
            self._finish_and_save()

    def _finish_and_save(self):
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

        self._write_report(aborted=False)
        self._reset_ui()
        self._exit_fullscreen()

    def abort_and_finalize(self):
        """
        ESC 中断：
        - 停止 EEG 保存（若存在）
        - 写 ABORT 报告
        - 重置 UI & 退出全屏
        """
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

        self._write_report(aborted=True)
        self._reset_ui()
        self._exit_fullscreen()

    # ==================== 报告写入（按半周期） ====================
    def _write_report(self, aborted: bool = False):
        name = self.current_user_name or self.name_input.text().strip() or "unknown"
        flag = "ABORT" if aborted else "DONE"

        base_dir = self.run_dir or self.user_dir or self.pupil_root
        os.makedirs(base_dir, exist_ok=True)

        ts_for_name = self.run_timestamp or datetime.now().strftime("%Y%m%d%H%M%S")

        fname = os.path.join(
            base_dir,
            f"PUPIL_{name}_{ts_for_name}_trials{len(self.trial_logs)}_{flag}.txt"
        )

        try:
            with open(fname, "w", encoding="utf-8") as f:
                for rec in self.trial_logs:
                    stim_start = rec.get("stim_start")
                    stim_end = rec.get("stim_end")
                    params = rec.get("params", {})
                    freq = float(params.get("freq", self.stim_freq_hz or 0.0))
                    stim_dur = float(params.get("stim", self.stim_duration))

                    # 若缺少关键数据，写两行 NaN 占位（保持 black_to_white / white_to_black 结构）
                    if not isinstance(stim_start, (int, float)) or freq <= 0 or stim_dur <= 0:
                        start_val = float("nan")
                        end_val = float("nan")
                        f.write(f"{start_val:.6f},{end_val:.6f},black_to_white\n")
                        f.write(f"{start_val:.6f},{end_val:.6f},white_to_black\n")
                        continue

                    stim_start = float(stim_start)
                    stim_end_val = float(stim_end) if isinstance(stim_end, (int, float)) else None

                    T = 1.0 / freq  # 完整周期：黑→白→黑
                    cycles = int(stim_dur * freq + 1e-6)
                    if cycles <= 0:
                        continue

                    for c in range(cycles):
                        cycle_start = stim_start + c * T

                        # 1) 黑到白：从周期开始到 T/2
                        btow_start = cycle_start
                        btow_end = btow_start + T / 2.0

                        # 2) 白到黑：从 T/2 到 T
                        wtob_start = cycle_start + T / 2.0
                        wtob_end = wtob_start + T / 2.0

                        # 若 stim_end 已知且半周期结束超出实际结束时间，则跳过该半周期
                        if stim_end_val is not None:
                            if btow_end > stim_end_val + 1e-6:
                                continue
                            if wtob_end > stim_end_val + 1e-6:
                                f.write(f"{btow_start:.6f},{btow_end:.6f},black_to_white\n")
                                continue

                        f.write(f"{btow_start:.6f},{btow_end:.6f},black_to_white\n")
                        f.write(f"{wtob_start:.6f},{wtob_end:.6f},white_to_black\n")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"写入日志失败：{e}")

    # ==================== 工具：UI & 计时器 & 全屏 ====================
    def _target_for_background(self):
        if self.fullscreen_win is not None:
            return self.fullscreen_win
        return self

    def _set_background_color(self, r: int, g: int, b: int):
        target = self._target_for_background()
        target.setStyleSheet(f"background-color: rgb({r},{g},{b});")

    def _clear_background_color(self):
        target = self._target_for_background()
        target.setStyleSheet("")

    def _stop_initial_timer(self):
        if self._initial_timer is not None:
            try:
                self._initial_timer.stop()
                self._initial_timer.deleteLater()
            except Exception:
                pass
            self._initial_timer = None

    def _stop_rest_timer(self):
        if self._rest_timer is not None:
            try:
                self._rest_timer.stop()
                self._rest_timer.deleteLater()
            except Exception:
                pass
            self._rest_timer = None

    def _stop_final_timer(self):
        if self._final_timer is not None:
            try:
                self._final_timer.stop()
                self._final_timer.deleteLater()
            except Exception:
                pass
            self._final_timer = None

    def _stop_stim_timer(self):
        if self._stim_timer is not None:
            try:
                self._stim_timer.stop()
                self._stim_timer.deleteLater()
            except Exception:
                pass
            self._stim_timer = None

    def _enter_fullscreen(self):
        # 根据系统分别采用你测试通过的方案
        if self._is_macos:
            # macOS：使用 WindowFullScreen 状态 + show()
            if self.fullscreen_win is not None:
                return

            self.fullscreen_win = QtWidgets.QWidget()
            self.fullscreen_win.setWindowFlags(
                QtCore.Qt.WindowType.FramelessWindowHint | QtCore.Qt.WindowType.Window
            )
            self.fullscreen_win.setWindowState(QtCore.Qt.WindowState.WindowFullScreen)

            layout = QVBoxLayout(self.fullscreen_win)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)

            self.screen_container.setParent(self.fullscreen_win)
            self.screen_container.show()
            layout.addWidget(self.screen_container)

            self._fs_esc_shortcut = QShortcut(
                QKeySequence(QtCore.Qt.Key.Key_Escape), self.fullscreen_win
            )
            self._fs_esc_shortcut.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
            self._fs_esc_shortcut.activated.connect(self.abort_and_finalize)

            self.fullscreen_win.show()

        else:
            # Windows / 其它：使用 showFullScreen，更稳定
            if self.fullscreen_win is not None:
                return

            self.fullscreen_win = QtWidgets.QWidget()
            self.fullscreen_win.setWindowFlags(
                QtCore.Qt.WindowType.FramelessWindowHint
                | QtCore.Qt.WindowType.Window
            )

            layout = QVBoxLayout(self.fullscreen_win)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)

            self.screen_container.setParent(self.fullscreen_win)
            self.screen_container.show()
            layout.addWidget(self.screen_container)

            self._fs_esc_shortcut = QShortcut(
                QKeySequence(QtCore.Qt.Key.Key_Escape),
                self.fullscreen_win
            )
            self._fs_esc_shortcut.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
            self._fs_esc_shortcut.activated.connect(self.abort_and_finalize)

            self.fullscreen_win.showFullScreen()
            self.fullscreen_win.raise_()
            self.fullscreen_win.activateWindow()

    def _exit_fullscreen(self):
        if self.fullscreen_win is None:
            return

        self._clear_background_color()

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

    def _reset_ui(self):
        self._stop_initial_timer()
        self._stop_rest_timer()
        self._stop_final_timer()
        self._stop_stim_timer()

        self.fixation_label.hide()
        self.message_label.hide()
        self.message_label.clear()

        self.instruction_label.show()
        self.settings_widget.show()
        self.start_btn.show()
        self.name_input.setFocus()

        self.trial_index = -1
        self.trial_logs = []
        self._stim_elapsed_ms = 0

        self.current_user_name = None
        self.user_dir = None
        self.run_dir = None
        self.run_timestamp = None
        self.eeg_exp_start = None
        self.eeg_exp_end = None


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    w = Page11Widget()
    w.resize(800, 600)
    w.show()
    sys.exit(app.exec())
