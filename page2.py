import os
import enum
import re
import socket
import threading
import time
import queue
import struct
import logging
from collections import deque
from dataclasses import dataclass
from typing import List, Optional

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout
import pyqtgraph as pg


# ====================== 状态枚举 ======================


class LabelStates(enum.Enum):
    # 未监听：初始化 / 停止后的状态
    stopped = "未监听（请填写端口号后点击开始）"
    # 已开启UDP监听，但还没有收到数据
    listening = "已开启UDP监听，但还没有收到数据"
    # 已经收到数据，正在实时接收并绘图
    receiving = "正在接收EEG数据..."


class ButtonStates(enum.Enum):
    start = "开始检测信号"
    stop = "停止检测信号"


# ====================== IP / 端口 / 采样率 校验 ======================


def is_valid_ip(ip: str) -> bool:
    IP_REGEX = r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$"
    if not re.match(IP_REGEX, ip):
        return False
    segments = ip.split(".")
    for segment in segments:
        if not 0 <= int(segment) <= 255:
            return False
    return True


def is_valid_port(port: str) -> bool:
    return port.isdigit() and 1 <= int(port) <= 65535


def is_valid_sample_rate(fs: str) -> bool:
    """采样率校验：>0 的数字即可（一般是整数）"""
    try:
        v = float(fs)
        return v > 0
    except ValueError:
        return False


# ====================== EEG 数据结构 & UDP 接收器 ======================


@dataclass
class EegDataPacket:
    """EEG数据包结构"""

    hardware_timestamp: float  # 来自EEG硬件的时间戳（秒）
    system_timestamp: float  # 系统接收到的时间戳（秒）
    data: List[float]  # 解析后的微伏值数据列表
    packet_id: int = 0  # 数据包ID，用于跟踪
    channel: int = 0  # 通道号
    raw_packet: bytes | None = None  # 原始数据包用于调试


