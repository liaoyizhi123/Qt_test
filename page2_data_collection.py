import os
import re
import enum
import time
import struct
import socket
import random
import logging
import threading
import numpy as np
from collections import deque
from typing import List, Optional
from dataclasses import dataclass

import pyqtgraph as pg
from PyQt6 import QtWidgets
from PyQt6.QtCore import Qt, QObject, pyqtSignal


# ====================== 状态枚举 ======================


class LabelStates(enum.Enum):
    # 未监听：初始化 / 停止后的状态
    stopped = "未监听（请填写端口号后点击开始）"
    # 已开启UDP监听，但还没有收到数据
    listening = "已开启UDP监听，但还没有收到数据"
    # 已经收到数据，正在实时接收并绘图
    receiving = "正在接收EEG数据..."


class ButtonStates(enum.Enum):
    start = "开始监测信号"
    stop = "停止监测信号"


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


# ====================== EEG 数据结构 & 时间校正 ======================


@dataclass
class EegDataPacket:
    """EEG 数据包结构

    hardware_timestamp: 片上时间（秒，来自设备时间戳）
    system_timestamp:   经过 ActualTimeRegulator 校正后的“电脑时间轴”（秒）
    """
    hardware_timestamp: float
    system_timestamp: float
    data: List[float]
    packet_id: int = 0
    channel: int = 0
    raw_packet: bytes | None = None


@dataclass
class TimeRegulatingResult:
    """对应 C# 中的 TimeRegulatingResult"""
    valid: bool
    pack_skipped: bool
    regulated_time: float


class ActualTimeRegulator:
    """
    对应 C# ActualTimeRegulator：
    - pack_time：这里直接使用“秒”为单位的片上时间（C# 用的是微秒，后乘 1e-6）
    - received_at：从当前会话启动以来的 elapsed 秒（类似 Stopwatch.Elapsed.TotalSeconds）
    """

    def __init__(self, rollback_tolerance_sec: float = 0.01):
        self._first_pack_time: float = 0.0
        self._prev_pack_time: float = 0.0
        self._first_pack_computer_time: float = 0.0
        self._first_pack: bool = True
        # 当片上时间回退超过此阈值时，认为异常并重置（C# 中是 10_000 微秒）
        self._rollback_tolerance = rollback_tolerance_sec

    def reset(self):
        self._first_pack = True
        self._prev_pack_time = 0.0
        self._first_pack_time = 0.0
        self._first_pack_computer_time = 0.0

    def get_time(self, pack_time: float, received_at: float) -> TimeRegulatingResult:
        """
        :param pack_time: 片上时间（秒，已经 /1e6 处理过）
        :param received_at: 电脑侧的相对时间（秒），例如从某个起点算起的 time.monotonic()
        """
        if (not self._first_pack) and (pack_time + self._rollback_tolerance < self._prev_pack_time):
            # 片上时间明显回退，认为异常，重置状态并跳过该包
            self.reset()
            return TimeRegulatingResult(False, True, received_at)

        if self._first_pack:
            # 第一包：建立基准，只记录，不输出校正时间
            self._first_pack_time = pack_time
            self._first_pack_computer_time = received_at
            self._first_pack = False
            self._prev_pack_time = pack_time
            return TimeRegulatingResult(False, False, received_at)

        # 对齐到电脑时间轴
        regulated = (pack_time - self._first_pack_time) + self._first_pack_computer_time
        self._prev_pack_time = pack_time
        return TimeRegulatingResult(True, False, regulated)


# ====================== UDP 接收器：解包逻辑与 C# 对齐 ======================


