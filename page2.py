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
    listening = "已开启UDP监听，等待数据..."
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
    status_changed = pyqtSignal(str, int, str)  # (状态, 包数量, 通道信息)
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

        # 统计用
        self.last_status_update = time.time()
        self.status_update_interval = 1.0  # 每秒更新一次状态

        self._recv_count = 0
        self._last_stat_time = time.time()
        self.receiver_thread: Optional[threading.Thread] = None

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

                # 统计接收速率
                self._recv_count += 1
                if self._recv_count % 100 == 0:
                    elapsed = system_ts - self._last_stat_time
                    rate = 100 / elapsed if elapsed > 0 else 0
                    self.logger.info(f"UDP接收速率: {rate:.1f} packet/s (已接收{self._recv_count}个)")
                    self._last_stat_time = system_ts

                # 解析EEG数据包
                packets = self._parse_eeg_packet(data, system_ts)

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

                # 用于更新“当前运行情况”的简要报告
                current_time = time.time()
                if current_time - self.last_status_update > self.status_update_interval:
                    self._update_status()
                    self.last_status_update = current_time

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

        if len(data) < 47:  # len(data) = 141个字节 = 47*3
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
            timestamp_offset = 38
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

    def _update_status(self):
        """更新状态信息（用于 tooltip 展示详细信息）"""
        status = "已同步" if self.synced else "等待同步"  # 判断是否已完成时间同步
        channel_info = f"通道: {sorted(list(self.active_channels))}" if self.active_channels else "通道: 无数据"
        self.status_changed.emit(status, self.packet_count, channel_info)  # 通知 UI

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
    - 利用硬件时间戳估算“最近 3 秒窗口”的采样率，只显示一次
    - 通过下拉框选择通道数（3/4），通过 checkbox 动态控制每个通道是否显示
    - 新增走纸方式：1=滚动窗口，2=扫屏重写（带竖直指示线）
    """

    def __init__(self, parent=None):
        super(Page2Widget, self).__init__(parent)

        self.last_plot_time = 0.0
        self.plot_interval = 1.0 / 120.0  # 最多 ~120 FPS

        # ====== 主布局 ======
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(4)

        # ===================== 顶部一行：IP / 端口 / 采样率 / 重置按钮 / 按钮+状态 =====================
        self.layout_1 = QtWidgets.QHBoxLayout()
        self.layout_1.setContentsMargins(20, 0, 20, 0)
        self.layout_1.setSpacing(12)  # 各小组之间间距

        # ---------- 1) IP 小组 ----------
        self.label_ip = QtWidgets.QLabel("监听IP：")
        self.label_ip.setFixedWidth(60)
        self.label_ip.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

        self.input_ip = QtWidgets.QLineEdit()
        self.input_ip.setFixedWidth(150)
        self.input_ip.setPlaceholderText("例如 0.0.0.0")
        self.input_ip.setText("0.0.0.0")
        self.input_ip.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

        ip_layout = QtWidgets.QHBoxLayout()
        ip_layout.setContentsMargins(0, 0, 0, 0)
        ip_layout.setSpacing(4)
        ip_layout.addWidget(self.label_ip)
        ip_layout.addWidget(self.input_ip)

        # ---------- 2) 端口 小组 ----------
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

        # ---------- 3) 采样率 小组 ----------
        self.label_fs = QtWidgets.QLabel("采样率(Hz)：")
        self.label_fs.setFixedWidth(80)
        self.label_fs.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

        self.input_fs = QtWidgets.QLineEdit()
        self.input_fs.setFixedWidth(80)
        self.input_fs.setPlaceholderText("例如 1000")
        self.input_fs.setText("1000")
        self.input_fs.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

        fs_layout = QtWidgets.QHBoxLayout()
        fs_layout.setContentsMargins(0, 0, 0, 0)
        fs_layout.setSpacing(4)
        fs_layout.addWidget(self.label_fs)
        fs_layout.addWidget(self.input_fs)

        # ---------- 4) 重置 y 轴范围按钮 ----------
        self.button_reset_y = QtWidgets.QPushButton("重置y轴范围")
        self.button_reset_y.setFixedWidth(110)
        self.button_reset_y.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self.button_reset_y.clicked.connect(self.reset_y_axis_range)

        # ---------- 5) 按钮 + 状态 小组 ----------
        self.button_1 = QtWidgets.QPushButton(ButtonStates.start.value)
        self.button_1.setFixedWidth(160)
        self.button_1.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

        self.label_1 = QtWidgets.QLabel(LabelStates.stopped.value)
        self.label_1.setFixedWidth(360)
        self.label_1.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self.label_1.setStyleSheet("color: #5d5d5d")

        btn_status_layout = QtWidgets.QHBoxLayout()
        btn_status_layout.setContentsMargins(0, 0, 0, 0)
        btn_status_layout.setSpacing(4)
        btn_status_layout.addWidget(self.button_1)
        btn_status_layout.addWidget(self.label_1)

        # ---------- 顶部行整体排布（左右拉伸，中间一条控件带） ----------
        self.layout_1.addStretch()
        self.layout_1.addLayout(ip_layout)
        self.layout_1.addSpacing(12)
        self.layout_1.addLayout(port_layout)
        self.layout_1.addSpacing(12)
        self.layout_1.addLayout(fs_layout)
        self.layout_1.addSpacing(16)
        self.layout_1.addWidget(self.button_reset_y)
        self.layout_1.addSpacing(24)
        self.layout_1.addLayout(btn_status_layout)
        self.layout_1.addStretch()

        # ===================== 第二行：通道数选择 + checkbox + 采样率估计 + 走纸方式 =====================
        self.channel_control_layout = QtWidgets.QHBoxLayout()
        self.channel_control_layout.setContentsMargins(20, 0, 20, 0)
        self.channel_control_layout.setSpacing(12)

        # 通道数下拉框
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

        # 显示通道标签
        self.label_show_channels = QtWidgets.QLabel("显示通道：")

        # checkbox 容器 layout
        self.channel_checkbox_layout = QtWidgets.QHBoxLayout()
        self.channel_checkbox_layout.setContentsMargins(0, 0, 0, 0)
        self.channel_checkbox_layout.setSpacing(8)

        # 存储 checkbox 的字典
        self.channel_checkboxes: dict[int, QtWidgets.QCheckBox] = {}

        # 采样率估计 Label（全局）
        self.label_fs_estimated = QtWidgets.QLabel("采样率估计：-- Hz")
        self.label_fs_estimated.setFixedWidth(160)

        # ===== 走纸方式选择（与前面控件一条线居中） =====
        self.label_scroll_mode = QtWidgets.QLabel("走纸方式：")
        self.label_scroll_mode.setFixedWidth(60)
        self.combo_scroll_mode = QtWidgets.QComboBox()
        self.combo_scroll_mode.setFixedWidth(120)
        self.combo_scroll_mode.addItem("滚动窗口", 1)   # 模式1：原来的最近5秒滚动方式
        self.combo_scroll_mode.addItem("扫屏重写", 2)   # 模式2：x轴固定，从左到右写满后回到左侧

        scroll_mode_layout = QtWidgets.QHBoxLayout()
        scroll_mode_layout.setContentsMargins(0, 0, 0, 0)
        scroll_mode_layout.setSpacing(4)
        scroll_mode_layout.addWidget(self.label_scroll_mode)
        scroll_mode_layout.addWidget(self.combo_scroll_mode)

        # ---------- 第二行整体排布 ----------
        self.channel_control_layout.addStretch()
        self.channel_control_layout.addLayout(channel_count_layout)
        self.channel_control_layout.addSpacing(16)
        self.channel_control_layout.addWidget(self.label_show_channels)
        self.channel_control_layout.addLayout(self.channel_checkbox_layout)
        self.channel_control_layout.addSpacing(16)
        self.channel_control_layout.addWidget(self.label_fs_estimated)
        self.channel_control_layout.addSpacing(16)
        self.channel_control_layout.addLayout(scroll_mode_layout)
        self.channel_control_layout.addStretch()

        # 连接通道数变化信号，并初始化
        self.combo_channel_count.currentIndexChanged.connect(self.on_channel_count_changed)
        self.on_channel_count_changed()

        # 走纸模式：1=当前滚动窗口，2=扫屏重写
        self.scroll_mode = 1
        self.combo_scroll_mode.currentIndexChanged.connect(self.on_scroll_mode_changed)

        # ===================== layout_2: pyqtgraph 曲线 =====================
        self.max_points = 1000  # 初始默认值，真正的 maxlen 会在 start 的时候按采样率重建
        self.sample_rate_hz: float | None = None  # 名义采样率（用户输入）

        # 窗口宽度（秒），两种模式统一使用
        self.window_sec = 5.0
        self.window_points = 1000
        self.sweep_x: List[float] = [
            self.window_sec * i / max(self.window_points - 1, 1)
            for i in range(self.window_points)
        ]

        # 多通道数据结构：每个通道有独立的 x/y 队列和 sample_index
        self.channel_data_x: dict[int, deque] = {}
        self.channel_data_y: dict[int, deque] = {}
        self.channel_sample_index: dict[int, int] = {}
        self.channel_curves: dict[int, pg.PlotDataItem] = {}
        self.active_channels_in_plot: set[int] = set()
        self.channel_colors = ["r", "g", "b", "c", "m", "y", "k"]

        # 第二种模式用的“扫屏缓冲区”：固定长度数组 + 写入指针
        self.sweep_buffers: dict[int, List[float]] = {}
        self.sweep_index: dict[int, int] = {}

        # 采样率估计（全局）：使用一个参考通道 + 最近 3 秒窗口
        self.reference_channel: Optional[int] = None     # 用来估计 fs 的通道
        self.ref_window = deque()                       # 存放 (hw_ts, n_samples)，仅最近 ~3 秒
        self.fs_estimated_global: float = 0.0           # 估算的实际采样率（当前 3 秒窗口）

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground("w")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.2)
        self.plot_widget.setLabel("left", "μV")
        self.plot_widget.setLabel("bottom", "Time (s)")  # x轴单位改为秒
        self.plot_widget.setYRange(-200, 200)
        self.legend = self.plot_widget.addLegend()

        # 扫屏模式下的竖直指示线
        self.sweep_line: Optional[pg.InfiniteLine] = None

        # 主布局加入：顶部一行 + 通道控制行 + 曲线
        self.main_layout.addLayout(self.layout_1)
        self.main_layout.addLayout(self.channel_control_layout)
        self.main_layout.addWidget(self.plot_widget)

        # 隐藏 IP 和“采样率(Hz)”这两个输入区域（仍然保留默认值供代码使用）
        self.label_ip.hide()
        self.input_ip.hide()
        self.label_fs.hide()
        self.input_fs.hide()

        # 信号与槽
        self.button_1.clicked.connect(self.start_udp_receiving)

        # UDP 接收器
        self.receiver: Optional[UdpEegReceiver] = None

    # -------- 工具：递归清空一个 layout（避免布局乱） --------

    def _clear_layout(self, layout: QtWidgets.QLayout):
        """递归清空一个 QLayout，确保其中 widget 和子 layout 都正确销毁"""
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            if child_layout is not None:
                self._clear_layout(child_layout)

    # -------- 通道数变化：更新 checkbox --------

    def on_channel_count_changed(self):
        """当下拉框选择通道数变化时，重新生成 checkbox"""
        # 清空旧的 checkbox
        self._clear_layout(self.channel_checkbox_layout)
        self.channel_checkboxes.clear()

        # 获取当前选择的通道数（3 或 4）
        count = self.combo_channel_count.currentData()
        if count is None:
            count = 3

        # 假定通道编号从 0 开始：0,1,2 / 0,1,2,3
        for ch in range(count):
            cb = QtWidgets.QCheckBox(f"Ch{ch}")
            cb.setChecked(True)  # 默认全选
            self.channel_checkbox_layout.addWidget(cb)
            self.channel_checkboxes[ch] = cb

    def on_scroll_mode_changed(self, index: int):
        """切换走纸方式：1=滚动窗口，2=扫屏重写"""
        mode = self.combo_scroll_mode.currentData()
        if mode in (1, 2):
            self.scroll_mode = mode

    # -------- 启动 / 停止按钮逻辑 --------

    def start_udp_receiving(self):
        """开始或停止 UDP 监听"""
        ip = self.input_ip.text().strip()
        port_str = self.input_port.text().strip()
        fs_str = self.input_fs.text().strip()

        # ====== 点击“开始检测信号” ======
        if self.button_1.text() == ButtonStates.start.value:
            # 参数检查（IP 和采样率虽然隐藏，但使用默认值即可通过）
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

            # 依据名义采样率估算窗口点数和缓冲长度
            points_for_5s = int(self.sample_rate_hz * self.window_sec)
            if points_for_5s <= 0:
                points_for_5s = 1
            self.window_points = max(points_for_5s, 1000)
            self.max_points = max(self.window_points * 2, 1000)  # deques 用更长一点的历史

            # 更新扫屏模式的 X 轴坐标
            if self.window_points > 1:
                self.sweep_x = [
                    self.window_sec * i / (self.window_points - 1)
                    for i in range(self.window_points)
                ]
            else:
                self.sweep_x = [0.0]

            # 清空旧数据（多通道）
            self.channel_data_x.clear()
            self.channel_data_y.clear()
            self.channel_sample_index.clear()
            self.channel_curves.clear()
            self.active_channels_in_plot.clear()
            self.last_plot_time = 0.0

            # 清空扫屏数据
            self.sweep_buffers.clear()
            self.sweep_index.clear()

            # 重置采样率估计（当前 3 秒窗口）
            self.reference_channel = None
            self.ref_window.clear()
            self.fs_estimated_global = 0.0
            self.label_fs_estimated.setText("采样率估计：-- Hz")

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
            # 只有在扫屏模式下显示
            self.sweep_line.setVisible(self.scroll_mode == 2)

            # UI 状态：先禁用端口输入和通道数选择 + 走纸方式（开始后不能改）
            self.input_ip.setDisabled(True)
            self.input_port.setDisabled(True)
            self.input_fs.setDisabled(True)
            self.combo_channel_count.setDisabled(True)
            self.combo_scroll_mode.setDisabled(True)

            # 如果之前有 receiver，先停掉
            if self.receiver is not None:
                self.receiver.stop()
                self.receiver.deleteLater()
                self.receiver = None

            # 创建新的 UdpEegReceiver
            self.receiver = UdpEegReceiver(host=ip, port=port, buffer_size=8192, parent=self)

            # 连接信号
            self.receiver.data_received.connect(self.on_eeg_packet)
            self.receiver.status_changed.connect(self.on_receiver_status_changed)
            self.receiver.error_occurred.connect(self.on_error)
            self.receiver.sync_established.connect(self.on_sync_established)

            # 启动
            try:
                self.receiver.start()
            except Exception as e:
                # 启动失败，恢复UI
                self.label_1.setText(f"启动UDP接收器失败: {e}")
                self.label_1.setStyleSheet("color: red")
                self.input_ip.setDisabled(False)
                self.input_port.setDisabled(False)
                self.input_fs.setDisabled(False)
                self.combo_channel_count.setDisabled(False)
                self.combo_scroll_mode.setDisabled(False)
                if self.receiver is not None:
                    self.receiver.deleteLater()
                    self.receiver = None
                return

            # 按钮 & 状态文案更新
            self.button_1.setText(ButtonStates.stop.value)
            self.label_1.setText(LabelStates.listening.value)
            self.label_1.setStyleSheet("color: #5d5d5d")

        # ====== 点击“停止检测信号” ======
        elif self.button_1.text() == ButtonStates.stop.value:
            if self.receiver is not None:
                self.receiver.stop()
                self.receiver.deleteLater()
                self.receiver = None

            # 恢复UI
            self.button_1.setText(ButtonStates.start.value)
            self.label_1.setText(LabelStates.stopped.value)
            self.label_1.setStyleSheet("color: #5d5d5d")
            self.input_ip.setDisabled(False)
            self.input_port.setDisabled(False)
            self.input_fs.setDisabled(False)
            self.combo_channel_count.setDisabled(False)
            self.combo_scroll_mode.setDisabled(False)

    # -------- 接收 EEG 数据并更新曲线（多通道 + 3 秒窗口采样率估计 + checkbox 控制） --------

    def on_eeg_packet(self, packet: EegDataPacket):
        """
        收到 UdpEegReceiver 解析好的 EegDataPacket
        逻辑：
          1. 对每一个通道分别维护 x/y 数据和 sample_index
          2. 为每个通道创建独立的曲线（不同颜色）
          3. 把所有被选中的通道的波形叠加在同一个 plot 上显示
          4. 选一个参考通道，用“最近 3 秒的硬件时间戳窗口”估算采样率：
             fs = N_samples_in_window / (t_now - t_oldest_in_window)
          5. 根据 scroll_mode，切换两种走纸方式：
             - 1：滚动窗口（当前实现）
             - 2：扫屏重写（X 轴固定，从左到右写满后从左重新写，并绘制竖直指示线）
        """
        # 安全判断（理论上不会 None，因为开始前已经检查）
        if self.sample_rate_hz is None or self.sample_rate_hz <= 0:
            return

        ch = packet.channel

        # 第一次看到这个通道 -> 初始化数据结构和曲线
        if ch not in self.channel_data_x:
            self.channel_data_x[ch] = deque(maxlen=self.max_points)
            self.channel_data_y[ch] = deque(maxlen=self.max_points)
            self.channel_sample_index[ch] = 0

            color = self.channel_colors[len(self.channel_curves) % len(self.channel_colors)]
            curve = self.plot_widget.plot(pen=color, name=f"Ch {ch}")
            self.channel_curves[ch] = curve

        # 扫屏模式下的缓冲区初始化
        if ch not in self.sweep_buffers:
            # 用 NaN 填充，未写过的位置不会画出有效波形
            self.sweep_buffers[ch] = [float("nan")] * self.window_points
            self.sweep_index[ch] = 0

        # 记录活跃通道
        self.active_channels_in_plot.add(ch)

        # 没有参考通道时，把当前通道当作参考通道
        if self.reference_channel is None:
            self.reference_channel = ch
            self.ref_window.clear()

        # -------- 1) 根据模式，把样本写入相应的数据结构 --------
        if self.scroll_mode == 1:
            # 模式1：滚动窗口（沿时间轴往前推进，显示最近 window_sec 秒）
            for v in packet.data:
                self.channel_sample_index[ch] += 1
                t_sec = self.channel_sample_index[ch] / self.sample_rate_hz
                self.channel_data_x[ch].append(t_sec)
                self.channel_data_y[ch].append(v)
        else:
            # 模式2：扫屏重写（X 轴固定，从左到右写满后从左重新写）
            if self.window_points <= 0:
                return
            idx = self.sweep_index[ch]
            for v in packet.data:
                # 写入当前采样值到扫屏缓冲区
                self.sweep_buffers[ch][idx] = v
                # 递增写指针并绕回
                idx += 1
                if idx >= self.window_points:
                    idx = 0
                # 仍然维护全局 sample_index，用于采样率估计
                self.channel_sample_index[ch] += 1
            self.sweep_index[ch] = idx

        # -------- 2) 采样率估计：与模式无关，基于参考通道硬件时间戳 --------
        if self.reference_channel == ch:
            ts_now = packet.hardware_timestamp
            n_new = len(packet.data)

            # 把当前包加入窗口
            self.ref_window.append((ts_now, n_new))

            # 移除 3 秒之前的旧数据，只保留 (ts >= ts_now - 3.0)
            window_len = 3.0
            window_start = ts_now - window_len
            while self.ref_window and self.ref_window[0][0] < window_start:
                self.ref_window.popleft()

            # 计算窗口内的样本总数和时间跨度
            if self.ref_window:
                total_samples = sum(n for (_, n) in self.ref_window)
                oldest_ts = self.ref_window[0][0]
                elapsed = ts_now - oldest_ts

                if elapsed > 0 and total_samples > 0:
                    self.fs_estimated_global = total_samples / elapsed
                    self.label_fs_estimated.setText(f"采样率估计：{self.fs_estimated_global:.1f} Hz")

        # 计算当前“显示中的通道”（勾选的那些）
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
        self.label_1.setStyleSheet("color: #008000")  # 绿色高亮

        # 刷新曲线（限频）
        now = time.time()
        if now - self.last_plot_time >= self.plot_interval:
            self.update_plot()
            self.last_plot_time = now

    def on_receiver_status_changed(self, status: str, packet_count: int, channel_info: str):
        """
        UdpEegReceiver 的状态信息（是否同步、包数、活跃通道）
        放在 label 的 tooltip 里，避免抢占主文案。
        同时附上“最近 3 秒窗口”的采样率估计。
        """
        tooltip = f"{status} | 已接收 {packet_count} 包 | {channel_info}"
        if self.fs_estimated_global > 0:
            tooltip += f" | 采样率估计: {self.fs_estimated_global:.1f} Hz"
        self.label_1.setToolTip(tooltip)

    def on_error(self, message: str):
        print("UDP 错误:", message)
        self.label_1.setText(message)
        self.label_1.setStyleSheet("color: red")

    def on_sync_established(self, offset: float):
        """
        时间同步建立时调用。
        现在只是添加到 tooltip，如果之后要用同步时间戳，可以从 receiver 获取。
        """
        current_tooltip = self.label_1.toolTip() or ""
        extra = f" | 时间同步偏移量: {offset:.6f}s"
        self.label_1.setToolTip(current_tooltip + extra)

    # -------- 重置 y 轴范围 --------

    def reset_y_axis_range(self):
        """将y轴范围重置回 -200 ~ 200 μV"""
        self.plot_widget.setYRange(-200, 200)

    # -------- 画图：两种走纸方式 --------

    def update_plot(self):
        """
        更新曲线显示：
        - 模式1：X轴为秒，固定 window_sec 秒窗口，所有“勾选”的通道叠加显示
        - 模式2：X轴固定为 [0, window_sec]，扫屏缓冲区按固定 X 坐标绘制，并显示竖直指示线
        """
        if not self.channel_curves:
            return

        # 模式1：滚动窗口
        if self.scroll_mode == 1:
            # 竖线隐藏
            if self.sweep_line is not None:
                self.sweep_line.setVisible(False)

            x_max = None

            for ch, curve in self.channel_curves.items():
                x_deque = self.channel_data_x.get(ch)
                y_deque = self.channel_data_y.get(ch)
                if not x_deque or not y_deque:
                    continue

                # 根据 checkbox 决定是否显示
                cb = self.channel_checkboxes.get(ch)
                if cb is not None and not cb.isChecked():
                    curve.setVisible(False)
                    continue
                else:
                    curve.setVisible(True)

                x_data = list(x_deque)
                y_data = list(y_deque)
                curve.setData(x=x_data, y=y_data)

                if x_data:
                    last_x = x_data[-1]
                    if x_max is None or last_x > x_max:
                        x_max = last_x

            if x_max is None:
                return

            # 固定显示最近 window_sec 秒
            window = self.window_sec
            if x_max <= window:
                self.plot_widget.setXRange(0, window)
            else:
                self.plot_widget.setXRange(x_max - window, x_max)

        else:
            # 模式2：扫屏重写，X轴固定
            self.plot_widget.setXRange(0, self.window_sec)

            for ch, curve in self.channel_curves.items():
                buf = self.sweep_buffers.get(ch)
                if buf is None or len(buf) == 0:
                    continue

                # 根据 checkbox 决定是否显示
                cb = self.channel_checkboxes.get(ch)
                if cb is not None and not cb.isChecked():
                    curve.setVisible(False)
                    continue
                else:
                    curve.setVisible(True)

                # 直接用固定的 X 坐标和当前缓冲区的 Y
                curve.setData(x=self.sweep_x, y=buf)

            # 更新竖直指示线位置
            if self.sweep_line is not None:
                self.sweep_line.setVisible(True)
                # 优先使用参考通道的写入指针
                idx = None
                if self.reference_channel is not None and self.reference_channel in self.sweep_index:
                    idx = self.sweep_index[self.reference_channel]
                else:
                    # 退而求其次：取任意一个可见通道的 index
                    if self.sweep_index:
                        idx = list(self.sweep_index.values())[0]

                if idx is not None and self.window_points > 0:
                    # 指示“最后写入”的位置：指针指向的是下一次写入的位置，所以往前挪一格
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
