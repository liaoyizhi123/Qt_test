import os
import math
from datetime import datetime
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
    修改点：
    1. 字体全部为白色。
    2. 有圆点时，文字显示在圆点下方。
    3. 无圆点时（休息、结束），文字居中显示。
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pupil Flicker Paradigm (Page11)")
        # ====== 数据根目录：data/pupil ======
        self.data_root = "data"
        self.pupil_root = os.path.join(self.data_root, "pupil")
        os.makedirs(self.pupil_root, exist_ok=True)
        # 当前被试 & 本次实验 run 的目录
        self.current_user_name: str | None = None
        self.user_dir: str | None = None
        self.run_dir: str | None = None
        self.run_timestamp: str | None = None
        # -------------------- 默认参数 --------------------
        self.initial_countdown = 10
        self.final_countdown = 10
        self.default_trials = 10
        self.baseline_duration = 3.0
        self.stim_duration = 6.0
        self.rest_duration = 6.0
        self.stim_freq_hz = 0.5
        # -------------------- 状态量 --------------------
        self.total_trials = self.default_trials
        self.trial_index = -1
        self.trial_logs: list[dict] = []
        # 与 EEG 采集页面（Page2）联动
        self.eeg_page = None
        self.eeg_exp_start = None
        self.eeg_exp_end = None
        # 计时器
        self._stim_timer: QtCore.QTimer | None = None
        self._stim_elapsed_ms: int = 0
        self._initial_timer: QtCore.QTimer | None = None
        self._rest_timer: QtCore.QTimer | None = None
        self._final_timer: QtCore.QTimer | None = None
        self._initial_remaining: int = 0
        self._rest_remaining: int = 0
        self._final_remaining: int = 0
        # 全屏专用窗口
        self.fullscreen_win: QtWidgets.QWidget | None = None
        self._fs_esc_shortcut: QShortcut | None = None
        
        self._build_ui()
        
        # ESC 中断快捷键
        self.shortcut_esc = QShortcut(QKeySequence(QtCore.Qt.Key.Key_Escape), self)
        self.shortcut_esc.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
        self.shortcut_esc.activated.connect(self.abort_and_finalize)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)
        root.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.root_layout = root

        # --- 中心控制块 ---
        self.center_widget = QWidget()
        center_layout = QVBoxLayout(self.center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(16)
        center_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

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

        # 设置区
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
        self.baseline_spin = QDoubleSpinBox()
        self.baseline_spin.setDecimals(1)
        self.baseline_spin.setRange(0.5, 120.0)
        self.baseline_spin.setSingleStep(0.5)
        self.baseline_spin.setValue(self.baseline_duration)
        form.addRow("基线时长 (秒):", self.baseline_spin)
        self.freq_combo = QComboBox()
        self.freq_combo.addItem("0.5 Hz", 0.5)
        self.freq_combo.addItem("1 Hz", 1.0)
        self.freq_combo.addItem("2 Hz", 2.0)
        self.freq_combo.setCurrentIndex(0)
        form.addRow("刺激频率 (Hz):", self.freq_combo)
        self.stim_spin = QDoubleSpinBox()
        self.stim_spin.setDecimals(1)
        self.stim_spin.setRange(0.5, 600.0)
        self.stim_spin.setSingleStep(0.5)
        self.stim_spin.setValue(self.stim_duration)
        form.addRow("刺激时长 (秒):", self.stim_spin)
        self.rest_spin = QDoubleSpinBox()
        self.rest_spin.setDecimals(1)
        self.rest_spin.setRange(0.5, 600.0)
        self.rest_spin.setSingleStep(0.5)
        self.rest_spin.setValue(self.rest_duration)
        form.addRow("休息时长 (秒):", self.rest_spin)
        self.settings_widget = settings
        center_layout.addWidget(settings)

        self.start_btn = QPushButton("开始实验")
        self.start_btn.clicked.connect(self.on_start_clicked)
        center_layout.addWidget(self.start_btn, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        root.addStretch()
        root.addWidget(self.center_widget, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)
        root.addStretch()

        # ---- 实验显示区（全屏容器）----
        self.screen_container = QWidget()
        self.screen_container.hide()
        
        # 使用垂直布局，中间加弹簧，确保内容垂直居中
        screen_layout = QVBoxLayout(self.screen_container)
        screen_layout.setContentsMargins(0, 0, 0, 0)
        screen_layout.setSpacing(0)
        
        # 上方弹簧
        screen_layout.addStretch()
        
        # 1. 注视点
        self.fixation_label = QLabel()
        self.fixation_label.setFixedSize(40, 40)
        self.fixation_label.setStyleSheet("background-color: rgb(64,64,64); border-radius: 20px;")
        self.fixation_label.hide()
        screen_layout.addWidget(self.fixation_label, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)
        
        # 2. 间距 (点与字之间的距离)
        screen_layout.addSpacing(30)
        
        # 3. 文字提示
        self.message_label = QLabel("")
        fm = self.message_label.font()
        fm.setPointSize(40)
        fm.setBold(True) # 加粗看的更清楚
        self.message_label.setFont(fm)
        self.message_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        # 关键修改：白色字体
        self.message_label.setStyleSheet("color: white;")
        self.message_label.hide()
        screen_layout.addWidget(self.message_label, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)
        
        # 下方弹簧
        screen_layout.addStretch()

    # ==================== 功能逻辑 ====================

    def _get_eeg_time_from_page(self):
        eeg_page = getattr(self, "eeg_page", None)
        if eeg_page and hasattr(eeg_page, "get_last_eeg_time"):
            try:
                return eeg_page.get_last_eeg_time()
            except:
                pass
        return None

    def on_start_clicked(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "错误", "请输入姓名！")
            return
        trials = self.trials_spin.value()
        
        # 检查 EEG
        eeg_page = getattr(self, "eeg_page", None)
        if eeg_page is None or not hasattr(eeg_page, "is_listening"):
            QMessageBox.warning(self, "错误", "未找到 EEG 采集页面。")
            return
        if not eeg_page.is_listening():
            QMessageBox.warning(self, "提示", "请先在【首页】点击“开始监测信号”。")
            return

        # 参数设置
        self.total_trials = trials
        self.baseline_duration = self.baseline_spin.value()
        self.stim_duration = self.stim_spin.value()
        self.rest_duration = self.rest_spin.value()
        self.stim_freq_hz = float(self.freq_combo.currentData())

        # 目录创建
        self.current_user_name = name
        self.user_dir = os.path.join(self.pupil_root, self.current_user_name)
        os.makedirs(self.user_dir, exist_ok=True)
        self.run_timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        self.run_dir = os.path.join(self.user_dir, self.run_timestamp)
        os.makedirs(self.run_dir, exist_ok=True)

        # 开启保存
        try:
            eeg_page.start_saving(self.run_dir)
        except:
            pass
        
        t = self._get_eeg_time_from_page()
        if t: self.eeg_exp_start = t

        # 界面切换
        self.trial_logs = []
        self.trial_index = -1
        self.instruction_label.hide()
        self.settings_widget.hide()
        self.start_btn.hide()
        
        self._enter_fullscreen()
        self._start_initial_countdown()

    # --- 阶段 1: 初始倒计时 (有圆点，字在下面) ---
    def _start_initial_countdown(self):
        self._set_background_color(128, 128, 128)
        self.fixation_label.show() # 显示圆点 -> 文字会被挤到圆点下方
        self.message_label.show()
        
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

    def _start_next_trial(self):
        self.trial_index += 1
        if self.trial_index >= self.total_trials:
            self._start_final_countdown()
            return
        
        self.trial_logs.append({
            "trial": self.trial_index + 1,
            "baseline_start": None, "baseline_end": None,
            "stim_start": None, "stim_end": None,
            "rest_start": None, "rest_end": None,
            "params": {"freq": self.stim_freq_hz, "stim": self.stim_duration}
        })
        self._start_baseline()

    # --- 阶段 2: 基线 (有圆点，字在下面) ---
    def _start_baseline(self):
        self._set_background_color(128, 128, 128)
        self.fixation_label.show() # 显示圆点
        self.message_label.show()
        self.message_label.setText("请注视圆点")
        
        t = self._get_eeg_time_from_page()
        if t: 
            self.trial_logs[self.trial_index]["baseline_start"] = t
            if not self.eeg_exp_start: self.eeg_exp_start = t

        QtCore.QTimer.singleShot(int(self.baseline_duration * 1000), self._end_baseline)

    def _end_baseline(self):
        t = self._get_eeg_time_from_page()
        if t: self.trial_logs[self.trial_index]["baseline_end"] = t
        self._start_stimulus()

    # --- 阶段 3: 刺激 (全屏闪烁，圆点可选，无字) ---
    def _start_stimulus(self):
        self.message_label.setText("") # 清空文字，以免闪烁时干扰
        # 这里依然保持 show()，因为 setText("") 后它实际上不占用视觉空间，或者你可以选择 hide()
        # 建议保持 fixation_label.show() 让被试目光锁定
        self.fixation_label.show() 
        
        t = self._get_eeg_time_from_page()
        if t: 
            self.trial_logs[self.trial_index]["stim_start"] = t
            if not self.eeg_exp_start: self.eeg_exp_start = t
            
        self._stim_elapsed_ms = 0
        self._stop_stim_timer()
        self._stim_timer = QtCore.QTimer(self)
        self._stim_timer.setInterval(16)
        self._stim_timer.timeout.connect(self._update_stimulus)
        self._stim_timer.start()

    def _update_stimulus(self):
        self._stim_elapsed_ms += self._stim_timer.interval()
        total_ms = int(self.stim_duration * 1000)
        t_sec = self._stim_elapsed_ms / 1000.0
        omega = 2.0 * math.pi * self.stim_freq_hz
        
        # 0(黑) -> 1(白) -> 0(黑)
        val = 0.5 * (1.0 - math.cos(omega * t_sec))
        val = max(0.0, min(1.0, val))
        brightness = int(round(255 * val))
        
        self._set_background_color(brightness, brightness, brightness)
        
        if self._stim_elapsed_ms >= total_ms:
            self._stop_stim_timer()
            self._end_stimulus()

    def _end_stimulus(self):
        t = self._get_eeg_time_from_page()
        if t: 
            self.trial_logs[self.trial_index]["stim_end"] = t
            self.eeg_exp_end = t
        self._start_rest()

    # --- 阶段 4: 休息 (无圆点 -> 文字自动居中) ---
    def _start_rest(self):
        self._set_background_color(128, 128, 128)
        self.fixation_label.hide() # 隐藏圆点 -> 布局只有弹簧和文字 -> 文字居中
        self.message_label.show()
        
        t = self._get_eeg_time_from_page()
        if t: self.trial_logs[self.trial_index]["rest_start"] = t
        
        self._rest_remaining = int(self.rest_duration)
        self.message_label.setText(f"请休息{self._rest_remaining}秒")
        
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
            if t: 
                self.trial_logs[self.trial_index]["rest_end"] = t
                self.eeg_exp_end = t
            self._start_next_trial()

    # --- 阶段 5: 结束倒计时 (无圆点 -> 文字自动居中) ---
    def _start_final_countdown(self):
        self._set_background_color(128, 128, 128)
        self.fixation_label.hide() # 隐藏圆点 -> 文字居中
        self.message_label.show()
        
        self._final_remaining = int(self.final_countdown)
        self.message_label.setText(f"实验结束，{self._final_remaining}秒")
        
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
        if eeg_page:
            t = self._get_eeg_time_from_page()
            if t: self.eeg_exp_end = t
            try: eeg_page.stop_saving()
            except: pass
            
        self._write_report(aborted=False)
        self._reset_ui()
        self._exit_fullscreen()

    def abort_and_finalize(self):
        eeg_page = getattr(self, "eeg_page", None)
        if eeg_page:
            t = self._get_eeg_time_from_page()
            if t: self.eeg_exp_end = t
            try: eeg_page.stop_saving()
            except: pass
            
        self._write_report(aborted=True)
        self._reset_ui()
        self._exit_fullscreen()

    def _write_report(self, aborted: bool = False):
        name = self.current_user_name or "unknown"
        flag = "ABORT" if aborted else "DONE"
        base_dir = self.run_dir or self.user_dir or self.pupil_root
        ts = self.run_timestamp or datetime.now().strftime("%Y%m%d%H%M%S")
        fname = os.path.join(base_dir, f"PUPIL_{name}_{ts}_trials{len(self.trial_logs)}_{flag}.txt")
        
        try:
            with open(fname, "w", encoding="utf-8") as f:
                for rec in self.trial_logs:
                    stim_start = rec.get("stim_start")
                    stim_end = rec.get("stim_end")
                    params = rec.get("params", {})
                    freq = params.get("freq", 0.5)
                    stim_dur = params.get("stim", 6.0)
                    
                    if not isinstance(stim_start, (int, float)):
                        # 写占位
                        f.write(f"nan,nan,black_to_white\nnan,nan,white_to_black\n")
                        continue
                        
                    T = 1.0 / freq
                    cycles = int(stim_dur * freq + 1e-6)
                    
                    for c in range(cycles):
                        cycle_start = float(stim_start) + c * T
                        
                        # 1) Black -> White
                        btow_end = cycle_start + T/2.0
                        if stim_end and btow_end > stim_end + 0.01: continue
                        f.write(f"{cycle_start:.6f},{btow_end:.6f},black_to_white\n")
                        
                        # 2) White -> Black
                        wtob_start = btow_end
                        wtob_end = wtob_start + T/2.0
                        if stim_end and wtob_end > stim_end + 0.01: continue
                        f.write(f"{wtob_start:.6f},{wtob_end:.6f},white_to_black\n")
                        
        except Exception as e:
            print(f"写入报告失败: {e}")

    # --- 辅助 ---
    def _target_for_background(self):
        if self.fullscreen_win: return self.fullscreen_win
        return self

    def _set_background_color(self, r, g, b):
        self._target_for_background().setStyleSheet(f"background-color: rgb({r},{g},{b});")

    def _clear_background_color(self):
        self._target_for_background().setStyleSheet("")

    def _stop_initial_timer(self):
        if self._initial_timer: 
            try: self._initial_timer.stop(); self._initial_timer.deleteLater()
            except: pass
            self._initial_timer = None

    def _stop_rest_timer(self):
        if self._rest_timer:
            try: self._rest_timer.stop(); self._rest_timer.deleteLater()
            except: pass
            self._rest_timer = None
            
    def _stop_final_timer(self):
        if self._final_timer:
            try: self._final_timer.stop(); self._final_timer.deleteLater()
            except: pass
            self._final_timer = None

    def _stop_stim_timer(self):
        if self._stim_timer:
            try: self._stim_timer.stop(); self._stim_timer.deleteLater()
            except: pass
            self._stim_timer = None

    def _enter_fullscreen(self):
        if self.fullscreen_win: return
        self.fullscreen_win = QtWidgets.QWidget()
        self.fullscreen_win.setWindowFlags(QtCore.Qt.WindowType.FramelessWindowHint | QtCore.Qt.WindowType.Window)
        self.fullscreen_win.setWindowState(QtCore.Qt.WindowState.WindowFullScreen)
        
        layout = QVBoxLayout(self.fullscreen_win)
        layout.setContentsMargins(0, 0, 0, 0)
        self.screen_container.setParent(self.fullscreen_win)
        self.screen_container.show()
        layout.addWidget(self.screen_container)
        
        self._fs_esc_shortcut = QShortcut(QKeySequence(QtCore.Qt.Key.Key_Escape), self.fullscreen_win)
        self._fs_esc_shortcut.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
        self._fs_esc_shortcut.activated.connect(self.abort_and_finalize)
        
        self.fullscreen_win.show()

    def _exit_fullscreen(self):
        if not self.fullscreen_win: return
        self._clear_background_color()
        if self._fs_esc_shortcut:
            try: self._fs_esc_shortcut.deleteLater()
            except: pass
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
        
        self.instruction_label.show()
        self.settings_widget.show()
        self.start_btn.show()
        self.name_input.setFocus()
        
        self.trial_index = -1
        self.trial_logs = []
        self._stim_elapsed_ms = 0
        self.current_user_name = None
        self.run_timestamp = None
        self.eeg_exp_start = None
        self.eeg_exp_end = None

if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    w = Page11Widget()
    w.resize(800, 600)
    w.show()
    sys.exit(app.exec())