class UdpEegReceiver(QObject):
    """
    UDP EEG数据接收器 - PyQt6版本

    解包逻辑与 C# 的 V2BufferParser 对齐：
    每个包结构（从某个索引 i 开始）：
        [0]   SensorType
        [1]   SensorType  (与 [0] 相同)
        [2-4] Serial Number (3字节)
        [5]   Channel Number (0xFF = MetaInfo)
        [6-7] DataLength (大端)
        [8 ... 8+DataLength-1]       Data 区
        [8+DataLength ... +7]        OnBoardTime 时间戳（8字节，大端 uint64，单位：微秒）
        [8+DataLength+8]             CRC8 校验和（此处暂不实际校验，只预留接口）

    总长度 = DataLength + PACK_INFO_LENGTH (17)
    """

    # PyQt6信号定义
    data_received = pyqtSignal(object)  # 发出 EegDataPacket 实例
    error_occurred = pyqtSignal(str)    # 错误发生

    PACK_INFO_LENGTH = 17  # header(8) + timestamp(8) + CRC(1)

    def __init__(
        self, host: str = "0.0.0.0", port: int = 30300, buffer_size: int = 8192, parent: Optional[QObject] = None
    ):
        super().__init__(parent)
        self.host = host
        self.port = port
        self.buffer_size = buffer_size
        self.socket: Optional[socket.socket] = None
        self.running = False
        self.packet_count = 0
        self.active_channels = set()
        self.logger = logging.getLogger("UdpEegReceiver")

        self._recv_count = 0
        self._last_stat_time = time.time()
        self.receiver_thread: Optional[threading.Thread] = None

        # 最近一次接收到的片上时间戳（秒）
        self._last_hw_timestamp: Optional[float] = None
        # 最近一次接收到的“校正后的电脑时间”（秒）——与 CSV Time 列保持一致
        self._last_regulated_ts: Optional[float] = None

        # 每个通道一个时间“纠正器”和排序缓冲区
        self._time_regulators: dict[int, ActualTimeRegulator] = {}
        self._sorted_packets: dict[int, list[tuple[float, EegDataPacket]]] = {}
        self._buffer_size_per_channel: int = 5  # 模仿 C# 中每通道凑够 5 个包后再吐出最早的一个

        # 会话起点，用于生成“电脑时间轴” received_at
        self._start_monotonic: float | None = None

        # ====== 模拟网络不稳定相关参数（默认开启丢包）======
        self.enable_loss_simulation = False   # 是否开启模拟丢包
        self.loss_rate = 0.6                 # 丢包比例（0~1）
        self.enable_jitter_simulation = False  # 是否模拟随机延迟
        self.jitter_max_delay = 0.05           # 最大延迟秒数

    def get_last_hw_timestamp(self) -> Optional[float]:
        """返回最近一次接收到的数据包的片上时间戳（秒）。如果还没有收到任何数据则返回 None。"""
        return self._last_hw_timestamp

    def get_last_regulated_timestamp(self) -> Optional[float]:
        """
        返回最近一次接收到的数据包的“校正后的电脑时间”（秒）。
        这就是 CSV 文件 Time 列所使用的时间轴。
        """
        return self._last_regulated_ts

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
            self._last_hw_timestamp = None
            self._last_regulated_ts = None

            # 重置时间纠正器与排序队列
            self._time_regulators.clear()
            self._sorted_packets.clear()

            # 会话起点（类似 C# 的 Stopwatch.StartNew()）
            self._start_monotonic = time.monotonic()

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

    # -------- 接收 & 解析循环（含时间校正 + 排序） --------

    def _receive_loop(self):
        """接收循环，在单独线程中运行"""
        while self.running:
            try:
                data, addr = self.socket.recvfrom(self.buffer_size)

                # ---- (可选) 模拟网络抖动：随机延迟一小段时间 ----
                if self.enable_jitter_simulation and self.jitter_max_delay > 0:
                    time.sleep(random.uniform(0, self.jitter_max_delay))

                # ---- (可选) 模拟 UDP 丢包：随机丢弃整个 datagram ----
                if self.enable_loss_simulation and random.random() < self.loss_rate:
                    self.logger.warning("【模拟丢包】随机丢弃 1 个 UDP datagram")
                    continue

                system_ts_wall = time.time()  # 真正的电脑时间（用于日志）
                if self._start_monotonic is not None:
                    recv_elapsed = time.monotonic() - self._start_monotonic
                else:
                    recv_elapsed = 0.0

                # 统计接收速率（仅日志用）
                self._recv_count += 1
                if self._recv_count % 100 == 0:
                    elapsed = system_ts_wall - self._last_stat_time
                    rate = 100 / elapsed if elapsed > 0 else 0
                    self.logger.info(f"UDP接收速率: {rate:.1f} packet/s (已接收{self._recv_count}个)")
                    self._last_stat_time = system_ts_wall

                # 解析一个 datagram 中可能包含的多个包
                packets = self._parse_eeg_packet(data)

                # 如果解析不到合法数据，直接跳过
                if not packets:
                    continue

                # 使用与 C# 类似的逻辑：按通道使用 ActualTimeRegulator + 排序缓冲
                for packet in packets:
                    ch = packet.channel

                    # 维护“最大片上时间”，用于上层查询
                    if self._last_hw_timestamp is None or packet.hardware_timestamp > self._last_hw_timestamp:
                        self._last_hw_timestamp = packet.hardware_timestamp

                    # 获取 / 创建通道对应的时间调节器
                    regulator = self._time_regulators.get(ch)
                    if regulator is None:
                        regulator = ActualTimeRegulator()
                        self._time_regulators[ch] = regulator

                    # 获取 / 创建通道对应的排序缓冲区
                    channel_buf = self._sorted_packets.get(ch)
                    if channel_buf is None:
                        channel_buf = []
                        self._sorted_packets[ch] = channel_buf

                    # 对应 C# regulator.GetTime(packNumber, session.Stopwatch.Elapsed.TotalSeconds)
                    reg_result = regulator.get_time(
                        pack_time=packet.hardware_timestamp,  # 秒
                        received_at=recv_elapsed,             # 秒
                    )

                    if reg_result.pack_skipped:
                        # 如果出现“片上时间倒退”，C# 会 Reset，并跳过该包
                        self.logger.warning(
                            f"通道 {ch} 监测到片上时间倒退超过阈值，本包被跳过并重置时间调节器"
                        )
                        channel_buf.clear()
                        continue

                    if not reg_result.valid:
                        # 第一包仅建立基准，不输出
                        continue

                    # 写入“校正后的电脑时间”
                    packet.system_timestamp = reg_result.regulated_time

                    # 按片上时间排序缓存（类似 SortedList<ulong, RawDataPack>）
                    channel_buf.append((packet.hardware_timestamp, packet))
                    channel_buf.sort(key=lambda x: x[0])

                    # 当该通道缓存达到一定数量后，弹出最早的一个包
                    if len(channel_buf) >= self._buffer_size_per_channel:
                        _, out_packet = channel_buf.pop(0)
                        self._emit_packet(out_packet)

            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    self.logger.error(f"接收数据时出错: {e}")
                    self.error_occurred.emit(f"接收数据时出错: {e}")

    def _emit_packet(self, packet: EegDataPacket):
        """将排序好的包发给上层（通过 signal）"""
        self.packet_count += 1
        self.active_channels.add(packet.channel)

        # 记录最近一个“校正后的电脑时间”（与 CSV Time 一致）
        if packet.system_timestamp > 0:
            self._last_regulated_ts = packet.system_timestamp

        # 直接通过信号发给上层
        self.data_received.emit(packet)

    # -------- C# 风格 UDP 解包 --------

    def _parse_eeg_packet(self, data: bytes) -> List[EegDataPacket]:
        """
        解包逻辑改成 C# V2BufferParser 的形式：
        - 包格式：
            SensorType,
            SensorType,
            Serial(3B),
            Channel,
            DataLen(2B),
            Data(DataLenB),
            Timestamp(8B, big-endian, µs),
            CRC(1B)
        - 总长度 = DataLen + PACK_INFO_LENGTH (17)
        - 假设一个 UDP datagram 内不会截断单个包（UDP 不会拆包），但可能包含多个包
        """
        packets: List[EegDataPacket] = []
        buf = data
        n = len(buf)
        i = 0

        while i + self.PACK_INFO_LENGTH <= n:
            if i + 8 > n:
                break

            sensor_type = buf[i]
            sensor_type_dup = buf[i + 1]

            # 对应 C# MatchPackInfo：两个字节相同
            if sensor_type != sensor_type_dup:
                i += 1
                continue

            # DataLength（大端）
            data_len = (buf[i + 6] << 8) | buf[i + 7]
            if data_len <= 0:
                i += 1
                continue

            total_len = data_len + self.PACK_INFO_LENGTH
            pack_end = i + total_len - 1
            if pack_end >= n:
                # 剩余数据不足一个完整包
                break

            # CRC 校验暂不实现（缺少多项式等信息），只保留结构
            frame_data = buf[i: pack_end + 1]
            packet = self._parse_single_channel_frame(frame_data)
            if packet is not None:
                packets.append(packet)

            i = pack_end + 1  # 跳到下一个候选包起点

        return packets

    def _parse_single_channel_frame(self, frame_data: bytes) -> Optional[EegDataPacket]:
        """解析单个通道的数据帧（对应 C# 中对单个 Pack 的处理逻辑）"""
        try:
            if len(frame_data) < self.PACK_INFO_LENGTH:
                return None

            # --- 头部：SensorType / Serial / Channel / DataLength ---
            sensor_type = frame_data[0]
            sensor_type_dup = frame_data[1]
            if sensor_type != sensor_type_dup:
                return None

            # 传感器序列号（3 字节）
            serial_raw = (frame_data[2] << 16) | (frame_data[3] << 8) | frame_data[4]

            # 通道号
            channel = frame_data[5]

            # meta 信息（Channel == 0xFF）在 C# 中走 SendToMetaWarehouse，这里直接忽略
            if channel == 0xFF:
                return None

            # 数据长度（大端）
            data_length = (frame_data[6] << 8) | frame_data[7]
            expected_len = data_length + self.PACK_INFO_LENGTH
            if len(frame_data) != expected_len:
                return None

            # --- 时间戳：8 + DataLen 开始的 8 字节，big-endian 微秒 ---
            timestamp_offset = 8 + data_length
            if timestamp_offset + 8 > len(frame_data):
                return None

            hardware_ts_raw = struct.unpack(">Q", frame_data[timestamp_offset: timestamp_offset + 8])[0]
            # 微秒 -> 秒
            hardware_ts = hardware_ts_raw / 1_000_000.0

            # --- 数据区：从 8 开始，长度 data_length ---
            data_bytes = frame_data[8: 8 + data_length]
            data_point_count = data_length // 3
            samples: List[float] = []

            for j in range(data_point_count):
                base = j * 3
                if base + 2 >= len(data_bytes):
                    break
                b1 = data_bytes[base]
                b2 = data_bytes[base + 1]
                b3 = data_bytes[base + 2]

                # 24bit 转 32bit 有符号整数
                if (b1 & 0x80) != 0:
                    raw_value = (b1 << 16) | (b2 << 8) | b3 | (0xFF << 24)
                else:
                    raw_value = (b1 << 16) | (b2 << 8) | b3

                if raw_value >= 0x80000000:
                    raw_value -= 0x100000000

                microvolts = raw_value / 1000.0
                samples.append(microvolts)

            if not samples:
                return None

            return EegDataPacket(
                hardware_timestamp=hardware_ts,
                system_timestamp=0.0,  # 占位，后续由 ActualTimeRegulator 覆盖
                data=samples,
                channel=channel,
                raw_packet=frame_data,
            )

        except Exception as e:
            self.logger.error(f"解析单通道数据帧失败: {e}")
            return None


