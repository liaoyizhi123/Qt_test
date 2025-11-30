# import os
# import sys
# from datetime import datetime

# from PyQt6 import QtCore, QtWidgets
# from PyQt6.QtWidgets import (
#     QApplication,
#     QWidget,
#     QVBoxLayout,
#     QFormLayout,
#     QLabel,
#     QLineEdit,
#     QSpinBox,
#     QPushButton,
#     QMessageBox,
# )
# from PyQt6.QtGui import QShortcut, QKeySequence

# try:
#     from PyQt6.QtTextToSpeech import QTextToSpeech
# except ImportError:
#     QTextToSpeech = None


# class Page9Widget(QWidget):
#     """
#     睁眼/闭眼范式（Run 级设计）

#     更新时间记录逻辑（与 Page4/5/6/7/8 一致）：
#       - 点击“开始实验”后，如果 Page2 正在接收数据，则立刻调用 start_saving(run_dir)，
#         开始写四个 CSV；run_dir = data/eye/<Name>/<YYYYMMDDHHMMSS>/。
#       - 每个激活段（open1 / closed / open2）：
#           段开始：从 Page2 取一次“EEG 时间”（校准后的电脑时间，秒），记为 start_time
#           段结束：再次取一次“EEG 时间”，记为 end_time
#         这两个时间与 CSV 里的 Time 列在同一时间轴上，可直接用来对齐截取。
#       - txt 日志每一行的第 1/2 列为 start_time, end_time（秒）。

#     原始逻辑时间 logical_ms 仍在内部用于计算 duration，但不再写入文件。
#     """

#     def __init__(self, parent=None):
#         super().__init__(parent)
#         self.setWindowTitle("睁眼 / 闭眼 实验")
#         self.setMinimumSize(900, 700)

#         # ====== 数据目录结构：data/eye/<Name>/<timestamp> ======
#         self.data_root = "data"
#         self.eye_root = os.path.join(self.data_root, "eye")
#         os.makedirs(self.eye_root, exist_ok=True)

#         # 当前被试 & 本次实验 run 的目录信息
#         self.current_user_name: str | None = None
#         self.user_dir: str | None = None       # data/eye/<name>
#         self.run_dir: str | None = None        # data/eye/<name>/<timestamp>
#         self.run_timestamp: str | None = None  # YYYYMMDDHHMMSS

#         # ---------- 固定/默认参数 ----------
#         self.initial_countdown = 10  # 实验开始前倒计时（秒）
#         self.cue_open_pre = 3        # 每个 run 开始时“请睁眼”提示时长（秒）
#         self.end_cue_duration = 3    # 每个 run 的“采集结束”提示时长（秒）

#         self.default_open_duration = 10   # 默认 eye_open 激活期（秒）
#         self.default_closed_duration = 10 # 默认 eye_closed 激活期（秒）
#         self.default_rest_duration = 10   # 默认 run 间休息（秒）
#         self.default_runs = 5             # 默认 run 数量

#         # 条件标签
#         self.COND_OPEN = "eye_open"
#         self.COND_CLOSED = "eye_closed"

#         # ---------- 状态变量 ----------
#         self.name = ""
#         self.total_runs = self.default_runs
#         self.current_run = 0      # 从 0 开始计数
#         self.logical_ms = 0       # 逻辑时间：用于内部计算，不写文件
#         self.trial_logs = []      # 每个激活期一条记录

#         self.open_duration = self.default_open_duration
#         self.closed_duration = self.default_closed_duration
#         self.rest_duration = self.default_rest_duration

#         self._countdown_timer = None

#         # ===== 与 EEG 采集页面（Page2）联动 =====
#         # 在主程序中需要： page9.eeg_page = page2
#         self.eeg_page = None
#         # 整个实验的起止时间（与 CSV Time 同一“校准电脑时间轴”）
#         self.eeg_exp_start = None
#         self.eeg_exp_end = None

#         # ---------- 语音 ----------
#         self.tts = None
#         self._init_tts()

#         # ---------- UI ----------
#         root = QVBoxLayout(self)
#         root.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

#         # 说明
#         self.instruction = QLabel(
#             "填写信息后点击开始。\n"
#             "本范式在每个 Run 内按顺序采集：睁眼 → 闭眼 → 睁眼。\n"
#             "现在会在点击 Start 时自动调用 Page2 开始保存 EEG。"
#         )
#         f = self.instruction.font()
#         f.setPointSize(13)
#         self.instruction.setFont(f)
#         self.instruction.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
#         self.instruction.setWordWrap(True)
#         root.addWidget(self.instruction)

#         # 参数设置
#         settings = QWidget()
#         settings.setMaximumWidth(520)
#         form = QFormLayout(settings)
#         form.setFormAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

#         self.name_input = QLineEdit()
#         form.addRow("姓名:", self.name_input)

#         self.runs_spin = QSpinBox()
#         self.runs_spin.setRange(1, 999)
#         self.runs_spin.setValue(self.default_runs)
#         form.addRow("Runs 数（每个 Run: 开-闭-开）:", self.runs_spin)

#         self.open_spin = QSpinBox()
#         self.open_spin.setRange(1, 600)
#         self.open_spin.setValue(self.default_open_duration)
#         form.addRow("睁眼激活期时长 To (秒):", self.open_spin)

#         self.closed_spin = QSpinBox()
#         self.closed_spin.setRange(1, 600)
#         self.closed_spin.setValue(self.default_closed_duration)
#         form.addRow("闭眼激活期时长 Tc (秒):", self.closed_spin)

#         self.rest_spin = QSpinBox()
#         self.rest_spin.setRange(0, 600)
#         self.rest_spin.setValue(self.default_rest_duration)
#         form.addRow("Run 间休息 Tr (秒):", self.rest_spin)

#         root.addWidget(settings)
#         self.settings_widget = settings

#         # 开始按钮
#         self.start_btn = QPushButton("开始实验")
#         self.start_btn.clicked.connect(self.on_start_clicked)
#         root.addWidget(self.start_btn, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