class UdpEegReceiver(QObject):
    """
    UDP EEG数据接收器 - PyQt6版本
    负责接收来自硬件的数据包，并提供时间戳同步功能
    使用信号槽机制与 UI 交互
    """

    # PyQt6信号定义
    data_received = pyqtSignal(object)  # 发出 EegDataPacket 实例
    error_occurred = pyqtSignal(str)  # 错误发生
    sync_established = pyqtSignal(float)  # 时间同步建立，传递偏移量

    def __init__(
        self, host: str = "0.0.0.0", port: int = 30300, buffer_size: int = 8192, parent: Optional[QObject] = None
    ):
        """
        初始化UDP接收器
        """
        super().__init__(parent)
        self.host = host
        self.port = port
        self.buffer_size = buffer_size
        self.socket: Optional[socket.socket] = None
        self.running = False
        self.data_queue: queue.Queue[EegDataPacket] = queue.Queue()
        self.sync_offset = 0.0
        self.synced = False
        self.packet_count = 0
        self.active_channels = set()
        self.logger = logging.getLogger("UdpEegReceiver")

        self._recv_count = 0
        self._last_stat_time = time.time()
        self.receiver_thread: Optional[threading.Thread] = None

        self._last_hw_timestamp: Optional[float] = None

    def get_last_hw_timestamp(self) -> Optional[float]:
        """返回最近一次接收到的数据包的片上时间戳（秒）。如果还没有收到任何数据则返回 None。"""
        return self._last_hw_timestamp

    def is_running(self) -> bool:
        """当前 UDP 接收线程是否在运行。"""
        return self.running

    # -------- 启动 / 停止 --------

    def start(self):
        """启动UDP接收器"""
        if self.running:
            self.logger.warning("接收器已经在运行中")
            return

        try:
            self.running = True
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

            # 尝试增大接收缓冲区
            try:
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2 * 1024 * 1024)
                actual_buffer = self.socket.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
                self.logger.info(f"Socket接收缓冲区大小: {actual_buffer} 字节")
            except Exception as e:
                self.logger.warning(f"设置socket缓冲区失败: {e}")

            self.socket.bind((self.host, self.port))
            self.socket.settimeout(0.1)  # 100ms 超时，方便干净关闭

            self._recv_count = 0
            self._last_stat_time = time.time()

            self.receiver_thread = threading.Thread(
                target=self._receive_loop,
                daemon=True,
                name="UDP-Receiver-Thread",
            )
            self.receiver_thread.start()

            self.logger.info(f"UDP接收器已启动，监听 {self.host}:{self.port}")

        except Exception as e:
            self.running = False
            self.logger.error(f"启动UDP接收器失败: {e}")
            self.error_occurred.emit(f"启动UDP接收器失败: {e}")
            raise

    def stop(self):
        """停止UDP接收器"""
        if not self.running:
            return

        self.running = False
        if self.socket:
            self.socket.close()
            self.socket = None

        if self.receiver_thread and self.receiver_thread.is_alive():
            self.receiver_thread.join(timeout=2.0)

        self.logger.info("UDP接收器已停止")

    # -------- 接收 & 解析循环 --------

    def _receive_loop(self):
        """接收循环，在单独线程中运行"""
        while self.running:
            try:
                data, addr = self.socket.recvfrom(self.buffer_size)
                system_ts = time.time()

                # 统计接收速率（仅日志用）
                self._recv_count += 1
                if self._recv_count % 100 == 0:
                    elapsed = system_ts - self._last_stat_time
                    rate = 100 / elapsed if elapsed > 0 else 0
                    self.logger.info(f"UDP接收速率: {rate:.1f} packet/s (已接收{self._recv_count}个)")
                    self._last_stat_time = system_ts

                # 解析EEG数据包
                packets = self._parse_eeg_packet(data, system_ts)

                # 如果解析不到合法数据，直接跳过
                if not packets:
                    continue

                # ------- 按“包”检查硬件时间戳是否倒退 -------
                current_hw_ts = packets[0].hardware_timestamp

                if self._last_hw_timestamp is not None and current_hw_ts < self._last_hw_timestamp:
                    # 当前包时间戳比上一包小，认为是“倒退”，丢弃这一整个 UDP 包
                    self.logger.warning(
                        f"硬件时间戳倒退，丢弃当前UDP包: 当前 {current_hw_ts:.6f}s, 上一次 {self._last_hw_timestamp:.6f}s"
                    )
                    continue

                # 正常情况：更新时间戳
                self._last_hw_timestamp = current_hw_ts
                # ------- 新增逻辑结束 -------

                for packet in packets:
                    # 第一个数据包建立时间同步
                    if not self.synced:
                        self.sync_offset = system_ts - packet.hardware_timestamp
                        self.synced = True
                        self.sync_established.emit(self.sync_offset)
                        self.logger.info(f"时间同步已建立，偏移量: {self.sync_offset:.6f}s")

                    # 更新统计信息
                    self.packet_count += 1
                    self.active_channels.add(packet.channel)

                    # 入队 & 发信号
                    self.data_queue.put(packet)
                    self.data_received.emit(packet)

            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    self.logger.error(f"接收数据时出错: {e}")
                    self.error_occurred.emit(f"接收数据时出错: {e}")

    def _parse_eeg_packet(self, data: bytes, system_ts: float) -> List[EegDataPacket]:
        """
        解析EEG数据包（优化版本）
        自动检测通道数：支持单通道(47字节)、多通道(47*N字节)格式
        """
        packets: List[EegDataPacket] = []

        if len(data) < 47:
            return packets

        # 前两个字节必须是 0xAD 0xAD
        if data[0] != 0xAD or data[1] != 0xAD:
            return packets

        CHANNEL_FRAME_SIZE = 47
        data_len = len(data)

        if data_len % CHANNEL_FRAME_SIZE == 0:
            num_channels = data_len // CHANNEL_FRAME_SIZE
            for i in range(num_channels):
                start_idx = i * CHANNEL_FRAME_SIZE
                end_idx = start_idx + CHANNEL_FRAME_SIZE
                channel_frame = data[start_idx:end_idx]

                if len(channel_frame) >= 2 and channel_frame[0] == 0xAD and channel_frame[1] == 0xAD:
                    packet = self._parse_single_channel_frame(channel_frame, system_ts)
                    if packet:
                        packets.append(packet)
        else:
            self.logger.warning(f"数据包长度 {data_len} 不是 {CHANNEL_FRAME_SIZE} 的整数倍，无法解析")

        return packets

    def _parse_single_channel_frame(self, frame_data: bytes, system_ts: float) -> Optional[EegDataPacket]:
        """解析单通道数据帧(47字节)"""
        try:
            if len(frame_data) < 47:
                return None

            # 通道号
            channel = frame_data[5]

            # 数据长度（大端）
            data_length = (frame_data[6] << 8) | frame_data[7]

            # 时间戳（大端 uint64，单位: 微秒）
            timestamp_offset = 8 + 30
            if timestamp_offset + 8 > len(frame_data):
                return None

            hardware_ts_raw = struct.unpack(">Q", frame_data[timestamp_offset: timestamp_offset + 8])[0]

            # 调试：只打印前几个
            if not hasattr(self, "_debug_count"):
                self._debug_count = 0
            if self._debug_count < 5:
                self.logger.info(f"原始时间戳: {hardware_ts_raw}, 通道: {channel}")
                self._debug_count += 1

            # 微秒 -> 秒
            hardware_ts = hardware_ts_raw / 1_000_000.0

            # 解析 3 字节 EEG 数据
            data_point_count = data_length // 3
            samples: List[float] = []

            for j in range(data_point_count):
                data_offset = 8 + j * 3
                if data_offset + 2 < len(frame_data):
                    b1 = frame_data[data_offset]
                    b2 = frame_data[data_offset + 1]
                    b3 = frame_data[data_offset + 2]

                    if (b1 & 0x80) != 0:
                        # 负数：符号扩展
                        raw_value = (b1 << 16) | (b2 << 8) | b3 | (0xFF << 24)
                    else:
                        raw_value = (b1 << 16) | (b2 << 8) | b3

                    # 转成 32 位有符号整数
                    if raw_value >= 0x80000000:
                        raw_value -= 0x100000000

                    # 转微伏
                    microvolts = raw_value / 1000.0
                    samples.append(microvolts)

            return EegDataPacket(
                hardware_timestamp=hardware_ts,
                system_timestamp=system_ts,
                data=samples,
                channel=channel,
                raw_packet=frame_data,
            )

        except Exception as e:
            self.logger.error(f"解析单通道数据帧失败: {e}")
            return None

    # ===== 辅助方法（可以先不用） =====

    def get_synchronized_timestamp(self, hardware_ts: float) -> float:
        if not self.synced:
            raise RuntimeError("时间同步尚未建立")
        return hardware_ts + self.sync_offset

    def get_latest_data(self) -> Optional[EegDataPacket]:
        try:
            return self.data_queue.get_nowait()
        except queue.Empty:
            return None

    def get_all_data(self) -> List[EegDataPacket]:
        packets: List[EegDataPacket] = []
        while True:
            packet = self.get_latest_data()
            if packet is None:
                break
            packets.append(packet)
        return packets

    def is_synced(self) -> bool:
        return self.synced

    def get_packet_count(self) -> int:
        return self.packet_count

    def get_queue_size(self) -> int:
        return self.data_queue.qsize()

    def get_active_channels(self) -> List[int]:
        return sorted(list(self.active_channels))

    def clear_queue(self):
        while not self.data_queue.empty():
            try:
                self.data_queue.get_nowait()
            except queue.Empty:
                break