# ====================== Page2：使用新的 UdpEegReceiver ======================


class Page2Widget(QtWidgets.QWidget):
    """
    页面2：实时显示 UDP EEG 数据
    - 自动解析多通道
    - 显示所有活跃通道的波形（叠加在同一个图上）
    - 通过下拉框选择通道数（3/4），通过 checkbox 动态控制每个通道是否显示
    - 支持两种走纸方式：滚动窗口 / 扫屏重写（带竖直指示线）
    - 支持简单的数据保存为 CSV
    """

    def __init__(self, parent=None):
        super(Page2Widget, self).__init__(parent)

        # ========= 默认数据目录 =========
        self.default_data_dir = "data"
        self.data_dir = self.default_data_dir
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

        # ===================== 顶部控件行 =====================

        # ---------- 端口 ----------
        self.label_port = QtWidgets.QLabel("端口：")
        # self.label_port.setFixedHeight(28)
        self.label_port.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

        self.input_port = QtWidgets.QLineEdit()
        self.input_port.setFixedWidth(80)
        self.input_port.setPlaceholderText("例如 30300")
        self.input_port.setText("30300")

        port_layout = QtWidgets.QHBoxLayout()
        port_layout.setContentsMargins(0, 0, 0, 0)
        port_layout.setSpacing(4)
        port_layout.addWidget(self.label_port)
        port_layout.addWidget(self.input_port)

        # ---------- 通道数 ----------
        self.label_channel_count = QtWidgets.QLabel("通道数：")
        # self.label_channel_count.setFixedWidth(60)
        # self.label_channel_count.setFixedHeight(28)

        self.combo_channel_count = QtWidgets.QComboBox()
        self.combo_channel_count.setFixedWidth(80)
        self.combo_channel_count.addItem("3", 3)
        self.combo_channel_count.addItem("4", 4)

        channel_count_layout = QtWidgets.QHBoxLayout()
        channel_count_layout.setContentsMargins(0, 0, 0, 0)
        channel_count_layout.setSpacing(4)
        channel_count_layout.addWidget(self.label_channel_count)
        channel_count_layout.addWidget(self.combo_channel_count)

        # ---------- 显示通道（checkbox） ----------
        self.label_show_channels = QtWidgets.QLabel("显示通道：")
        # self.label_show_channels.setFixedHeight(28)
        self.label_show_channels.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

        self.channel_checkbox_layout = QtWidgets.QHBoxLayout()
        self.channel_checkbox_layout.setContentsMargins(0, 0, 0, 0)
        self.channel_checkbox_layout.setSpacing(8)

        self.channel_checkboxes: dict[int, QtWidgets.QCheckBox] = {}

        show_channels_layout = QtWidgets.QHBoxLayout()
        show_channels_layout.setContentsMargins(0, 0, 0, 0)
        show_channels_layout.setSpacing(4)
        show_channels_layout.addWidget(self.label_show_channels)
        show_channels_layout.addLayout(self.channel_checkbox_layout)

        # ---------- 绘图降采样 ----------
        self.checkbox_downsample_plot = QtWidgets.QCheckBox("绘图降采样1/5")
        self.checkbox_downsample_plot.setChecked(False)

        downsample_layout = QtWidgets.QHBoxLayout()
        downsample_layout.setContentsMargins(0, 0, 0, 0)
        downsample_layout.setSpacing(4)
        downsample_layout.addWidget(self.checkbox_downsample_plot)

        # ---------- 走纸方式 ----------
        self.label_scroll_mode = QtWidgets.QLabel("走纸方式：")
        # self.label_scroll_mode.setFixedHeight(28)

        self.combo_scroll_mode = QtWidgets.QComboBox()
        self.combo_scroll_mode.setFixedWidth(120)
        self.combo_scroll_mode.addItem("滚动窗口", 1)
        self.combo_scroll_mode.addItem("扫屏重写", 2)

        scroll_mode_layout = QtWidgets.QHBoxLayout()
        scroll_mode_layout.setContentsMargins(0, 0, 0, 0)
        scroll_mode_layout.setSpacing(4)
        scroll_mode_layout.addWidget(self.label_scroll_mode)
        scroll_mode_layout.addWidget(self.combo_scroll_mode)

        # ---------- 顶部整行 ----------
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
        self.top_controls_layout.addLayout(downsample_layout)
        self.top_controls_layout.addSpacing(16)
        self.top_controls_layout.addLayout(scroll_mode_layout)
        self.top_controls_layout.addStretch()

        # ===================== 第二行：按钮 + 状态 =====================

        # 重置 y 轴范围按钮
        self.button_reset_y = QtWidgets.QPushButton("重置y轴范围")
        self.button_reset_y.setFixedWidth(110)

        # 开始/停止监测信号按钮
        self.button_1 = QtWidgets.QPushButton(ButtonStates.start.value)
        self.button_1.setFixedWidth(160)

        # 开始保存数据按钮
        self.button_save = QtWidgets.QPushButton("开始保存数据")
        self.button_save.setFixedWidth(220)
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
        # self.label_1.setFixedHeight(28)
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
        self.plot_downsample_step = 5

        self.window_sec = 5.0
        self.window_points = 1000
        self.sweep_x: List[float] = [
            self.window_sec * i / max(self.window_points - 1, 1)
            for i in range(self.window_points)
        ]

        self.channel_data_x: dict[int, deque] = {}
        self.channel_data_y: dict[int, deque] = {}
        self.channel_sample_index: dict[int, int] = {}
        self.channel_curves: dict[int, pg.PlotDataItem] = {}
        self.active_channels_in_plot: set[int] = set()
        self.channel_colors = ["r", "g", "b", "c", "m", "y", "k"]

        # 旧扫屏模式用的 buffer/index，保留属性但不再使用
        self.sweep_buffers: dict[int, List[float]] = {}
        self.sweep_index: dict[int, int] = {}

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground("w")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.2)
        self.plot_widget.setLabel("left", "μV")
        self.plot_widget.setLabel("bottom", "Time (s)")
        self.plot_widget.setYRange(-200, 200)
        self.legend = self.plot_widget.addLegend()

        # 扫屏模式下的竖直指示线
        self.sweep_line: Optional[pg.InfiniteLine] = None

        # 主布局
        self.main_layout.addLayout(self.top_controls_layout)
        self.main_layout.addLayout(self.bottom_controls_layout)
        self.main_layout.addWidget(self.plot_widget)

        # 默认走纸模式：2 = 扫屏重写
        self.scroll_mode = 2
        self.combo_scroll_mode.setCurrentIndex(1)
        self.combo_scroll_mode.currentIndexChanged.connect(self.on_scroll_mode_changed)

        # 通道数变化 -> checkbox
        self.combo_channel_count.currentIndexChanged.connect(self.on_channel_count_changed)
        self.on_channel_count_changed()

        # ===== IP 和采样率输入控件（只用默认值，不参与布局） =====
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

        # 隐藏 IP 和采样率输入控件
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

        # ===== 保存数据相关 =====
        self.is_saving: bool = False
        self.channel_save_files: dict[int, object] = {}   # ch -> file
        self.channel_save_index: dict[int, int] = {}      # ch -> sample index
        self.marker_file: Optional[object] = None         # markers.csv 文件句柄

    # -------- 工具：递归清空一个 layout --------

    def _clear_layout(self, layout: QtWidgets.QLayout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            if child_layout is not None:
                self._clear_layout(child_layout)

    # -------- 时间展开的小工具函数 --------

    def _expand_packet_times(self, packet: EegDataPacket) -> List[float]:
        """
        根据当前 sample_rate_hz，将一个包里的采样点展开成逐点时间列表。
        - 使用与 CSV / Page4 相同的“校正电脑时间轴”（系统时间）。
        - 约定 packet.system_timestamp 为“本包最后一个采样点”的时间。
        返回长度 == len(packet.data)。若采样率无效或数据为空则返回 []。
        """
        if self.sample_rate_hz is None or self.sample_rate_hz <= 0:
            return []

        samples = packet.data
        n = len(samples)
        if n == 0:
            return []

        dt_s = 1.0 / self.sample_rate_hz

        # 基准时间：本包“最后一个采样点”的电脑时间
        base_ts = packet.system_timestamp if packet.system_timestamp > 0 else packet.hardware_timestamp

        if dt_s > 0:
            # 第一个采样点时间 = 最后一个点时间 - (n-1)*dt
            t_first = base_ts - (n - 1) * dt_s
        else:
            t_first = base_ts

        return [t_first + j * dt_s for j in range(n)]

    # -------- 根据数据帧解析传感器序列号 --------

    def _parse_sensor_serial(self, frame_data: bytes) -> str:
        """
        根据数据帧解析传感器序列号：
        示例：使用第 2~4 字节作为 3 字节无符号整数，格式化为 6 位十进制。
        """
        try:
            if len(frame_data) < 5:
                return "000000"

            raw = (frame_data[2] << 16) | (frame_data[3] << 8) | frame_data[4]
            serial_int = raw & 0xFFFFFF
            serial_str = f"{serial_int:06d}"
            return serial_str
        except Exception as e:
            print("解析传感器序列号失败:", e)
            return "000000"

    # -------- 通道数变化：更新 checkbox --------

    def on_channel_count_changed(self):
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
        mode = self.combo_scroll_mode.currentData()
        if mode in (1, 2):
            self.scroll_mode = mode

    # -------- 启动 / 停止按钮逻辑 --------

    def start_udp_receiving(self):
        ip = self.input_ip.text().strip()
        port_str = self.input_port.text().strip()
        fs_str = self.input_fs.text().strip()

        # 开始
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

            # 扫屏指示线
            from pyqtgraph import mkPen
            self.sweep_line = pg.InfiniteLine(
                angle=90,
                movable=False,
                pen=mkPen(color=(200, 0, 150), width=2, style=Qt.PenStyle.DashLine),
            )
            self.plot_widget.addItem(self.sweep_line)
            self.sweep_line.setVisible(self.scroll_mode == 2)

            # UI 禁用
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
            self.receiver.error_occurred.connect(self.on_error)

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
                if self.receiver is not None:
                    self.receiver.deleteLater()
                    self.receiver = None
                return

            self.button_1.setText(ButtonStates.stop.value)
            self.label_1.setText(LabelStates.listening.value)
            self.label_1.setStyleSheet("color: #5d5d5d")

            self.stop_saving()
            self.button_save.setEnabled(True)

        # 停止
        elif self.button_1.text() == ButtonStates.stop.value:
            if self.receiver is not None:
                self.receiver.stop()
                self.receiver.deleteLater()
                self.receiver = None

            self.stop_saving()
            self.button_save.setEnabled(False)

            self.button_1.setText(ButtonStates.start.value)
            self.label_1.setText(LabelStates.stopped.value)
            self.label_1.setStyleSheet("color: #5d5d5d")
            self.input_ip.setDisabled(False)
            self.input_port.setDisabled(False)
            self.input_fs.setDisabled(False)
            self.combo_channel_count.setDisabled(False)
            self.combo_scroll_mode.setDisabled(False)

    # -------- 接收 EEG 数据并更新曲线 + 保存 --------

    def on_eeg_packet(self, packet: EegDataPacket):
        """
        收到 UdpEegReceiver 解析好的 EegDataPacket
        - packet.hardware_timestamp：片上时间（秒）
        - packet.system_timestamp：经过 ActualTimeRegulator 校正后的电脑时间（秒）
        当前绘图和保存都以“校正后的电脑时间轴”为准（packet.system_timestamp 展开）。
        """
        if self.sample_rate_hz is None or self.sample_rate_hz <= 0:
            return

        ch = packet.channel

        # 第一次收到数据时，解析传感器序列号
        if (not self._sensor_serial_parsed) and packet.raw_packet:
            self.sensor_serial = self._parse_sensor_serial(packet.raw_packet)
            self._sensor_serial_parsed = True
            print(f"数据来自传感器序列号: {self.sensor_serial}")

        # 保存数据
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

        self.active_channels_in_plot.add(ch)

        # ===== 使用工具函数展开时间轴 =====
        times = self._expand_packet_times(packet)
        if not times:
            return

        for t_s, v in zip(times, packet.data):
            self.channel_sample_index[ch] += 1
            self.channel_data_x[ch].append(t_s)
            self.channel_data_y[ch].append(v)

        now = time.time()
        if now - self.last_plot_time >= self.plot_interval:
            # 当前显示通道列表
            channels_sorted = sorted(self.active_channels_in_plot)
            visible_channels = []
            for c in channels_sorted:
                cb = self.channel_checkboxes.get(c)
                if cb is None or cb.isChecked():
                    visible_channels.append(c)

            # 只在重绘时更新状态文字 + 颜色
            self.label_1.setText(
                f"{LabelStates.receiving.value} 当前显示通道: {visible_channels}"
            )
            self.label_1.setStyleSheet("color: #008000")

            self.update_plot()
            self.last_plot_time = now

    # -------- 保存按钮逻辑 --------

    def toggle_save_data(self):
        if not self.is_saving:
            self.start_saving()
        else:
            self.stop_saving()

    def start_saving(self, save_dir: str | None = None):
        """
        开始保存数据：创建 CSV 文件和 markers.csv
        - save_dir 为 None 时：使用 self.data_dir（默认 "data"）
        """
        if self.is_saving:
            return

        if not self.is_listening():
            self.label_1.setText("请先点击“开始监测信号”再启动数据保存")
            self.label_1.setStyleSheet("color: red")
            return

        if self.sample_rate_hz is None or self.sample_rate_hz <= 0:
            self.label_1.setText("采样率无效，无法开始保存数据")
            self.label_1.setStyleSheet("color: red")
            return

        if save_dir is not None:
            self.data_dir = save_dir
        else:
            self.data_dir = self.default_data_dir
        os.makedirs(self.data_dir, exist_ok=True)

        self.is_saving = True
        self.channel_save_files.clear()
        self.channel_save_index.clear()

        # 创建 markers.csv
        try:
            marker_path = os.path.join(self.data_dir, "markers.csv")
            self.marker_file = open(marker_path, "w", encoding="utf-8", newline="")
            self.marker_file.write("Time,marker_index\n")
        except Exception as e:
            print("创建 markers.csv 失败:", e)
            self.marker_file = None

        self.button_save.setText("暂停保存数据，并落盘")

    def stop_saving(self):
        if not self.is_saving:
            return

        for f in self.channel_save_files.values():
            try:
                f.close()
            except Exception:
                pass
        self.channel_save_files.clear()
        self.channel_save_index.clear()

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
        时间轴按“校正后的电脑时间（system_timestamp）+ 采样率”展开。
        """
        ch = packet.channel

        if ch not in self.channel_save_files:
            serial_str = getattr(self, "sensor_serial", "xxxxxx")
            filename = os.path.join(self.data_dir, f"EEG_{serial_str}_{ch:02d}.csv")
            try:
                f = open(filename, "w", encoding="utf-8", newline="")
                f.write("Time,Response\n")
                self.channel_save_files[ch] = f
                self.channel_save_index[ch] = 0
            except Exception as e:
                print(f"打开通道 {ch} 的 CSV 文件失败:", e)
                return

        f = self.channel_save_files[ch]

        # 使用同一套时间展开逻辑，保证 CSV 时间轴与绘图一致
        times = self._expand_packet_times(packet)
        if not times:
            return

        samples = packet.data
        idx = self.channel_save_index.get(ch, 0)

        for t_s, v in zip(times, samples):
            f.write(f"{t_s:.6f},{v:.6f}\n")

            # 简单示例：在 ch==0 的每个点写一个 marker=0（你后面可以按需要修改逻辑）
            if ch == 0 and self.marker_file is not None:
                self.marker_file.write(f"{t_s:.6f},0\n")

            idx += 1

        self.channel_save_index[ch] = idx

    # -------- 其他 UI 回调 --------

    def on_error(self, message: str):
        print("UDP 错误:", message)
        self.label_1.setText(message)
        self.label_1.setStyleSheet("color: red")

    # -------- 提供给其他页面的辅助方法 --------

    def is_listening(self) -> bool:
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

    def get_last_eeg_time(self) -> Optional[float]:
        """
        获取最近一次接收到的 EEG 时间（秒）：
        使用的是与 CSV Time 列一致的“校正后的电脑时间轴”。
        """
        if self.receiver is None:
            return None
        getter = getattr(self.receiver, "get_last_regulated_timestamp", None)
        if getter is None:
            return None
        try:
            return getter()
        except Exception:
            return None

    # -------- 重置 y 轴范围 --------

    def reset_y_axis_range(self):
        self.plot_widget.setYRange(-200, 200)

    # -------- 画图：两种走纸方式 + 可选 1/5 降采样 --------

    def update_plot(self):
        if not self.channel_curves:
            return

        # 1. 统一获取需要的数据，避免多次查询
        # 将 deque 转换为 numpy array 是加速的第一步
        # 即使这里有一次拷贝，后续的数学运算也比 Python 循环快得多
        data_map = {}
        t_max = 0.0
        
        # 筛选出需要绘制的通道
        visible_channels = []
        for ch, curve in self.channel_curves.items():
            cb = self.channel_checkboxes.get(ch)
            if cb is not None and cb.isChecked():
                # 检查数据是否为空
                if self.channel_data_x[ch]:
                    visible_channels.append((ch, curve))
                    t_max = max(t_max, self.channel_data_x[ch][-1])
            else:
                curve.setVisible(False)
        
        if not visible_channels:
            return

        window = self.window_sec
        downsample = self.checkbox_downsample_plot.isChecked()
        step = self.plot_downsample_step if downsample else 1

        # ================= Mode 1: 滚动窗口 (Scrolling) =================
        if self.scroll_mode == 1:
            if self.sweep_line is not None:
                self.sweep_line.setVisible(False)

            # 更新 X 轴范围
            min_x = t_max - window
            if min_x < 0: min_x = 0
            self.plot_widget.setXRange(min_x, max(min_x + window, 0.001), padding=0)

            for ch, curve in visible_channels:
                curve.setVisible(True)
                
                # 转为 numpy 数组
                x_arr = np.array(self.channel_data_x[ch])
                y_arr = np.array(self.channel_data_y[ch])

                # 降采样 (切片操作在 numpy 中是瞬时的)
                if step > 1:
                    x_arr = x_arr[::step]
                    y_arr = y_arr[::step]
                
                # 直接设置数据，pyqtgraph 处理 numpy 极快
                curve.setData(x_arr, y_arr)

        # ================= Mode 2: 扫屏重写 (Sweep / Oscilloscope) =================
        else:
            if self.sweep_line is not None:
                self.sweep_line.setVisible(True)
                line_pos = t_max % window
                self.sweep_line.setValue(line_pos)

            # 固定 X 轴
            self.plot_widget.setXRange(0, window, padding=0)
            
            # 计算有效时间起点
            start_valid_time = t_max - window

            for ch, curve in visible_channels:
                curve.setVisible(True)

                x_arr = np.array(self.channel_data_x[ch])
                y_arr = np.array(self.channel_data_y[ch])

                # 1. 过滤：只取最近 window 秒的数据
                # 使用 numpy 布尔索引，比列表推导式快
                mask = x_arr > start_valid_time
                x_roi = x_arr[mask]
                y_roi = y_arr[mask]
                
                if len(x_roi) == 0:
                    curve.setData([], [])
                    continue

                # 2. 降采样
                if step > 1:
                    x_roi = x_roi[::step]
                    y_roi = y_roi[::step]

                # 3. 向量化计算取模 (扫屏的核心优化)
                # 直接对整个数组进行取模运算
                x_mod = x_roi % window

                # 4. 处理回绕 (Wrap-around) 断点
                # 找到当前点比前一个点小的地方 (说明跨越了窗口右边界回到左边)
                # diff < 0 的位置就是回绕点
                diffs = np.diff(x_mod)
                # np.where 返回的是 tuple
                wrap_indices = np.where(diffs < 0)[0]
                
                if len(wrap_indices) > 0:
                    # 我们需要在回绕处插入 NaN 来断开连线
                    # 索引 + 1 是因为 diff 的长度比原数组少 1，且我们要插在突变点之后
                    insert_idx = wrap_indices + 1
                    
                    # 插入 NaN
                    x_draw = np.insert(x_mod, insert_idx, np.nan)
                    y_draw = np.insert(y_roi, insert_idx, np.nan)
                else:
                    x_draw = x_mod
                    y_draw = y_roi

                # connect="finite" 配合 numpy 的 NaN 使用，性能最佳
                curve.setData(x_draw, y_draw, connect="finite")

    # -------- 生命周期清理 --------

    def closeEvent(self, event):
        if self.receiver is not None:
            self.receiver.stop()
            self.receiver.deleteLater()
            self.receiver = None

        if self.is_saving:
            self.stop_saving()

        event.accept()


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    app = QtWidgets.QApplication(sys.argv)
    w = Page2Widget()
    w.resize(1000, 700)
    w.show()
    sys.exit(app.exec())