#         # 大显示区
#         self.stage_label = QLabel("")
#         fs = self.stage_label.font()
#         fs.setPointSize(40)
#         self.stage_label.setFont(fs)
#         self.stage_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
#         self.stage_label.hide()
#         root.addWidget(self.stage_label)

#         # 倒计时显示
#         self.countdown_label = QLabel("")
#         fc = self.countdown_label.font()
#         fc.setPointSize(32)
#         self.countdown_label.setFont(fc)
#         self.countdown_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
#         self.countdown_label.hide()
#         root.addWidget(self.countdown_label)

#         # ESC 中断
#         self.esc_shortcut = QShortcut(QKeySequence(QtCore.Qt.Key.Key_Escape), self)
#         self.esc_shortcut.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
#         self.esc_shortcut.activated.connect(self.abort_and_finalize)

#     # ---------- 语音初始化 ----------

#     def _init_tts(self):
#         if QTextToSpeech is None:
#             return
#         try:
#             engines = QTextToSpeech.availableEngines()
#         except Exception:
#             return
#         if not engines:
#             return

#         # Windows 下优先使用 sapi 引擎
#         if sys.platform.startswith("win") and "sapi" in engines:
#             engine = "sapi"
#         else:
#             engine = engines[0]

#         try:
#             self.tts = QTextToSpeech(engine, self)
#             self.tts.setVolume(1.0)
#         except Exception:
#             self.tts = None

#     def _speak(self, text: str):
#         if self.tts is not None and text:
#             try:
#                 self.tts.say(text)
#             except Exception:
#                 pass

#     # ---------- 与 Page2 的时间交互（校准电脑时间） ----------

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

#     def _record_segment_start_time(self, idx: int):
#         """在某一激活段开始时调用，记录该段 start_time。"""
#         t = self._get_eeg_time_from_page()
#         if t is None:
#             return
#         if 0 <= idx < len(self.trial_logs):
#             self.trial_logs[idx]["start_time"] = t
#             if self.eeg_exp_start is None:
#                 self.eeg_exp_start = t

#     def _record_segment_end_time(self, idx: int):
#         """在某一激活段结束时调用，记录该段 end_time。"""
#         t = self._get_eeg_time_from_page()
#         if t is None:
#             return
#         if 0 <= idx < len(self.trial_logs):
#             self.trial_logs[idx]["end_time"] = t
#             self.eeg_exp_end = t

#     # ---------- 开始入口 ----------

#     def on_start_clicked(self):
#         name = self.name_input.text().strip()
#         if not name:
#             QMessageBox.warning(self, "错误", "请输入姓名！")
#             return

#         To = self.open_spin.value()
#         Tc = self.closed_spin.value()
#         Tr = self.rest_spin.value()
#         runs = self.runs_spin.value()

#         if To <= 0 or Tc <= 0:
#             QMessageBox.warning(self, "错误", "激活期时长必须大于 0 秒。")
#             return

#         # ===== 检查 EEG 采集页面状态 =====
#         eeg_page = getattr(self, "eeg_page", None)
#         if eeg_page is None or not hasattr(eeg_page, "is_listening"):
#             QMessageBox.warning(
#                 self, "错误",
#                 "未找到 EEG 采集页面，请在主程序中确保已创建并注入 Page2Widget。"
#             )
#             return

#         if not eeg_page.is_listening():
#             QMessageBox.warning(
#                 self,
#                 "提示",
#                 "请先在【首页】点击“开始监测信号”，\n"
#                 "确保已经开始接收EEG数据后，再启动本实验范式。"
#             )
#             return

#         self.name = name
#         self.open_duration = To
#         self.closed_duration = Tc
#         self.rest_duration = Tr
#         self.total_runs = runs

#         # ===== 构建目录：data/eye/<name>/<timestamp>/ =====
#         self.current_user_name = name
#         self.user_dir = os.path.join(self.eye_root, self.current_user_name)
#         os.makedirs(self.user_dir, exist_ok=True)

#         self.run_timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
#         self.run_dir = os.path.join(self.user_dir, self.run_timestamp)
#         os.makedirs(self.run_dir, exist_ok=True)

#         # 状态重置
#         self.current_run = 0
#         self.logical_ms = 0
#         self.trial_logs = []

#         # ===== 启动 EEG CSV 记录（从点击“开始实验”这一刻起） =====
#         self.eeg_exp_start = None
#         self.eeg_exp_end = None
#         try:
#             if hasattr(eeg_page, "start_saving"):
#                 eeg_page.start_saving(self.run_dir)
#         except Exception:
#             pass

#         first_time = self._get_eeg_time_from_page()
#         if first_time is not None:
#             self.eeg_exp_start = first_time

#         # UI 切换
#         self.instruction.hide()
#         self.start_btn.hide()
#         self.settings_widget.hide()

#         # 初始倒计时（此时 EEG 已经在记录）
#         self._show_fullscreen_message(
#             "{n}秒后将开始实验",
#             self.initial_countdown,
#             plain=True,
#             next_callback=self._after_initial_countdown,
#         )

#     def _after_initial_countdown(self):
#         # 初始倒计时结束，逻辑时间前进（仅内部使用）
#         self.logical_ms += self.initial_countdown * 1000
#         self._start_run()

#     # ---------- Run 流程 ----------

#     def _start_run(self):
#         if self.current_run >= self.total_runs:
#             # 所有 run 完成
#             self._finish_and_save()
#             return

#         # Run 起始：3s 提示“请睁眼”（不记日志）
#         cue = "请睁眼"
#         self._speak(cue)
#         self._show_fullscreen_message(
#             cue,
#             self.cue_open_pre,
#             bg="#ffec99",
#             fg="#000000",
#             plain=False,
#             next_callback=self._run_open1,
#         )

#     def _run_open1(self):
#         # 完成 3s 提示，逻辑时间推进
#         self.logical_ms += self.cue_open_pre * 1000