# ====================== Page2：使用新的 UdpEegReceiver ======================


class Page2Widget(QtWidgets.QWidget):
    """
    页面2：实时显示 UDP EEG 数据（只展示，不保存）
    - 自动解析多通道
    - 显示所有活跃通道的波形（叠加在同一个图上）
    - 利用硬件时间戳估算“最近 3 秒窗口”的采样率（可选）
    - 通过下拉框选择通道数（3/4），通过 checkbox 动态控制每个通道是否显示
    - 新增走纸方式：1=滚动窗口，2=扫屏重写（带竖直指示线）
    - 新增数据保存按钮：“开始保存数据” / “暂停保存数据，并落盘”
    """

    def __init__(self, parent=None):
        super(Page2Widget, self).__init__(parent)

        self.data_dir = "data"
        os.makedirs(self.data_dir, exist_ok=True)

        # 传感器序列号（默认值 000003，真正的值在收到第一帧数据后解析）
        self.sensor_serial: str = "000003"
        self._sensor_serial_parsed: bool = False

        self.last_plot_time = 0.0
        self.plot_interval = 1.0 / 30.0  # 最多 ~30 FPS

        # ====== 主布局 ======
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(4)

        # ===================== 顶部控件行：端口 -> 通道数 -> 显示通道 -> 计算采样率 -> 绘图降采样 -> 走纸方式 =====================

        # ---------- 端口 小组 ----------
        self.label_port = QtWidgets.QLabel("端口：")
        self.label_port.setFixedWidth(40)
        self.label_port.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

        self.input_port = QtWidgets.QLineEdit()
        self.input_port.setFixedWidth(80)
        self.input_port.setPlaceholderText("例如 30300")
        self.input_port.setText("30300")
        self.input_port.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

        port_layout = QtWidgets.QHBoxLayout()
        port_layout.setContentsMargins(0, 0, 0, 0)
        port_layout.setSpacing(4)
        port_layout.addWidget(self.label_port)
        port_layout.addWidget(self.input_port)

        # ---------- 通道数 小组 ----------
        self.label_channel_count = QtWidgets.QLabel("通道数：")
        self.label_channel_count.setFixedWidth(60)
        self.combo_channel_count = QtWidgets.QComboBox()
        self.combo_channel_count.setFixedWidth(80)
        self.combo_channel_count.addItem("3", 3)
        self.combo_channel_count.addItem("4", 4)

        channel_count_layout = QtWidgets.QHBoxLayout()
        channel_count_layout.setContentsMargins(0, 0, 0, 0)
        channel_count_layout.setSpacing(4)
        channel_count_layout.addWidget(self.label_channel_count)
        channel_count_layout.addWidget(self.combo_channel_count)

        # ---------- 显示通道（checkbox 区域） ----------
        self.label_show_channels = QtWidgets.QLabel("显示通道：")

        # checkbox 容器 layout
        self.channel_checkbox_layout = QtWidgets.QHBoxLayout()
        self.channel_checkbox_layout.setContentsMargins(0, 0, 0, 0)
        self.channel_checkbox_layout.setSpacing(8)

        # 存储 checkbox 的字典
        self.channel_checkboxes: dict[int, QtWidgets.QCheckBox] = {}

        show_channels_layout = QtWidgets.QHBoxLayout()
        show_channels_layout.setContentsMargins(0, 0, 0, 0)
        show_channels_layout.setSpacing(4)
        show_channels_layout.addWidget(self.label_show_channels)
        show_channels_layout.addLayout(self.channel_checkbox_layout)

        # ---------- 采样率估计 & 绘图降采样 ----------
        self.checkbox_enable_fs_estimate = QtWidgets.QCheckBox("计算采样率")
        self.checkbox_enable_fs_estimate.setChecked(False)

        self.checkbox_downsample_plot = QtWidgets.QCheckBox("绘图降采样1/5")
        self.checkbox_downsample_plot.setChecked(False)

        self.label_fs_estimated = QtWidgets.QLabel("采样率估计：-- Hz")
        self.label_fs_estimated.setFixedWidth(160)

        fs_est_layout = QtWidgets.QHBoxLayout()
        fs_est_layout.setContentsMargins(0, 0, 0, 0)
        fs_est_layout.setSpacing(4)
        fs_est_layout.addWidget(self.checkbox_enable_fs_estimate)
        fs_est_layout.addWidget(self.label_fs_estimated)
        fs_est_layout.addSpacing(8)
        fs_est_layout.addWidget(self.checkbox_downsample_plot)

        # ---------- 走纸方式 ----------
        self.label_scroll_mode = QtWidgets.QLabel("走纸方式：")
        self.combo_scroll_mode = QtWidgets.QComboBox()
        self.combo_scroll_mode.setFixedWidth(120)
        self.combo_scroll_mode.addItem("滚动窗口", 1)   # 模式1
        self.combo_scroll_mode.addItem("扫屏重写", 2)   # 模式2

        scroll_mode_layout = QtWidgets.QHBoxLayout()
        scroll_mode_layout.setContentsMargins(0, 0, 0, 0)
        scroll_mode_layout.setSpacing(4)
        scroll_mode_layout.addWidget(self.label_scroll_mode)
        scroll_mode_layout.addWidget(self.combo_scroll_mode)

        # ---------- 顶部整行布局 ----------
        self.top_controls_layout = QtWidgets.QHBoxLayout()
        self.top_controls_layout.setContentsMargins(20, 0, 20, 0)
        self.top_controls_layout.setSpacing(12)

        self.top_controls_layout.addStretch()
        self.top_controls_layout.addLayout(port_layout)
        self.top_controls_layout.addSpacing(16)
        self.top_controls_layout.addLayout(channel_count_layout)
        self.top_controls_layout.addSpacing(16)
        self.top_controls_layout.addLayout(show_channels_layout)
        self.top_controls_layout.addSpacing(16)
        self.top_controls_layout.addLayout(fs_est_layout)
        self.top_controls_layout.addSpacing(16)
        self.top_controls_layout.addLayout(scroll_mode_layout)
        self.top_controls_layout.addStretch()

        # ===================== 第二行：重置y轴范围、开始检测信号、开始保存数据 + 状态 =====================

        # 重置 y 轴范围按钮
        self.button_reset_y = QtWidgets.QPushButton("重置y轴范围")
        self.button_reset_y.setFixedWidth(110)
        self.button_reset_y.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

        # 开始/停止检测信号按钮
        self.button_1 = QtWidgets.QPushButton(ButtonStates.start.value)
        self.button_1.setFixedWidth(160)
        self.button_1.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

        # 开始保存数据按钮
        self.button_save = QtWidgets.QPushButton("开始保存数据")
        self.button_save.setFixedWidth(220)  # 按钮加长，防止文字被截断
        self.button_save.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        # 初始不可用 + 灰色样式
        self.button_save.setEnabled(False)
        self.button_save.setStyleSheet(
            "QPushButton:disabled {"
            "background-color: #dcdcdc;"
            "color: #888888;"
            "}"
        )

        # 状态标签
        self.label_1 = QtWidgets.QLabel(LabelStates.stopped.value)
        self.label_1.setFixedWidth(360)
        self.label_1.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self.label_1.setStyleSheet("color: #5d5d5d")

        self.bottom_controls_layout = QtWidgets.QHBoxLayout()
        self.bottom_controls_layout.setContentsMargins(20, 0, 20, 0)
        self.bottom_controls_layout.setSpacing(16)

        self.bottom_controls_layout.addStretch()
        self.bottom_controls_layout.addWidget(self.button_reset_y)
        self.bottom_controls_layout.addSpacing(16)
        self.bottom_controls_layout.addWidget(self.button_1)
        self.bottom_controls_layout.addSpacing(16)
        self.bottom_controls_layout.addWidget(self.label_1)
        self.bottom_controls_layout.addSpacing(24)
        self.bottom_controls_layout.addWidget(self.button_save)
        self.bottom_controls_layout.addStretch()

        # ===================== 曲线相关结构 =====================
        self.max_points = 1000
        self.sample_rate_hz: float | None = None
        self.plot_downsample_step = 5   # 绘图降采样步长（1/5）

        # 窗口宽度（秒）
        self.window_sec = 5.0
        self.window_points = 1000
        self.sweep_x: List[float] = [
            self.window_sec * i / max(self.window_points - 1, 1)
            for i in range(self.window_points)
        ]

        # 多通道数据结构
        self.channel_data_x: dict[int, deque] = {}
        self.channel_data_y: dict[int, deque] = {}
        self.channel_sample_index: dict[int, int] = {}
        self.channel_curves: dict[int, pg.PlotDataItem] = {}
        self.active_channels_in_plot: set[int] = set()
        self.channel_colors = ["r", "g", "b", "c", "m", "y", "k"]

        # 扫屏模式 buffer
        self.sweep_buffers: dict[int, List[float]] = {}
        self.sweep_index: dict[int, int] = {}

        # 采样率估计（全局）
        self.reference_channel: Optional[int] = None
        self.ref_window = deque()             # (hw_ts, n_samples)
        self.fs_estimated_global: float = 0.0

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground("w")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.2)
        self.plot_widget.setLabel("left", "μV")
        self.plot_widget.setLabel("bottom", "Time (s)")
        self.plot_widget.setYRange(-200, 200)
        self.legend = self.plot_widget.addLegend()

        # 扫屏模式下的竖直指示线
        self.sweep_line: Optional[pg.InfiniteLine] = None

        # 主布局加入：顶部控件行 + 按钮行 + 曲线
        self.main_layout.addLayout(self.top_controls_layout)
        self.main_layout.addLayout(self.bottom_controls_layout)
        self.main_layout.addWidget(self.plot_widget)

        # 默认走纸模式：2 = 扫屏重写
        self.scroll_mode = 2
        self.combo_scroll_mode.setCurrentIndex(1)
        self.combo_scroll_mode.currentIndexChanged.connect(self.on_scroll_mode_changed)

        # 连接通道数变化信号，并初始化 checkbox
        self.combo_channel_count.currentIndexChanged.connect(self.on_channel_count_changed)
        self.on_channel_count_changed()

        # ===== IP 和采样率输入控件（仅提供默认值，不参与布局） =====
        self.label_ip = QtWidgets.QLabel("监听IP：")
        self.label_ip.setFixedWidth(60)
        self.input_ip = QtWidgets.QLineEdit()
        self.input_ip.setFixedWidth(150)
        self.input_ip.setPlaceholderText("例如 0.0.0.0")
        self.input_ip.setText("0.0.0.0")

        self.label_fs = QtWidgets.QLabel("采样率(Hz)：")
        self.label_fs.setFixedWidth(80)
        self.input_fs = QtWidgets.QLineEdit()
        self.input_fs.setFixedWidth(80)
        self.input_fs.setPlaceholderText("例如 1000")
        self.input_fs.setText("1000")

        # 隐藏 IP 和采样率输入控件（只用默认值）
        self.label_ip.hide()
        self.input_ip.hide()
        self.label_fs.hide()
        self.input_fs.hide()

        # 信号与槽
        self.button_1.clicked.connect(self.start_udp_receiving)
        self.button_reset_y.clicked.connect(self.reset_y_axis_range)
        self.button_save.clicked.connect(self.toggle_save_data)

        # UDP 接收器
        self.receiver: Optional[UdpEegReceiver] = None
        # 与硬件时间同步的偏移量（system_ts - hardware_ts），在 on_sync_established 中写入
        self.sync_offset: Optional[float] = None

        # ===== 保存数据相关 =====
        self.is_saving: bool = False
        self.channel_save_files: dict[int, object] = {}   # ch -> file
        self.channel_save_index: dict[int, int] = {}      # ch -> sample index（仅做计数，不再用于计算时间轴）
        self.marker_file: Optional[object] = None         # markers.csv 文件句柄

    # -------- 工具：递归清空一个 layout --------

    def _clear_layout(self, layout: QtWidgets.QLayout):
        """递归清空一个 QLayout"""
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            if child_layout is not None:
                self._clear_layout(child_layout)

    # -------- 根据数据帧解析传感器序列号 --------

    def _parse_sensor_serial(self, frame_data: bytes) -> str:
        """
        根据数据帧解析传感器序列号。
        具体哪几个字节表示序列号需要根据你的协议 / 图示来调整。
        这里暂时示例为：使用第 2~4 字节作为 3 字节无符号整数，
        再格式化为 6 位十进制字符串，例如 "000003"。
        """
        try:
            if len(frame_data) < 5:
                return "000000"

            # 示例：假设 2~4 字节为序列号
            raw = (frame_data[2] << 16) | (frame_data[3] << 8) | frame_data[4]
            serial_int = raw & 0xFFFFFF
            serial_str = f"{serial_int:06d}"
            return serial_str
        except Exception as e:
            print("解析传感器序列号失败:", e)
            return "000000"

    # -------- 通道数变化：更新 checkbox --------

    def on_channel_count_changed(self):
        """当下拉框选择通道数变化时，重新生成 checkbox"""
        self._clear_layout(self.channel_checkbox_layout)
        self.channel_checkboxes.clear()

        count = self.combo_channel_count.currentData()
        if count is None:
            count = 3

        for ch in range(count):
            cb = QtWidgets.QCheckBox(f"Ch{ch}")
            cb.setChecked(True)
            self.channel_checkbox_layout.addWidget(cb)
            self.channel_checkboxes[ch] = cb

    def on_scroll_mode_changed(self, index: int):
        """切换走纸方式：1=滚动窗口，2=扫屏重写"""
        mode = self.combo_scroll_mode.currentData()
        if mode in (1, 2):
            self.scroll_mode = mode
        # 竖直线显隐在 update_plot 内部控制，这里无需额外处理

    # -------- 启动 / 停止按钮逻辑 --------

    def start_udp_receiving(self):
        """开始或停止 UDP 监听"""
        ip = self.input_ip.text().strip()
        port_str = self.input_port.text().strip()
        fs_str = self.input_fs.text().strip()

        # ====== 点击“开始检测信号” ======
        if self.button_1.text() == ButtonStates.start.value:
            if not ip or not port_str or not fs_str:
                self.label_1.setText("请输入 IP、端口 和 采样率")
                self.label_1.setStyleSheet("color: red")
                return
            if not is_valid_ip(ip):
                self.label_1.setText("请输入合法的 IP")
                self.label_1.setStyleSheet("color: red")
                return
            if not is_valid_port(port_str):
                self.label_1.setText("请输入合法的端口 (1-65535)")
                self.label_1.setStyleSheet("color: red")
                return
            if not is_valid_sample_rate(fs_str):
                self.label_1.setText("请输入合法的采样率(>0)")
                self.label_1.setStyleSheet("color: red")
                return

            port = int(port_str)
            self.sample_rate_hz = float(fs_str)

            # 根据采样率估算窗口点数和缓冲长度
            points_for_5s = int(self.sample_rate_hz * self.window_sec)
            if points_for_5s <= 0:
                points_for_5s = 1
            self.window_points = max(points_for_5s, 1000)
            self.max_points = max(self.window_points * 2, 1000)

            # 更新扫屏模式 X 坐标
            if self.window_points > 1:
                self.sweep_x = [
                    self.window_sec * i / (self.window_points - 1)
                    for i in range(self.window_points)
                ]
            else:
                self.sweep_x = [0.0]

            # 清空旧数据
            self.channel_data_x.clear()
            self.channel_data_y.clear()
            self.channel_sample_index.clear()
            self.channel_curves.clear()
            self.active_channels_in_plot.clear()
            self.last_plot_time = 0.0

            self.sweep_buffers.clear()
            self.sweep_index.clear()

            # 重置采样率估计
            self.reference_channel = None
            self.ref_window.clear()
            self.fs_estimated_global = 0.0
            self.label_fs_estimated.setText("采样率估计：-- Hz")

            # 重置传感器序列号解析标记
            self.sensor_serial = "000003"
            self._sensor_serial_parsed = False

            # 清空图像并重新设置轴和图例
            self.plot_widget.clear()
            self.plot_widget.setBackground("w")
            self.plot_widget.showGrid(x=True, y=True, alpha=0.2)
            self.plot_widget.setLabel("left", "μV")
            self.plot_widget.setLabel("bottom", "Time (s)")
            self.plot_widget.setYRange(-200, 200)
            self.legend = self.plot_widget.addLegend()

            # 重新创建扫屏指示线
            from pyqtgraph import mkPen
            self.sweep_line = pg.InfiniteLine(
                angle=90,
                movable=False,
                pen=mkPen(color=(200, 0, 150), width=2, style=Qt.PenStyle.DashLine),
            )
            self.plot_widget.addItem(self.sweep_line)
            self.sweep_line.setVisible(self.scroll_mode == 2)

            # UI 状态：禁用一些控件
            self.input_ip.setDisabled(True)
            self.input_port.setDisabled(True)
            self.input_fs.setDisabled(True)
            self.combo_channel_count.setDisabled(True)
            self.combo_scroll_mode.setDisabled(True)
            self.checkbox_enable_fs_estimate.setDisabled(True)
            # 降采样 checkbox 保持可用

            # 如果之前有 receiver，先停掉
            if self.receiver is not None:
                self.receiver.stop()
                self.receiver.deleteLater()
                self.receiver = None

            # 创建新的 UdpEegReceiver
            self.receiver = UdpEegReceiver(host=ip, port=port, buffer_size=8192, parent=self)

            # 连接信号
            self.receiver.data_received.connect(self.on_eeg_packet)
            self.receiver.error_occurred.connect(self.on_error)
            self.receiver.sync_established.connect(self.on_sync_established)

            # 启动
            try:
                self.receiver.start()
            except Exception as e:
                self.label_1.setText(f"启动UDP接收器失败: {e}")
                self.label_1.setStyleSheet("color: red")
                self.input_ip.setDisabled(False)
                self.input_port.setDisabled(False)
                self.input_fs.setDisabled(False)
                self.combo_channel_count.setDisabled(False)
                self.combo_scroll_mode.setDisabled(False)
                self.checkbox_enable_fs_estimate.setDisabled(False)
                if self.receiver is not None:
                    self.receiver.deleteLater()
                    self.receiver = None
                return

            # 按钮 & 状态文案更新
            self.button_1.setText(ButtonStates.stop.value)
            self.label_1.setText(LabelStates.listening.value)
            self.label_1.setStyleSheet("color: #5d5d5d")

            # 启动接收时，允许“开始保存数据”
            self.stop_saving()
            self.button_save.setEnabled(True)

        # ====== 点击“停止检测信号” ======
        elif self.button_1.text() == ButtonStates.stop.value:
            if self.receiver is not None:
                self.receiver.stop()
                self.receiver.deleteLater()
                self.receiver = None

            # 停止保存并禁用按钮
            self.stop_saving()
            self.button_save.setEnabled(False)

            # 恢复UI
            self.button_1.setText(ButtonStates.start.value)
            self.label_1.setText(LabelStates.stopped.value)
            self.label_1.setStyleSheet("color: #5d5d5d")
            self.input_ip.setDisabled(False)
            self.input_port.setDisabled(False)
            self.input_fs.setDisabled(False)
            self.combo_channel_count.setDisabled(False)
            self.combo_scroll_mode.setDisabled(False)
            self.checkbox_enable_fs_estimate.setDisabled(False)

    # -------- 接收 EEG 数据并更新曲线 + 保存 --------

    def on_eeg_packet(self, packet: EegDataPacket):
        """
        收到 UdpEegReceiver 解析好的 EegDataPacket
        """
        if self.sample_rate_hz is None or self.sample_rate_hz <= 0:
            return

        ch = packet.channel

        # 第一次收到数据时，尝试从原始数据帧中解析传感器序列号
        if (not self._sensor_serial_parsed) and packet.raw_packet:
            self.sensor_serial = self._parse_sensor_serial(packet.raw_packet)
            self._sensor_serial_parsed = True
            print(f"数据来自传感器序列号: {self.sensor_serial}")

        # 先保存数据
        if self.is_saving:
            self._save_packet_samples(packet)

        # 初始化通道数据结构和曲线
        if ch not in self.channel_data_x:
            self.channel_data_x[ch] = deque(maxlen=self.max_points)
            self.channel_data_y[ch] = deque(maxlen=self.max_points)
            self.channel_sample_index[ch] = 0

            color = self.channel_colors[len(self.channel_curves) % len(self.channel_colors)]
            curve = self.plot_widget.plot(pen=color, name=f"Ch {ch}")
            self.channel_curves[ch] = curve

        # 扫屏模式缓冲区初始化
        if ch not in self.sweep_buffers:
            self.sweep_buffers[ch] = [float("nan")] * self.window_points
            self.sweep_index[ch] = 0

        # 记录活跃通道
        self.active_channels_in_plot.add(ch)

        # 没有参考通道时，把当前通道当作参考通道
        if self.reference_channel is None:
            self.reference_channel = ch
            self.ref_window.clear()

        # -------- 1) 按模式写入数据（用于绘图） --------
        if self.scroll_mode == 1:
            # 滚动窗口：使用片上时间作为 X 轴（秒）
            dt_s = 1.0 / self.sample_rate_hz if self.sample_rate_hz and self.sample_rate_hz > 0 else 0.0
            samples = packet.data
            n = len(samples)
            if n == 0:
                return

            hw_ts = packet.hardware_timestamp  # 该包最后一个采样点的片上时间（秒）

            if dt_s > 0:
                # 第 j 个点的时间：t_j = hw_ts - (n - 1 - j) * dt
                t_first = hw_ts - (n - 1) * dt_s
            else:
                # 兜底：没有有效采样率时，所有点使用同一个时间
                t_first = hw_ts

            for j, v in enumerate(samples):
                self.channel_sample_index[ch] += 1  # 仍然累积样本计数，仅用于统计
                t_s = t_first + j * dt_s
                self.channel_data_x[ch].append(t_s)
                self.channel_data_y[ch].append(v)
        else:
            # 扫屏重写
            if self.window_points <= 0:
                return
            idx = self.sweep_index[ch]
            for v in packet.data:
                self.sweep_buffers[ch][idx] = v
                idx += 1
                if idx >= self.window_points:
                    idx = 0
                self.channel_sample_index[ch] += 1
            self.sweep_index[ch] = idx

        # -------- 2) 采样率估计（仅参考通道 + 勾选时） --------
        if self.checkbox_enable_fs_estimate.isChecked() and self.reference_channel == ch:
            ts_now = packet.hardware_timestamp
            n_new = len(packet.data)

            self.ref_window.append((ts_now, n_new))

            window_len = 3.0
            window_start = ts_now - window_len
            while self.ref_window and self.ref_window[0][0] < window_start:
                self.ref_window.popleft()

            if self.ref_window:
                total_samples = sum(n for (_, n) in self.ref_window)
                oldest_ts = self.ref_window[0][0]
                elapsed = ts_now - oldest_ts

                if elapsed > 0 and total_samples > 0:
                    self.fs_estimated_global = total_samples / elapsed
                    self.label_fs_estimated.setText(f"采样率估计：{self.fs_estimated_global:.1f} Hz")

        # 当前显示通道列表
        channels_sorted = sorted(self.active_channels_in_plot)
        visible_channels = []
        for c in channels_sorted:
            cb = self.channel_checkboxes.get(c)
            if cb is None or cb.isChecked():
                visible_channels.append(c)

        # 更新主状态 label
        self.label_1.setText(
            f"{LabelStates.receiving.value} 当前显示通道: {visible_channels}"
        )
        self.label_1.setStyleSheet("color: #008000")

        # 刷新曲线（限频）
        now = time.time()
        if now - self.last_plot_time >= self.plot_interval:
            self.update_plot()
            self.last_plot_time = now

    # -------- 保存按钮逻辑 --------

    def toggle_save_data(self):
        """点击“开始保存数据” / “暂停保存数据，并落盘”"""
        if not self.is_saving:
            self.start_saving()
        else:
            self.stop_saving()

    def start_saving(self):
        """开始保存数据：创建 CSV 文件和 markers.csv"""
        if self.is_saving:
            return

        # 必须已经开启 UDP 监听（Page2 中点击过“开始检测信号”）
        if not self.is_listening():
            self.label_1.setText("请先点击“开始检测信号”再启动数据保存")
            self.label_1.setStyleSheet("color: red")
            return

        if self.sample_rate_hz is None or self.sample_rate_hz <= 0:
            self.label_1.setText("采样率无效，无法开始保存数据")
            self.label_1.setStyleSheet("color: red")
            return

        self.is_saving = True
        self.channel_save_files.clear()
        self.channel_save_index.clear()

        # 创建 markers.csv，并写入表头（放到 data 目录下）
        try:
            marker_path = os.path.join(self.data_dir, "markers.csv")
            self.marker_file = open(marker_path, "w", encoding="utf-8", newline="")
            self.marker_file.write("Time,marker_index\n")
        except Exception as e:
            print("创建 markers.csv 失败:", e)
            self.marker_file = None

        self.button_save.setText("暂停保存数据，并落盘")

    def stop_saving(self):
        """停止保存数据，关闭所有文件"""
        if not self.is_saving:
            return

        # 关闭每个通道的 CSV 文件
        for f in self.channel_save_files.values():
            try:
                f.close()
            except Exception:
                pass
        self.channel_save_files.clear()
        self.channel_save_index.clear()

        # 关闭 markers.csv
        if self.marker_file is not None:
            try:
                self.marker_file.close()
            except Exception:
                pass
            self.marker_file = None

        self.is_saving = False
        self.button_save.setText("开始保存数据")

    def _save_packet_samples(self, packet: EegDataPacket):
        """
        将一个 EegDataPacket 中的每个采样点写入对应通道的 CSV，
        并在 markers.csv 中写入时间和 marker_index（目前全为0）。

        时间轴与片上时间的关系：
        - packet.hardware_timestamp 来自硬件（单位：秒），同一个 UDP 包内所有通道一致
        - 假设它表示“该包最后一个采样点”的时间
        - 已知采样率 fs，则 dt = 1/fs
        - 若包内有 N 个点，则：
            第 j 个采样点（j 从 0 开始）的时间为：
                t_j = hardware_timestamp - (N - 1 - j) * dt

        CSV 中的 Time 列直接使用 t_j（单位：秒），
        这样就可以和你打印出来的 8.23274 / 8.242737 / 8.252734 等片上时间对齐。
        """
        ch = packet.channel

        # 初始化该通道的 CSV 文件
        if ch not in self.channel_save_files:
            serial_str = getattr(self, "sensor_serial", "xxxxxx")
            filename = os.path.join(self.data_dir, f"EEG_{serial_str}_{ch:02d}.csv")
            try:
                f = open(filename, "w", encoding="utf-8", newline="")
                f.write("Time,Response\n")
                self.channel_save_files[ch] = f
                self.channel_save_index[ch] = 0  # 现在只做计数，不参与时间计算
            except Exception as e:
                print(f"打开通道 {ch} 的 CSV 文件失败:", e)
                return

        f = self.channel_save_files[ch]

        # 采样间隔 dt
        if self.sample_rate_hz and self.sample_rate_hz > 0:
            dt_s = 1.0 / self.sample_rate_hz
        else:
            dt_s = 0.0  # 理论上不会走到，因为前面已经校验过 fs

        samples = packet.data
        n = len(samples)
        if n == 0:
            return

        hw_ts = packet.hardware_timestamp  # 该包的片上时间（秒）

        # 假设 hardware_timestamp 是“最后一个采样点”的时间
        if dt_s > 0:
            t_first = hw_ts - (n - 1) * dt_s
        else:
            # 兜底：没有有效采样率时，就全部写成同一个时间戳
            t_first = hw_ts

        idx = self.channel_save_index.get(ch, 0)

        for j, v in enumerate(samples):
            # 第 j 个采样点的时间
            t_s = t_first + j * dt_s

            # EEG 通道 CSV：Time,Response
            # 使用 6 位小数，保留微秒级别的精度
            f.write(f"{t_s:.6f},{v:.6f}\n")

            # markers.csv：Time,marker_index（目前 marker_index 全为0）
            if ch == 0 and self.marker_file is not None:
                self.marker_file.write(f"{t_s:.6f},0\n")

            idx += 1

        # 更新该通道已经写出的样本数
        self.channel_save_index[ch] = idx

    # -------- 其他 UI 回调 --------

    def on_error(self, message: str):
        print("UDP 错误:", message)
        self.label_1.setText(message)
        self.label_1.setStyleSheet("color: red")

    def on_sync_established(self, offset: float):
        """
        时间同步建立时调用。
        不再使用 tooltip，仅打印到控制台。
        """
        self.sync_offset = offset
        print(f"时间同步偏移量: {offset:.6f}s")

    # -------- 提供给其他页面（如范式页）的辅助方法 --------

    def is_listening(self) -> bool:
        """
        返回当前是否已经开启 UDP 监听：
        - True  表示 UdpEegReceiver 已经启动（处于 listening / receiving 状态）
        - False 表示尚未启动或已经停止
        """
        if self.receiver is None:
            return False
        if hasattr(self.receiver, "is_running"):
            try:
                return self.receiver.is_running()
            except Exception:
                return False
        return self.receiver.running

    def get_last_hardware_timestamp(self) -> Optional[float]:
        """
        获取最近一次接收到的数据包的片上时间戳（秒）。
        若尚未收到任何数据或未启动接收，则返回 None。
        """
        if self.receiver is None:
            return None
        if hasattr(self.receiver, "get_last_hw_timestamp"):
            try:
                return self.receiver.get_last_hw_timestamp()
            except Exception:
                return None
        return getattr(self.receiver, "_last_hw_timestamp", None)

    def convert_system_time_to_hw(self, system_ts: float) -> Optional[float]:
        """
        将本机 system_ts（time.time()）转换为片上时间。
        需要已经完成一次时间同步（sync_offset 不为 None）。
        """
        if self.sync_offset is None:
            return None
        return system_ts - self.sync_offset

    # -------- 重置 y 轴范围 --------

    def reset_y_axis_range(self):
        """将y轴范围重置回 -200 ~ 200 μV"""
        self.plot_widget.setYRange(-200, 200)

    # -------- 画图：两种走纸方式 + 可选 1/2 降采样 --------

    def update_plot(self):
        """
        更新曲线显示：
        - 模式1：X轴为片上时间（秒），固定 window_sec 秒窗口，所有勾选通道叠加显示
        - 模式2：X轴固定为 [0, window_sec]，扫屏缓冲区按固定 X 坐标绘制，并显示竖直指示线
        - 勾选“绘图降采样1/2”时，对 X/Y 使用 ::2 降采样
        """
        if not self.channel_curves:
            return

        downsample = self.checkbox_downsample_plot.isChecked()

        # 模式1：滚动窗口（使用片上时间）
        if self.scroll_mode == 1:
            if self.sweep_line is not None:
                self.sweep_line.setVisible(False)

            x_max = None

            for ch, curve in self.channel_curves.items():
                x_deque = self.channel_data_x.get(ch)
                y_deque = self.channel_data_y.get(ch)
                if not x_deque or not y_deque:
                    continue

                cb = self.channel_checkboxes.get(ch)
                if cb is not None and not cb.isChecked():
                    curve.setVisible(False)
                    continue
                else:
                    curve.setVisible(True)

                x_data = list(x_deque)
                y_data = list(y_deque)

                if downsample and len(x_data) > 1:
                    step = self.plot_downsample_step
                    x_plot = x_data[::step]
                    y_plot = y_data[::step]
                else:
                    x_plot = x_data
                    y_plot = y_data

                curve.setData(x=x_plot, y=y_plot)

                if x_plot:
                    last_x = x_plot[-1]
                    if x_max is None or last_x > x_max:
                        x_max = last_x

            if x_max is None:
                return

            window = self.window_sec
            if x_max <= window:
                self.plot_widget.setXRange(0, window)
            else:
                self.plot_widget.setXRange(x_max - window, x_max)

        else:
            # 模式2：扫屏重写
            self.plot_widget.setXRange(0, self.window_sec)

            for ch, curve in self.channel_curves.items():
                buf = self.sweep_buffers.get(ch)
                if buf is None or len(buf) == 0:
                    continue

                cb = self.channel_checkboxes.get(ch)
                if cb is not None and not cb.isChecked():
                    curve.setVisible(False)
                    continue
                else:
                    curve.setVisible(True)

                if downsample and len(buf) > 1:
                    step = self.plot_downsample_step
                    x_plot = self.sweep_x[::step]
                    y_plot = buf[::step]
                else:
                    x_plot = self.sweep_x
                    y_plot = buf

                curve.setData(x=x_plot, y=y_plot)

            # 更新竖直指示线位置
            if self.sweep_line is not None:
                self.sweep_line.setVisible(True)
                idx = None
                if self.reference_channel is not None and self.reference_channel in self.sweep_index:
                    idx = self.sweep_index[self.reference_channel]
                else:
                    if self.sweep_index:
                        idx = list(self.sweep_index.values())[0]

                if idx is not None and self.window_points > 0:
                    last_idx = (idx - 1) % self.window_points
                    if 0 <= last_idx < len(self.sweep_x):
                        x_pos = self.sweep_x[last_idx]
                        self.sweep_line.setValue(x_pos)

    # -------- 生命周期清理 --------

    def closeEvent(self, event):
        """防止窗口关闭时线程还在运行"""
        if self.receiver is not None:
            self.receiver.stop()
            self.receiver.deleteLater()
            self.receiver = None

        if self.is_saving:
            self.stop_saving()

        event.accept()


if __name__ == "__main__":
    # 简单自测：只启动界面，不实际接收 UDP（除非你自己往端口发）
    import sys

    logging.basicConfig(level=logging.INFO)

    app = QtWidgets.QApplication(sys.argv)
    w = Page2Widget()
    w.resize(1000, 700)
    w.show()
    sys.exit(app.exec())