#         dur = self.open_duration
#         start_ms = self.logical_ms
#         end_ms = start_ms + dur * 1000

#         # 第一次睁眼激活期
#         self.trial_logs.append(
#             {
#                 "condition": self.COND_OPEN,
#                 "start_ms": start_ms,
#                 "end_ms": end_ms,
#                 "start_time": None,  # EEG 时间（秒）
#                 "end_time": None,
#                 "duration": dur,
#                 "run": self.current_run + 1,
#                 "segment": "open1",
#             }
#         )
#         idx = len(self.trial_logs) - 1
#         self._record_segment_start_time(idx)

#         self._apply_bg("#ffffff")
#         self._apply_fg("#000000")
#         self.stage_label.setText("睁眼数据采集中")
#         self.stage_label.show()
#         self.countdown_label.hide()

#         QtCore.QTimer.singleShot(dur * 1000, self._run_closed)

#     def _run_closed(self):
#         # open1 段结束时记录 end_time
#         if self.trial_logs:
#             self._record_segment_end_time(len(self.trial_logs) - 1)

#         # 第一次睁眼结束，逻辑时间推进
#         self.logical_ms = self.trial_logs[-1]["end_ms"]

#         dur = self.closed_duration
#         start_ms = self.logical_ms
#         end_ms = start_ms + dur * 1000

#         # 闭眼阶段
#         self.trial_logs.append(
#             {
#                 "condition": self.COND_CLOSED,
#                 "start_ms": start_ms,
#                 "end_ms": end_ms,
#                 "start_time": None,
#                 "end_time": None,
#                 "duration": dur,
#                 "run": self.current_run + 1,
#                 "segment": "closed",
#             }
#         )
#         idx = len(self.trial_logs) - 1
#         self._record_segment_start_time(idx)

#         txt = "闭眼数据采集中"
#         self._speak("请闭眼")
#         self._apply_bg("#ffffff")
#         self._apply_fg("#000000")
#         self.stage_label.setText(txt)
#         self.stage_label.show()
#         self.countdown_label.hide()

#         QtCore.QTimer.singleShot(dur * 1000, self._run_open2)

#     def _run_open2(self):
#         # closed 段结束时记录 end_time
#         if self.trial_logs:
#             self._record_segment_end_time(len(self.trial_logs) - 1)

#         # 闭眼结束
#         self.logical_ms = self.trial_logs[-1]["end_ms"]

#         dur = self.open_duration
#         start_ms = self.logical_ms
#         end_ms = start_ms + dur * 1000

#         # 第二次睁眼阶段
#         self.trial_logs.append(
#             {
#                 "condition": self.COND_OPEN,
#                 "start_ms": start_ms,
#                 "end_ms": end_ms,
#                 "start_time": None,
#                 "end_time": None,
#                 "duration": dur,
#                 "run": self.current_run + 1,
#                 "segment": "open2",
#             }
#         )
#         idx = len(self.trial_logs) - 1
#         self._record_segment_start_time(idx)

#         txt = "睁眼数据采集中"
#         self._speak("请睁眼")
#         self._apply_bg("#ffffff")
#         self._apply_fg("#000000")
#         self.stage_label.setText(txt)
#         self.stage_label.show()
#         self.countdown_label.hide()

#         QtCore.QTimer.singleShot(dur * 1000, self._run_end_cue)

#     def _run_end_cue(self):
#         # 第二次睁眼结束时记录 end_time
#         if self.trial_logs:
#             self._record_segment_end_time(len(self.trial_logs) - 1)

#         # 第二次睁眼结束，逻辑时间推进
#         self.logical_ms = self.trial_logs[-1]["end_ms"]

#         # 3s “采集结束”提示（不记日志）
#         txt = "采集结束"
#         self._speak(txt)
#         self._show_fullscreen_message(
#             txt,
#             self.end_cue_duration,
#             bg="#e6ffea",
#             fg="#000000",
#             plain=False,
#             next_callback=self._after_run_end_cue,
#         )

#     def _after_run_end_cue(self):
#         # 结束提示计入时间
#         self.logical_ms += self.end_cue_duration * 1000
#         self.current_run += 1

#         # 最后一个 run：不休息，直接结束
#         if self.current_run >= self.total_runs:
#             self._finish_and_save()
#             return

#         # 其他 run：休息 Tr 秒（不记日志）
#         if self.rest_duration > 0:
#             self._show_fullscreen_message(
#                 "请休息，{n}秒后开始下一次实验",
#                 self.rest_duration,
#                 bg="#dddddd",
#                 fg="#000000",
#                 plain=False,
#                 next_callback=self._after_rest,
#             )
#         else:
#             # 没有休息，直接下一个 run
#             self._start_run()

#     def _after_rest(self):
#         self.logical_ms += self.rest_duration * 1000
#         self._start_run()

#     # ---------- 全屏消息 & 倒计时 ----------

#     def _show_fullscreen_message(
#         self,
#         template_or_text: str,
#         seconds: int,
#         bg: str | None = None,
#         fg: str | None = None,
#         plain: bool = False,
#         next_callback=None,
#     ):
#         if plain:
#             self._clear_styles()
#         else:
#             if bg is not None:
#                 self._apply_bg(bg)
#             if fg is not None:
#                 self._apply_fg(fg)

#         self.stage_label.hide()
#         self.countdown_label.show()

#         self._countdown_value = int(seconds)
#         self._countdown_template = template_or_text

#         # 初始显示
#         if "{n}" in template_or_text:
#             txt = template_or_text.format(n=self._countdown_value)
#         else:
#             txt = template_or_text
#         self.countdown_label.setText(txt)

#         # 清理旧 timer
#         if self._countdown_timer is not None:
#             self._countdown_timer.stop()
#             self._countdown_timer.deleteLater()
#             self._countdown_timer = None

#         self._countdown_timer = QtCore.QTimer(self)
#         self._countdown_timer.timeout.connect(lambda: self._tick(next_callback))
#         self._countdown_timer.start(1000)

#     def _tick(self, next_callback):
#         self._countdown_value -= 1
#         if self._countdown_value > 0:
#             if "{n}" in self._countdown_template:
#                 txt = self._countdown_template.format(n=self._countdown_value)
#             else:
#                 txt = self._countdown_template
#             self.countdown_label.setText(txt)
#         else:
#             if self._countdown_timer is not None:
#                 self._countdown_timer.stop()
#                 self._countdown_timer.deleteLater()
#                 self._countdown_timer = None
#             self.countdown_label.hide()
#             if callable(next_callback):
#                 next_callback()

#     # ---------- 样式 ----------

#     def _apply_bg(self, color: str):
#         self.setStyleSheet(f"background-color:{color};")

#     def _apply_fg(self, color: str):
#         self.stage_label.setStyleSheet(f"color:{color};")
#         self.countdown_label.setStyleSheet(f"color:{color};")

#     def _clear_styles(self):
#         self.setStyleSheet("")
#         self.stage_label.setStyleSheet("")
#         self.countdown_label.setStyleSheet("")

#     # ---------- 结束 & 中断 ----------

#     def _finish_and_save(self):
#         """
#         所有 run 完成后调用：
#           - 尝试停止 EEG 保存
#           - 写入日志
#           - 重置 UI
#         """
#         eeg_page = getattr(self, "eeg_page", None)
#         if eeg_page is not None:
#             last_t = self._get_eeg_time_from_page()
#             if last_t is not None:
#                 self.eeg_exp_end = last_t
#             if hasattr(eeg_page, "stop_saving"):
#                 try:
#                     eeg_page.stop_saving()
#                 except Exception:
#                     pass

#         self._save_report()
#         self._reset_ui()

#     def abort_and_finalize(self):
#         """
#         ESC 中断：
#           - 尝试停止 EEG 保存
#           - 写 ABORT 日志
#         """
#         eeg_page = getattr(self, "eeg_page", None)
#         if eeg_page is not None:
#             last_t = self._get_eeg_time_from_page()
#             if last_t is not None:
#                 self.eeg_exp_end = last_t
#             if hasattr(eeg_page, "stop_saving"):
#                 try:
#                     eeg_page.stop_saving()
#                 except Exception:
#                     pass

#         self._save_report(aborted=True)
#         self._reset_ui()

#     def _save_report(self, aborted: bool = False):
#         """
#         每一行：
#           start_time,end_time,condition,duration=秒,run=idx,segment=标记

#         其中 start_time / end_time 为 EEG 时间（秒，float），
#         与 EEG CSV 的 Time 列在同一校准时间轴上；
#         若当时未能获取则为 NaN。

#         报告文件保存到：
#           data/eye/<Name>/<YYYYMMDDHHMMSS>/EyeOpenClose_*.txt
#         """
#         if not self.trial_logs:
#             return

#         flag = "ABORT" if aborted else "DONE"

#         # 用于文件名的被试名
#         name = (
#             self.current_user_name
#             or self.name
#             or self.name_input.text().strip()
#             or "unknown"
#         )

#         # 用于保存的目录：优先 run_dir，其次 user_dir，再次 eye_root
#         base_dir = self.run_dir or self.user_dir or self.eye_root
#         os.makedirs(base_dir, exist_ok=True)

#         # 文件名中的时间戳：优先 run_timestamp，兜底当前时间
#         ts_for_name = self.run_timestamp or datetime.now().strftime("%Y%m%d%H%M%S")

#         fname = os.path.join(
#             base_dir,
#             f"EyeOpenClose_{name}_{ts_for_name}_runs{self.total_runs}_{flag}.txt",
#         )

#         try:
#             with open(fname, "w", encoding="utf-8") as f:
#                 for rec in self.trial_logs:
#                     start_t = rec.get("start_time")
#                     end_t = rec.get("end_time")

#                     if isinstance(start_t, (int, float)):
#                         t0 = float(start_t)
#                     else:
#                         t0 = float("nan")

#                     if isinstance(end_t, (int, float)):
#                         t1 = float(end_t)
#                     else:
#                         t1 = float("nan")

#                     cond = rec["condition"]
#                     dur = rec["duration"]
#                     run = rec.get("run", "")
#                     seg = rec.get("segment", "")
#                     f.write(
#                         f"{t0:.6f},{t1:.6f},{cond},"
#                         f"duration={dur},run={run},segment={seg}\n"
#                     )
#         except Exception as e:
#             QMessageBox.critical(self, "保存失败", f"写入日志失败：{e}")

#     def _reset_ui(self):
#         if self._countdown_timer is not None:
#             self._countdown_timer.stop()
#             self._countdown_timer.deleteLater()
#             self._countdown_timer = None

#         self._clear_styles()
#         self.stage_label.hide()
#         self.countdown_label.hide()

#         # 恢复配置区
#         self.name_input.clear()
#         self.instruction.show()
#         self.start_btn.show()
#         self.settings_widget.show()
#         self.name_input.setFocus()

#         # 状态复位
#         self.current_run = 0
#         self.logical_ms = 0
#         self.trial_logs = []

#         # 目录 & 时间信息复位
#         self.current_user_name = None
#         self.user_dir = None
#         self.run_dir = None
#         self.run_timestamp = None
#         self.name = ""
#         self.eeg_exp_start = None
#         self.eeg_exp_end = None


# if __name__ == "__main__":
#     app = QApplication(sys.argv)
#     w = Page9Widget()
#     w.show()
#     sys.exit(app.exec())

import os
import sys
import json
from datetime import datetime

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QPushButton,
    QMessageBox,
)
from PyQt6.QtGui import QShortcut, QKeySequence

try:
    from PyQt6.QtTextToSpeech import QTextToSpeech
except ImportError:
    QTextToSpeech = None


class Page9Widget(QWidget):
    """
    睁眼/闭眼范式（Run 级设计）

    与 Page7 一致的记录方式：
    - Page9 只负责打 trigger，不再直接用 get_last_eeg_time。
    - Page2 写 EEG_xxx.csv + triggers.csv。
    - 实验结束后，Page9 读取 triggers.csv，对齐每个激活段的 start/end，
      并生成 txt + meta.json。

    trigger 定义：
      0: baseline（由 Page2 在无事件时写 0）
      1: eye_open_start
      2: eye_open_end
      3: eye_closed_start
      4: eye_closed_end
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("睁眼 / 闭眼 实验")
        self.setMinimumSize(900, 700)

        # ===== trigger code 定义 =====
        self.TRIG_EYE_OPEN_START = 1
        self.TRIG_EYE_OPEN_END = 2
        self.TRIG_EYE_CLOSED_START = 3
        self.TRIG_EYE_CLOSED_END = 4

        # ===== 数据目录结构：data/eye/<Name>/<timestamp> =====
        self.data_root = "data"
        self.eye_root = os.path.join(self.data_root, "eye")
        os.makedirs(self.eye_root, exist_ok=True)

        # 当前被试 & 本次实验 run 的目录信息
        self.current_user_name: str | None = None
        self.user_dir: str | None = None  # data/eye/<name>
        self.run_dir: str | None = None  # data/eye/<name>/<timestamp>
        self.run_timestamp: str | None = None  # YYYYMMDDHHMMSS

        # ---------- 固定/默认参数 ----------
        self.initial_countdown = 10  # 实验开始前倒计时（秒）
        self.cue_open_pre = 3  # 每个 run 开始时“请睁眼”提示时长（秒）
        self.end_cue_duration = 3  # 每个 run 的“采集结束”提示时长（秒）

        self.default_open_duration = 10  # 默认 eye_open 激活期（秒）
        self.default_closed_duration = 10  # 默认 eye_closed 激活期（秒）
        self.default_rest_duration = 10  # 默认 run 间休息（秒）
        self.default_runs = 5  # 默认 run 数量

        # 条件标签
        self.COND_OPEN = "eye_open"
        self.COND_CLOSED = "eye_closed"

        # ---------- 状态变量 ----------
        self.name = ""
        self.total_runs = self.default_runs
        self.current_run = 0  # 从 0 开始计数
        self.logical_ms = 0  # 内部逻辑时间：用于时序安排，不写文件
        self.trial_logs: list[dict] = []  # 每个激活段一条记录（open1 / closed / open2）

        self.open_duration = self.default_open_duration
        self.closed_duration = self.default_closed_duration
        self.rest_duration = self.default_rest_duration

        self._countdown_timer: QtCore.QTimer | None = None

        # ===== 与 EEG 采集页面（Page2）联动 =====
        # 在主程序中需要： page9.eeg_page = page2
        self.eeg_page = None
        self.eeg_exp_start: float | None = None
        self.eeg_exp_end: float | None = None

        # ---------- 语音 ----------
        self.tts: QTextToSpeech | None = None
        self._init_tts()

        # ---------- UI ----------
        root = QVBoxLayout(self)
        root.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        # 说明
        self.instruction = QLabel(
            "填写信息后点击开始。\n"
            "本范式在每个 Run 内按顺序采集：睁眼 → 闭眼 → 睁眼。\n"
            "点击 Start 后将自动调用 Page2 开始保存 EEG + triggers.csv。"
        )
        f = self.instruction.font()
        f.setPointSize(13)
        self.instruction.setFont(f)
        self.instruction.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.instruction.setWordWrap(True)
        root.addWidget(self.instruction)

        # 参数设置
        settings = QWidget()
        settings.setMaximumWidth(520)
        form = QFormLayout(settings)
        form.setFormAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        self.name_input = QLineEdit()
        form.addRow("姓名:", self.name_input)

        self.runs_spin = QSpinBox()
        self.runs_spin.setRange(1, 999)
        self.runs_spin.setValue(self.default_runs)
        form.addRow("Runs 数（每个 Run: 开-闭-开）:", self.runs_spin)

        self.open_spin = QSpinBox()
        self.open_spin.setRange(1, 600)
        self.open_spin.setValue(self.default_open_duration)
        form.addRow("睁眼激活期时长 To (秒):", self.open_spin)

        self.closed_spin = QSpinBox()
        self.closed_spin.setRange(1, 600)
        self.closed_spin.setValue(self.default_closed_duration)
        form.addRow("闭眼激活期时长 Tc (秒):", self.closed_spin)

        self.rest_spin = QSpinBox()
        self.rest_spin.setRange(0, 600)
        self.rest_spin.setValue(self.default_rest_duration)
        form.addRow("Run 间休息 Tr (秒):", self.rest_spin)

        root.addWidget(settings)
        self.settings_widget = settings

        # 开始按钮
        self.start_btn = QPushButton("开始实验")
        self.start_btn.clicked.connect(self.on_start_clicked)
        root.addWidget(self.start_btn, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        # 大显示区
        self.stage_label = QLabel("")
        fs = self.stage_label.font()
        fs.setPointSize(40)
        self.stage_label.setFont(fs)
        self.stage_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.stage_label.hide()
        root.addWidget(self.stage_label)

        # 倒计时显示
        self.countdown_label = QLabel("")
        fc = self.countdown_label.font()
        fc.setPointSize(32)
        self.countdown_label.setFont(fc)
        self.countdown_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.countdown_label.hide()
        root.addWidget(self.countdown_label)

        # ESC 中断
        self.esc_shortcut = QShortcut(QKeySequence(QtCore.Qt.Key.Key_Escape), self)
        self.esc_shortcut.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
        self.esc_shortcut.activated.connect(self.abort_and_finalize)

    # ---------- 语音初始化 ----------

    def _init_tts(self):
        if QTextToSpeech is None:
            return
        try:
            engines = QTextToSpeech.availableEngines()
        except Exception:
            return
        if not engines:
            return

        # Windows 下优先使用 sapi 引擎
        if sys.platform.startswith("win") and "sapi" in engines:
            engine = "sapi"
        else:
            engine = engines[0]

        try:
            self.tts = QTextToSpeech(engine, self)
            self.tts.setVolume(1.0)
        except Exception:
            self.tts = None

    def _speak(self, text: str):
        if self.tts is not None and text:
            try:
                self.tts.say(text)
            except Exception:
                pass

    # ---------- 向 Page2 发送 trigger ----------

    def _send_trigger(self, code: int):
        """
        将 trigger 发送给 Page2。
        Page2 会在 ch0 的下一采样点把该 trigger 写入 triggers.csv。
        """
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

    # ---------- 开始入口 ----------

    def on_start_clicked(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "错误", "请输入姓名！")
            return

        To = self.open_spin.value()
        Tc = self.closed_spin.value()
        Tr = self.rest_spin.value()
        runs = self.runs_spin.value()

        if To <= 0 or Tc <= 0:
            QMessageBox.warning(self, "错误", "激活期时长必须大于 0 秒。")
            return

        # ===== 检查 EEG 采集页面状态 =====
        eeg_page = getattr(self, "eeg_page", None)
        if eeg_page is None or not hasattr(eeg_page, "is_listening"):
            QMessageBox.warning(self, "错误", "未找到 EEG 采集页面，请在主程序中确保已创建并注入 Page2Widget。")
            return

        if not eeg_page.is_listening():
            QMessageBox.warning(
                self, "提示", "请先在【首页】点击“开始监测信号”，\n" "确保已经开始接收EEG数据后，再启动本实验范式。"
            )
            return

        self.name = name
        self.open_duration = To
        self.closed_duration = Tc
        self.rest_duration = Tr
        self.total_runs = runs

        # ===== 构建目录：data/eye/<name>/<timestamp>/ =====
        self.current_user_name = name
        self.user_dir = os.path.join(self.eye_root, self.current_user_name)
        os.makedirs(self.user_dir, exist_ok=True)

        self.run_timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        self.run_dir = os.path.join(self.user_dir, self.run_timestamp)
        os.makedirs(self.run_dir, exist_ok=True)

        # 状态重置
        self.current_run = 0
        self.logical_ms = 0
        self.trial_logs = []

        # ===== 启动 EEG CSV + triggers.csv 记录 =====
        self.eeg_exp_start = None
        self.eeg_exp_end = None
        try:
            if hasattr(eeg_page, "start_saving"):
                eeg_page.start_saving(self.run_dir)
        except Exception:
            pass

        # UI 切换
        self.instruction.hide()
        self.start_btn.hide()
        self.settings_widget.hide()

        # 初始倒计时（此时 EEG 已经在记录）
        self._show_fullscreen_message(
            "{n}秒后将开始实验",
            self.initial_countdown,
            plain=True,
            next_callback=self._after_initial_countdown,
        )

    def _after_initial_countdown(self):
        # 初始倒计时结束，逻辑时间前进（仅内部使用）
        self.logical_ms += self.initial_countdown * 1000
        self._start_run()

    # ---------- Run 流程 ----------

    def _start_run(self):
        if self.current_run >= self.total_runs:
            # 所有 run 完成
            self._finish_and_save()
            return

        # Run 起始：3s 提示“请睁眼”（不记入 trial_logs）
        cue = "请睁眼"
        self._speak(cue)
        self._show_fullscreen_message(
            cue,
            self.cue_open_pre,
            bg="#ffec99",
            fg="#000000",
            plain=False,
            next_callback=self._run_open1,
        )

    def _run_open1(self):
        # 完成 3s 提示，逻辑时间推进
        self.logical_ms += self.cue_open_pre * 1000

        dur = self.open_duration
        start_ms = self.logical_ms
        end_ms = start_ms + dur * 1000

        # 第一次睁眼激活期（open1）
        self.trial_logs.append(
            {
                "condition": self.COND_OPEN,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "start_time": None,  # 最终从 triggers.csv 解析后填充
                "end_time": None,
                "duration": float(dur),
                "run": self.current_run + 1,
                "segment": "open1",
            }
        )
        # 段开始 trigger：eye_open_start
        self._send_trigger(self.TRIG_EYE_OPEN_START)

        self._apply_bg("#ffffff")
        self._apply_fg("#000000")
        self.stage_label.setText("睁眼数据采集中")
        self.stage_label.show()
        self.countdown_label.hide()

        QtCore.QTimer.singleShot(dur * 1000, self._run_closed)

    def _run_closed(self):
        # open1 段逻辑结束：eye_open_end
        self._send_trigger(self.TRIG_EYE_OPEN_END)

        # open1 结束，逻辑时间推进
        self.logical_ms = self.trial_logs[-1]["end_ms"]

        dur = self.closed_duration
        start_ms = self.logical_ms
        end_ms = start_ms + dur * 1000

        # 闭眼阶段（closed）
        self.trial_logs.append(
            {
                "condition": self.COND_CLOSED,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "start_time": None,
                "end_time": None,
                "duration": float(dur),
                "run": self.current_run + 1,
                "segment": "closed",
            }
        )
        # 段开始 trigger：eye_closed_start
        self._send_trigger(self.TRIG_EYE_CLOSED_START)

        txt = "闭眼数据采集中"
        self._speak("请闭眼")
        self._apply_bg("#ffffff")
        self._apply_fg("#000000")
        self.stage_label.setText(txt)
        self.stage_label.show()
        self.countdown_label.hide()

        QtCore.QTimer.singleShot(dur * 1000, self._run_open2)

    def _run_open2(self):
        # closed 段逻辑结束：eye_closed_end
        self._send_trigger(self.TRIG_EYE_CLOSED_END)

        # 闭眼结束，逻辑时间推进
        self.logical_ms = self.trial_logs[-1]["end_ms"]

        dur = self.open_duration
        start_ms = self.logical_ms
        end_ms = start_ms + dur * 1000

        # 第二次睁眼阶段（open2）
        self.trial_logs.append(
            {
                "condition": self.COND_OPEN,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "start_time": None,
                "end_time": None,
                "duration": float(dur),
                "run": self.current_run + 1,
                "segment": "open2",
            }
        )
        # 段开始 trigger：eye_open_start
        self._send_trigger(self.TRIG_EYE_OPEN_START)

        txt = "睁眼数据采集中"
        self._speak("请睁眼")
        self._apply_bg("#ffffff")
        self._apply_fg("#000000")
        self.stage_label.setText(txt)
        self.stage_label.show()
        self.countdown_label.hide()

        QtCore.QTimer.singleShot(dur * 1000, self._run_end_cue)

    def _run_end_cue(self):
        # 第二次睁眼结束：eye_open_end
        self._send_trigger(self.TRIG_EYE_OPEN_END)

        # 第二次睁眼逻辑结束，时间推进
        self.logical_ms = self.trial_logs[-1]["end_ms"]

        # 3s “采集结束”提示（不记日志）
        txt = "采集结束"
        self._speak(txt)
        self._show_fullscreen_message(
            txt,
            self.end_cue_duration,
            bg="#e6ffea",
            fg="#000000",
            plain=False,
            next_callback=self._after_run_end_cue,
        )

    def _after_run_end_cue(self):
        # 结束提示计入时间
        self.logical_ms += self.end_cue_duration * 1000
        self.current_run += 1

        # 最后一个 run：不休息，直接结束
        if self.current_run >= self.total_runs:
            self._finish_and_save()
            return

        # 其他 run：休息 Tr 秒（不记日志）
        if self.rest_duration > 0:
            self._show_fullscreen_message(
                "请休息，{n}秒后开始下一次实验",
                self.rest_duration,
                bg="#dddddd",
                fg="#000000",
                plain=False,
                next_callback=self._after_rest,
            )
        else:
            # 没有休息，直接下一个 run
            self._start_run()

    def _after_rest(self):
        self.logical_ms += self.rest_duration * 1000
        self._start_run()

    # ---------- 全屏消息 & 倒计时 ----------

    def _show_fullscreen_message(
        self,
        template_or_text: str,
        seconds: int,
        bg: str | None = None,
        fg: str | None = None,
        plain: bool = False,
        next_callback=None,
    ):
        if plain:
            self._clear_styles()
        else:
            if bg is not None:
                self._apply_bg(bg)
            if fg is not None:
                self._apply_fg(fg)

        self.stage_label.hide()
        self.countdown_label.show()

        self._countdown_value = int(seconds)
        self._countdown_template = template_or_text

        # 初始显示
        if "{n}" in template_or_text:
            txt = template_or_text.format(n=self._countdown_value)
        else:
            txt = template_or_text
        self.countdown_label.setText(txt)

        # 清理旧 timer
        if self._countdown_timer is not None:
            self._countdown_timer.stop()
            self._countdown_timer.deleteLater()
            self._countdown_timer = None

        self._countdown_timer = QtCore.QTimer(self)
        self._countdown_timer.timeout.connect(lambda: self._tick(next_callback))
        self._countdown_timer.start(1000)

    def _tick(self, next_callback):
        self._countdown_value -= 1
        if self._countdown_value > 0:
            if "{n}" in self._countdown_template:
                txt = self._countdown_template.format(n=self._countdown_value)
            else:
                txt = self._countdown_template
            self.countdown_label.setText(txt)
        else:
            if self._countdown_timer is not None:
                self._countdown_timer.stop()
                self._countdown_timer.deleteLater()
                self._countdown_timer = None
            self.countdown_label.hide()
            if callable(next_callback):
                next_callback()

    # ---------- 样式 ----------

    def _apply_bg(self, color: str):
        self.setStyleSheet(f"background-color:{color};")

    def _apply_fg(self, color: str):
        self.stage_label.setStyleSheet(f"color:{color};")
        self.countdown_label.setStyleSheet(f"color:{color};")

    def _clear_styles(self):
        self.setStyleSheet("")
        self.stage_label.setStyleSheet("")
        self.countdown_label.setStyleSheet("")

    # ---------- 从 triggers.csv 解析各段时间 ----------

    def _parse_segments_from_triggers(self) -> list[dict]:
        """
        从 <run_dir>/triggers.csv 中解析出段列表：
          [{"start": t0, "end": t1}, ...]
        只关心 trigger == 1/3 (start) 或 2/4 (end)，
        按时间排序后一一配对。
        """
        segments: list[dict] = []

        base_dir = self.run_dir or self.user_dir or self.eye_root
        triggers_path = os.path.join(base_dir, "triggers.csv")
        if not os.path.exists(triggers_path):
            return segments

        events: list[tuple[float, int]] = []
        try:
            with open(triggers_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception:
            return segments

        start_codes = {self.TRIG_EYE_OPEN_START, self.TRIG_EYE_CLOSED_START}
        end_codes = {self.TRIG_EYE_OPEN_END, self.TRIG_EYE_CLOSED_END}

        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split(",")
            if len(parts) < 2:
                continue
            try:
                t = float(parts[0])
                code = int(float(parts[1]))
            except Exception:
                continue
            if code in start_codes or code in end_codes:
                events.append((t, code))

        events.sort(key=lambda x: x[0])

        current_start: float | None = None
        for t, code in events:
            if code in start_codes:
                # 如果之前有未闭合的 start，简单覆盖
                current_start = t
            elif code in end_codes and current_start is not None:
                segments.append({"start": current_start, "end": t})
                current_start = None

        if segments:
            self.eeg_exp_start = segments[0]["start"]
            self.eeg_exp_end = segments[-1]["end"]

        return segments

    # ---------- 结束 & 中断 ----------

    def _finish_and_save(self):
        """
        所有 run 完成后调用：
          - 停止 EEG 保存
          - 从 triggers.csv 解析时间并写入 txt + meta.json
          - 重置 UI
        """
        eeg_page = getattr(self, "eeg_page", None)
        if eeg_page is not None and hasattr(eeg_page, "stop_saving"):
            try:
                eeg_page.stop_saving()
            except Exception:
                pass

        self._write_report(aborted=False)
        self._reset_ui()

    def abort_and_finalize(self):
        """
        ESC 中断：
          - 停止 EEG 保存
          - 写 ABORT 日志（依然基于 triggers.csv）
        """
        eeg_page = getattr(self, "eeg_page", None)
        if eeg_page is not None and hasattr(eeg_page, "stop_saving"):
            try:
                eeg_page.stop_saving()
            except Exception:
                pass

        self._write_report(aborted=True)
        self._reset_ui()

    # ---------- 报告写入（txt + meta.json） ----------

    def _write_report(self, aborted: bool = False):
        """
        1) 从 triggers.csv 解析每个激活段(start, end)时间；
        2) 按段顺序写入 self.trial_logs[start_time/end_time]；
        3) 写 txt：
             start_time,end_time,condition,duration=..,run=..,segment=..
        4) 写 meta.json。
        """
        if not self.trial_logs:
            return

        flag = "ABORT" if aborted else "DONE"

        # 用于文件名的被试名
        name = self.current_user_name or self.name or self.name_input.text().strip() or "unknown"

        # 解析 triggers.csv 得到 segments
        segments = self._parse_segments_from_triggers()
        seg_count = len(segments)
        log_count = len(self.trial_logs)
        n_assign = min(seg_count, log_count)

        # 将 segments 的时间按顺序写入 trial_logs
        for i in range(n_assign):
            s = segments[i]["start"]
            e = segments[i]["end"]
            self.trial_logs[i]["start_time"] = s
            self.trial_logs[i]["end_time"] = e

        # 目录和时间戳
        base_dir = self.run_dir or self.user_dir or self.eye_root
        os.makedirs(base_dir, exist_ok=True)

        ts_for_name = self.run_timestamp or datetime.now().strftime("%Y%m%d%H%M%S")

        # ---- 写 txt 报告 ----
        txt_path = os.path.join(
            base_dir,
            f"EyeOpenClose_{name}_{ts_for_name}_runs{self.total_runs}_{flag}.txt",
        )

        try:
            with open(txt_path, "w", encoding="utf-8") as f:
                for rec in self.trial_logs:
                    start_t = rec.get("start_time")
                    end_t = rec.get("end_time")

                    if isinstance(start_t, (int, float)):
                        t0 = float(start_t)
                    else:
                        t0 = float("nan")

                    if isinstance(end_t, (int, float)):
                        t1 = float(end_t)
                    else:
                        t1 = float("nan")

                    cond = rec["condition"]
                    dur = rec["duration"]
                    run = rec.get("run", "")
                    seg = rec.get("segment", "")
                    f.write(f"{t0:.6f},{t1:.6f},{cond}," f"duration={dur},run={run},segment={seg}\n")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"写入 txt 日志失败：{e}")
            # 即使 txt 失败，也继续尝试写 meta.json

        # ---- 写 meta.json ----
        timing = {
            "initial_countdown": int(self.initial_countdown),
            "cue_open_pre": int(self.cue_open_pre),
            "end_cue_duration": int(self.end_cue_duration),
            "open_duration": float(self.open_duration),
            "closed_duration": float(self.closed_duration),
            "rest_duration": float(self.rest_duration),
        }

        trigger_code_labels = {
            "0": "baseline",
            str(self.TRIG_EYE_OPEN_START): "eye_open_start",
            str(self.TRIG_EYE_OPEN_END): "eye_open_end",
            str(self.TRIG_EYE_CLOSED_START): "eye_closed_start",
            str(self.TRIG_EYE_CLOSED_END): "eye_closed_end",
        }

        meta_trials: list[dict] = []
        for idx, rec in enumerate(self.trial_logs, start=1):
            st = rec.get("start_time")
            et = rec.get("end_time")
            if isinstance(st, (int, float)):
                st_val: float | None = float(st)
            else:
                st_val = None
            if isinstance(et, (int, float)):
                et_val: float | None = float(et)
            else:
                et_val = None

            meta_trials.append(
                {
                    "trial_index": idx,
                    "condition": rec.get("condition"),
                    "run": rec.get("run"),
                    "segment": rec.get("segment"),
                    "duration": float(rec.get("duration", 0.0)),
                    "start_time": st_val,
                    "end_time": et_val,
                }
            )

        meta = {
            "subject_name": name,
            "timing": timing,
            "trigger_code_labels": trigger_code_labels,
            "trials": meta_trials,
        }

        meta_path = os.path.join(
            base_dir,
            f"EyeOpenClose_{name}_{ts_for_name}_meta.json",
        )

        try:
            with open(meta_path, "w", encoding="utf-8") as f_meta:
                json.dump(meta, f_meta, ensure_ascii=False, indent=2)
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"写入 meta.json 失败：{e}")

    # ---------- UI 重置 ----------

    def _reset_ui(self):
        if self._countdown_timer is not None:
            self._countdown_timer.stop()
            self._countdown_timer.deleteLater()
            self._countdown_timer = None

        self._clear_styles()
        self.stage_label.hide()
        self.countdown_label.hide()

        # 恢复配置区
        self.name_input.clear()
        self.instruction.show()
        self.start_btn.show()
        self.settings_widget.show()
        self.name_input.setFocus()

        # 状态复位
        self.current_run = 0
        self.logical_ms = 0
        self.trial_logs = []

        # 目录 & 时间信息复位
        self.current_user_name = None
        self.user_dir = None
        self.run_dir = None
        self.run_timestamp = None
        self.name = ""
        self.eeg_exp_start = None
        self.eeg_exp_end = None


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = Page9Widget()
    w.show()
    sys.exit(app.exec())
