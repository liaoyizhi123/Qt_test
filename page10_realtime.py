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
from typing import List, Optional, Dict, Tuple

from pathlib import Path

import yaml
import torch
import joblib
import numpy as np
from scipy.signal import resample

from PyQt6 import QtWidgets
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QTimer
import pyqtgraph as pg

from models.models import build_model
from braindecode.models import EEGNet
from process.process import bandpass_filter
from training_helpers import EEGAnalyzer


# ====================== 状态枚举 ======================

class LabelStates(enum.Enum):
    stopped = "未监听（请填写端口号后点击开始）"
    listening = "已开启UDP监听，但还没有收到数据"
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
    try:
        v = float(fs)
        return v > 0
    except ValueError:
        return False


# ====================== 数据结构 & 时间校正 ======================

@dataclass
class EegDataPacket:
    hardware_timestamp: float
    system_timestamp: float
    data: List[float]
    packet_id: int = 0
    channel: int = 0
    raw_packet: Optional[bytes] = None


@dataclass
class TimeRegulatingResult:
    valid: bool
    pack_skipped: bool
    regulated_time: float


class ActualTimeRegulator:
    def __init__(self, rollback_tolerance_sec: float = 0.01):
        self._first_pack_time: float = 0.0
        self._prev_pack_time: float = 0.0
        self._first_pack_computer_time: float = 0.0
        self._first_pack: bool = True
        self._rollback_tolerance = rollback_tolerance_sec

    def reset(self):
        self._first_pack = True
        self._prev_pack_time = 0.0
        self._first_pack_time = 0.0
        self._first_pack_computer_time = 0.0

    def get_time(self, pack_time: float, received_at: float) -> TimeRegulatingResult:
        if (not self._first_pack) and (pack_time + self._rollback_tolerance < self._prev_pack_time):
            self.reset()
            return TimeRegulatingResult(False, True, received_at)
        if self._first_pack:
            self._first_pack_time = pack_time
            self._first_pack_computer_time = received_at
            self._first_pack = False
            self._prev_pack_time = pack_time
            return TimeRegulatingResult(False, False, received_at)
        regulated = (pack_time - self._first_pack_time) + self._first_pack_computer_time
        self._prev_pack_time = pack_time
        return TimeRegulatingResult(True, False, regulated)


# ====================== UDP 接收器（与 page2 对齐） ======================

class UdpEegReceiver(QObject):
    data_received = pyqtSignal(object)
    error_occurred = pyqtSignal(str)

    PACK_INFO_LENGTH = 17

    def __init__(self, host: str = "0.0.0.0", port: int = 30300, buffer_size: int = 8192,
                 parent: Optional[QObject] = None):
        super().__init__(parent)
        self.host = host
        self.port = port
        self.buffer_size = buffer_size
        self.socket: Optional[socket.socket] = None
        self.running = False
        self.data_queue: "queue.Queue[EegDataPacket]" = queue.Queue()
        self.packet_count = 0
        self.active_channels = set()
        self.logger = logging.getLogger("UdpEegReceiver")

        self._recv_count = 0
        self._last_stat_time = time.time()
        self.receiver_thread: Optional[threading.Thread] = None

        self._last_hw_timestamp: Optional[float] = None
        self._last_regulated_ts: Optional[float] = None

        self._time_regulators: Dict[int, ActualTimeRegulator] = {}
        self._sorted_packets: Dict[int, List[Tuple[float, EegDataPacket]]] = {}
        self._buffer_size_per_channel: int = 5

        self._start_monotonic: Optional[float] = None

    def get_last_hw_timestamp(self) -> Optional[float]:
        return self._last_hw_timestamp

    def get_last_regulated_timestamp(self) -> Optional[float]:
        return self._last_regulated_ts

    def is_running(self) -> bool:
        return self.running

    def start(self):
        if self.running:
            self.logger.warning("接收器已经在运行中")
            return
        try:
            self.running = True
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2 * 1024 * 1024)
                actual_buffer = self.socket.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
                self.logger.info(f"Socket接收缓冲区大小: {actual_buffer} 字节")
            except Exception as e:
                self.logger.warning(f"设置socket缓冲区失败: {e}")
            self.socket.bind((self.host, self.port))
            self.socket.settimeout(0.1)

            self._recv_count = 0
            self._last_stat_time = time.time()
            self._last_hw_timestamp = None
            self._last_regulated_ts = None
            self._time_regulators.clear()
            self._sorted_packets.clear()
            self._start_monotonic = time.monotonic()

            self.receiver_thread = threading.Thread(target=self._receive_loop, daemon=True,
                                                    name="UDP-Receiver-Thread")
            self.receiver_thread.start()
            self.logger.info(f"UDP接收器已启动，监听 {self.host}:{self.port}")
        except Exception as e:
            self.running = False
            self.logger.error(f"启动UDP接收器失败: {e}")
            self.error_occurred.emit(f"启动UDP接收器失败: {e}")
            raise

    def stop(self):
        if not self.running:
            return
        self.running = False
        if self.socket:
            self.socket.close()
            self.socket = None
        if self.receiver_thread and self.receiver_thread.is_alive():
            self.receiver_thread.join(timeout=2.0)
        self.logger.info("UDP接收器已停止")

    def _receive_loop(self):
        while self.running:
            try:
                data, addr = self.socket.recvfrom(self.buffer_size)
                system_ts_wall = time.time()
                if self._start_monotonic is not None:
                    recv_elapsed = time.monotonic() - self._start_monotonic
                else:
                    recv_elapsed = 0.0

                self._recv_count += 1
                if self._recv_count % 100 == 0:
                    elapsed = system_ts_wall - self._last_stat_time
                    rate = 100 / elapsed if elapsed > 0 else 0
                    self.logger.info(f"UDP接收速率: {rate:.1f} packet/s (已接收{self._recv_count}个)")
                    self._last_stat_time = system_ts_wall

                packets = self._parse_eeg_packet(data)
                if not packets:
                    continue

                for packet in packets:
                    ch = packet.channel
                    if self._last_hw_timestamp is None or packet.hardware_timestamp > self._last_hw_timestamp:
                        self._last_hw_timestamp = packet.hardware_timestamp

                    regulator = self._time_regulators.get(ch)
                    if regulator is None:
                        regulator = ActualTimeRegulator()
                        self._time_regulators[ch] = regulator

                    channel_buf = self._sorted_packets.get(ch)
                    if channel_buf is None:
                        channel_buf = []
                        self._sorted_packets[ch] = channel_buf

                    reg_result = regulator.get_time(
                        pack_time=packet.hardware_timestamp,
                        received_at=recv_elapsed,
                    )

                    if reg_result.pack_skipped:
                        self.logger.warning(
                            f"通道 {ch} 监测到片上时间倒退超过阈值，本包被跳过并重置时间调节器"
                        )
                        channel_buf.clear()
                        continue

                    if not reg_result.valid:
                        continue

                    packet.system_timestamp = reg_result.regulated_time

                    channel_buf.append((packet.hardware_timestamp, packet))
                    channel_buf.sort(key=lambda x: x[0])

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
        self.packet_count += 1
        self.active_channels.add(packet.channel)
        if packet.system_timestamp > 0:
            self._last_regulated_ts = packet.system_timestamp
        self.data_queue.put(packet)
        self.data_received.emit(packet)

    def _parse_eeg_packet(self, data: bytes) -> List[EegDataPacket]:
        packets: List[EegDataPacket] = []
        buf = data
        n = len(buf)
        i = 0

        while i + self.PACK_INFO_LENGTH <= n:
            if i + 8 > n:
                break
            sensor_type = buf[i]
            sensor_type_dup = buf[i + 1]
            if sensor_type != sensor_type_dup:
                i += 1
                continue

            data_len = (buf[i + 6] << 8) | buf[i + 7]
            if data_len <= 0:
                i += 1
                continue

            total_len = data_len + self.PACK_INFO_LENGTH
            pack_end = i + total_len - 1
            if pack_end >= n:
                break

            frame_data = buf[i: pack_end + 1]
            packet = self._parse_single_channel_frame(frame_data)
            if packet is not None:
                packets.append(packet)

            i = pack_end + 1

        return packets

    def _parse_single_channel_frame(self, frame_data: bytes) -> Optional[EegDataPacket]:
        try:
            if len(frame_data) < self.PACK_INFO_LENGTH:
                return None

            sensor_type = frame_data[0]
            sensor_type_dup = frame_data[1]
            if sensor_type != sensor_type_dup:
                return None

            serial_raw = (frame_data[2] << 16) | (frame_data[3] << 8) | frame_data[4]
            channel = frame_data[5]
            if channel == 0xFF:
                return None

            data_length = (frame_data[6] << 8) | frame_data[7]
            expected_len = data_length + self.PACK_INFO_LENGTH
            if len(frame_data) != expected_len:
                return None

            timestamp_offset = 8 + data_length
            if timestamp_offset + 8 > len(frame_data):
                return None

            hardware_ts_raw = struct.unpack(">Q", frame_data[timestamp_offset: timestamp_offset + 8])[0]
            hardware_ts = hardware_ts_raw / 1_000_000.0

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
                system_timestamp=0.0,
                data=samples,
                channel=channel,
                raw_packet=frame_data,
            )
        except Exception as e:
            self.logger.error(f"解析单通道数据帧失败: {e}")
            return None


# ====================== 模型推理相关 ======================

class ModelInference:
    def __init__(self, device, args, logger, param_grid, dataset_configs, training_config):
        self.logger = logger
        self.device = device
        self.args = args
        self.scaler = joblib.load(args.scaler_path)
        # X_train_sudeo: (N, 1, C, T_target)
        X_train_sudeo = torch.randn(8, 1, 3, int(args.target_fs * args.window_duration))
        self.model = build_model(
            training_config['model'],
            X_train_sudeo,
            len(dataset_configs['dataset']['annotations']['label_projection']),
            device,
        )
        self.load_model_weights()
        self.model.to(self.device)
        self.model.eval()

    def load_model_weights(self):
        state_dict = torch.load(self.args.model_path, map_location=self.device)
        try:
            self.model.load_state_dict(state_dict)
        except RuntimeError as e:
            self.logger.error(f"Failed to load weights. Possible mismatch: {e}")
            raise RuntimeError(f"Failed to load weights. Possible mismatch: {e}")
        self.logger.info(f"Pretrained model loaded from {self.args.model_path}")

    def predict(self, features, dataset_configs):
        """
        返回：
        - pred_name: 最高概率类别名称
        - prob_dict: {类别名: 概率(float)}，包含所有类别
        """
        X_data = features[np.newaxis, np.newaxis, :, :]
        with torch.no_grad():
            _sample, _channel_cv, _channel, _time = X_data.shape
            X_data = self.scaler.transform(X_data.reshape(_sample, -1)).reshape(
                _sample, _channel_cv, _channel, _time
            )
            X_data = X_data.astype(np.float32)
            x = torch.FloatTensor(X_data).to(self.device)
            if isinstance(self.model, EEGNet):
                x = x.permute(0, 2, 3, 1)
            outputs = self.model(x)
            probabilities = torch.softmax(outputs, dim=1)

            label_list = dataset_configs['dataset']['annotations']['label_projection']
            prob_vec = probabilities[0].detach().cpu().numpy()

            # 确保长度匹配
            n_classes = min(len(label_list), prob_vec.shape[0])
            prob_dict = {label_list[i]: float(prob_vec[i]) for i in range(n_classes)}

            pred_class = int(torch.argmax(probabilities, dim=1).item())
            if pred_class >= n_classes:
                pred_class = 0
            pred_name = label_list[pred_class]

            return pred_name, prob_dict


class EEGBufferProcessor:
    """
    3 秒滑动缓冲池，用于推理（不影响画图）
    """

    def __init__(self, incoming_fs, window_duration, n_channels):
        self.incoming_fs = int(incoming_fs)
        self.window_duration = float(window_duration)
        self.n_channels = int(n_channels)
        self.window_samples = int(self.incoming_fs * self.window_duration)
        self.buffer = np.zeros((self.n_channels, self.window_samples))
        self.sample_counts = np.zeros(self.n_channels, dtype=int)

    def update_channel_buffer(self, ch: int, new_samples: np.ndarray):
        if ch < 0 or ch >= self.n_channels:
            return
        if new_samples.ndim != 1:
            new_samples = np.asarray(new_samples).reshape(-1)
        shift = len(new_samples)
        if shift <= 0:
            return
        if shift >= self.window_samples:
            self.buffer[ch, :] = new_samples[-self.window_samples:]
            self.sample_counts[ch] = self.window_samples
        else:
            self.buffer[ch, :-shift] = self.buffer[ch, shift:]
            self.buffer[ch, -shift:] = new_samples
            self.sample_counts[ch] = min(self.sample_counts[ch] + shift, self.window_samples)

    def buffer_is_full(self):
        return np.min(self.sample_counts) >= self.window_samples

    def baseline_correction(self, filtered_data):
        baseline = np.mean(filtered_data[:, : self.incoming_fs], axis=1)
        target_data = filtered_data[:, self.incoming_fs:]
        return target_data - baseline[:, np.newaxis]

    def downsampling_data(self, data, incoming_fs, target_fs):
        if incoming_fs == target_fs:
            return data
        n_channels, n_samples = data.shape
        new_n_samples = int(n_samples * target_fs / incoming_fs)
        downsampled_data = resample(data, new_n_samples, axis=1)
        return downsampled_data

    def process_features(self, args):
        filtered_data = np.zeros_like(self.buffer)
        current_buffer = self.buffer.copy()
        for ch in range(self.n_channels):
            filtered_data[ch, :] = bandpass_filter(
                current_buffer[ch, :],
                args.butterworth_low_cut,
                args.butterworth_high_cut,
                args.incoming_fs,
            )
        is_baseline = False
        if is_baseline:
            corrected_data = self.baseline_correction(filtered_data)
        else:
            corrected_data = filtered_data
        if args.incoming_fs != args.target_fs:
            corrected_data = self.downsampling_data(corrected_data, args.incoming_fs, args.target_fs)
        return corrected_data


# ====================== 模型文件检查 ======================

def _fine_tuning_param_check(args, logger):
    args.model_path = Path(args.path) / 'model_weight' / 'fine_tuned_model.pth'
    if not args.model_path.exists():
        logger.info(f"Model file not found at {str(args.model_path)}")
        logger.info('Using pretrained directory')
        candidates = list((Path(args.root) / 'pretrained_models' / args.pretrained_dir).glob("*.pth"))
        if not candidates:
            logger.error(
                f"No pretrained model file found in {str(Path(args.root) / 'pretrained_models' / args.pretrained_dir)}"
            )
            raise FileNotFoundError("Could not find model file.")
        args.model_path = candidates[0]

    args.scaler_path = Path(args.path) / 'model_weight' / 'scaler.joblib'
    if not args.scaler_path.exists():
        logger.info(f"Scaler file not found at {str(args.scaler_path)}")
        logger.info('Using scaler from pretrained directory')
        args.scaler_path = Path(args.root) / 'pretrained_models' / args.pretrained_dir / 'scaler.joblib'
        if not args.scaler_path.exists():
            logger.error(f"Scaler file not found at {str(args.scaler_path)}")
            raise FileNotFoundError("Could not find scaler file.")


# ====================== Page10 Widget ======================

class Page10Widget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        # ========= 默认数据目录 =========
        self.default_data_dir = "data"
        self.data_dir = self.default_data_dir
        os.makedirs(self.data_dir, exist_ok=True)

        self.sensor_serial: str = "000003"
        self._sensor_serial_parsed: bool = False

        self.last_plot_time = 0.0
        self.plot_interval = 1.0 / 30.0

        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(4)

        # ---------- 端口 ----------
        self.label_port = QtWidgets.QLabel("端口：")
        self.label_port.setFixedHeight(28)
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
        self.label_channel_count.setFixedWidth(60)
        self.label_channel_count.setFixedHeight(28)

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
        self.label_show_channels.setFixedHeight(28)

        self.channel_checkbox_layout = QtWidgets.QHBoxLayout()
        self.channel_checkbox_layout.setContentsMargins(0, 0, 0, 0)
        self.channel_checkbox_layout.setSpacing(8)

        self.channel_checkboxes: Dict[int, QtWidgets.QCheckBox] = {}

        show_channels_layout = QtWidgets.QHBoxLayout()
        show_channels_layout.setContentsMargins(0, 0, 0, 0)
        show_channels_layout.setSpacing(4)
        show_channels_layout.addWidget(self.label_show_channels)
        show_channels_layout.addLayout(self.channel_checkbox_layout)

        # ---------- 绘图降采样 checkbox ----------
        self.checkbox_downsample_plot = QtWidgets.QCheckBox("绘图降采样1/5")
        self.checkbox_downsample_plot.setChecked(False)

        downsample_layout = QtWidgets.QHBoxLayout()
        downsample_layout.setContentsMargins(0, 0, 0, 0)
        downsample_layout.setSpacing(4)
        downsample_layout.addWidget(self.checkbox_downsample_plot)

        # ---------- 走纸方式 ----------
        self.label_scroll_mode = QtWidgets.QLabel("走纸方式：")
        self.label_scroll_mode.setFixedHeight(28)

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

        self.button_reset_y = QtWidgets.QPushButton("重置y轴范围")
        self.button_reset_y.setFixedWidth(110)

        self.button_1 = QtWidgets.QPushButton(ButtonStates.start.value)
        self.button_1.setFixedWidth(160)

        self.button_save = QtWidgets.QPushButton("开始保存数据")
        self.button_save.setFixedWidth(220)
        self.button_save.setEnabled(False)
        self.button_save.setStyleSheet(
            "QPushButton:disabled {"
            "background-color: #dcdcdc;"
            "color: #888888;"
            "}"
        )

        self.label_1 = QtWidgets.QLabel(LabelStates.stopped.value)
        self.label_1.setFixedWidth(360)
        self.label_1.setFixedHeight(28)
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

        # ===================== 第三行：推理结果显示 =====================

        self.label_pred_title = QtWidgets.QLabel("当前预测：")
        self.label_pred_value = QtWidgets.QLabel("——")

        self.label_tbr_title = QtWidgets.QLabel("TBR EMA：")
        self.label_tbr_value = QtWidgets.QLabel("——")

        self.label_probs_title = QtWidgets.QLabel("类别概率：")
        self.label_probs_value = QtWidgets.QLabel("——")
        self.label_probs_value.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.label_probs_value.setMinimumWidth(260)

        self.stats_layout = QtWidgets.QHBoxLayout()
        self.stats_layout.setContentsMargins(20, 0, 20, 0)
        self.stats_layout.setSpacing(16)

        self.stats_layout.addStretch()
        self.stats_layout.addWidget(self.label_pred_title)
        self.stats_layout.addWidget(self.label_pred_value)
        self.stats_layout.addSpacing(24)
        self.stats_layout.addWidget(self.label_tbr_title)
        self.stats_layout.addWidget(self.label_tbr_value)
        self.stats_layout.addSpacing(24)
        self.stats_layout.addWidget(self.label_probs_title)
        self.stats_layout.addWidget(self.label_probs_value, 1)
        self.stats_layout.addStretch()

        # ===================== 曲线相关结构 =====================

        self.max_points = 1000
        self.sample_rate_hz: Optional[float] = None
        self.plot_downsample_step = 5

        self.window_sec = 5.0
        self.window_points = 1000
        self.sweep_x: List[float] = [
            self.window_sec * i / max(self.window_points - 1, 1)
            for i in range(self.window_points)
        ]

        self.channel_data_x: Dict[int, deque] = {}
        self.channel_data_y: Dict[int, deque] = {}
        self.channel_sample_index: Dict[int, int] = {}
        self.channel_curves: Dict[int, pg.PlotDataItem] = {}
        self.active_channels_in_plot: set[int] = set()
        self.channel_colors = ["r", "g", "b", "c", "m", "y", "k"]

        # 扫屏模式 buffer
        self.sweep_buffers: Dict[int, List[float]] = {}
        self.sweep_index: Dict[int, int] = {}

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground("w")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.2)
        self.plot_widget.setLabel("left", "μV")
        self.plot_widget.setLabel("bottom", "Time (s)")
        self.plot_widget.setYRange(-200, 200)
        self.legend = self.plot_widget.addLegend()

        self.sweep_line: Optional[pg.InfiniteLine] = None

        # 将三行布局和绘图 widget 加入主布局
        self.main_layout.addLayout(self.top_controls_layout)
        self.main_layout.addLayout(self.bottom_controls_layout)
        self.main_layout.addLayout(self.stats_layout)
        self.main_layout.addWidget(self.plot_widget)

        # 默认扫屏模式
        self.scroll_mode = 2
        self.combo_scroll_mode.setCurrentIndex(1)
        self.combo_scroll_mode.currentIndexChanged.connect(self.on_scroll_mode_changed)

        # 通道数变化
        self.combo_channel_count.currentIndexChanged.connect(self.on_channel_count_changed)
        self.on_channel_count_changed()

        # ===== IP 和采样率输入控件（隐藏，仅用来存值） =====
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
        # ✅ 这里改回和实际设备一致的 1000Hz，用于画图和保存
        self.input_fs.setPlaceholderText("例如 1000")
        self.input_fs.setText("1000")

        self.label_ip.hide()
        self.input_ip.hide()
        self.label_fs.hide()
        self.input_fs.hide()

        # 按钮信号
        self.button_1.clicked.connect(self.start_udp_receiving)
        self.button_reset_y.clicked.connect(self.reset_y_axis_range)
        self.button_save.clicked.connect(self.toggle_save_data)

        # UDP 接收器
        self.receiver: Optional[UdpEegReceiver] = None

        # ===== 保存数据相关 =====
        self.is_saving: bool = False
        self.channel_save_files: Dict[int, object] = {}
        self.channel_save_index: Dict[int, int] = {}
        self.marker_file: Optional[object] = None

        # ===== 推理相关结构 =====
        self.shared_queue: "queue.Queue[EegDataPacket]" = queue.Queue()
        self.result_queue: "queue.Queue[dict]" = queue.Queue()

        self.inference_model: Optional[ModelInference] = None
        self.eeg_processor: Optional[EEGBufferProcessor] = None
        self.inference_stop_event: Optional[threading.Event] = None
        self.inference_thread: Optional[threading.Thread] = None
        self.args = None
        self.dataset_configs = None
        self.training_config = None

        # logger
        self.logger = logging.getLogger("Page10Inference")
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

        # 定时器轮询推理结果
        self.result_timer = QTimer(self)
        self.result_timer.setInterval(200)
        self.result_timer.timeout.connect(self.poll_inference_results)

    # -------- 工具：递归清空 layout --------

    def _clear_layout(self, layout: QtWidgets.QLayout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            if child_layout is not None:
                self._clear_layout(child_layout)

    # -------- 解析传感器序列号 --------

    def _parse_sensor_serial(self, frame_data: bytes) -> str:
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

    # -------- 开始 / 停止 UDP + 推理 --------

    def start_udp_receiving(self):
        ip = self.input_ip.text().strip()
        port_str = self.input_port.text().strip()
        fs_str = self.input_fs.text().strip()

        if self.button_1.text() == ButtonStates.start.value:
            # ===== 开始 =====
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
            self.sample_rate_hz = float(fs_str)  # ✅ 这就是画图用的 fs（建议填 1000Hz）

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

            self.receiver = UdpEegReceiver(host=ip, port=port, buffer_size=8192, parent=self)
            self.receiver.data_received.connect(self.on_eeg_packet)
            self.receiver.error_occurred.connect(self.on_error)

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

            # 启动推理线程
            self.start_inference()

        elif self.button_1.text() == ButtonStates.stop.value:
            # ===== 停止 =====
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

            # 停止推理
            self.stop_inference()

    # -------- 初始化 / 启动推理 --------

    def ensure_model_loaded(self):
        if self.inference_model is not None and self.args is not None and self.dataset_configs is not None:
            return

        from argparse import Namespace
        root = Path(__file__).resolve().parent
        args = Namespace()
        args.path = Path(
            "/home/Y_Y/proj/hybrid_eeg_fnirs/data/test_all_in_one_company/LYZ_MI_Data_0610"
        )
        args.pretrained_dir = "my_eeg_dataset_eye_movement"
        args.dataset_configs = "data_eye_movement.yaml"
        args.train_configs = "train.yaml"
        args.log_level = "INFO"

        # ✅ 这里设定推理使用的输入采样率，和设备真实采样率一致（1000Hz）
        args.incoming_fs = 1000
        args.target_fs = 128
        args.butterworth_order = 4
        args.butterworth_low_cut = 7.0
        args.butterworth_high_cut = 47.0
        args.sampling_rate = 1000
        args.window_duration = 3.0
        args.n_channels = 3
        args.average_count = 3
        args.EMA_alpha = 0.4
        args.root = root
        args.cwd = root

        # 读取配置
        with open(args.root / 'configs' / f'{args.dataset_configs}', 'r', encoding='utf-8') as f:
            dataset_configs = yaml.safe_load(f)

        with open(args.root / 'configs' / f'{args.train_configs}', 'r', encoding='utf-8') as f:
            training_config = yaml.safe_load(f)

        _fine_tuning_param_check(args, self.logger)

        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

        inference = ModelInference(
            device=device,
            args=args,
            logger=self.logger,
            param_grid={
                'low_cut': [7.0],
                'high_cut': [47.0],
                'lr': [0.001],
                'model_F1': [8],
                'model_D': [2],
                'dropout': [0.25],
            },
            dataset_configs=dataset_configs,
            training_config=training_config,
        )

        self.args = args
        self.dataset_configs = dataset_configs
        self.training_config = training_config
        self.inference_model = inference

    def start_inference(self):
        try:
            self.ensure_model_loaded()
        except Exception as e:
            self.logger.error(f"初始化模型失败: {e}")
            self.label_pred_value.setText("模型初始化失败")
            return

        if self.args is None or self.inference_model is None:
            return

        # 如果希望推理采样率跟 UI 填写的设备采样率保持一致，可以打开这段
        try:
            fs_str = self.input_fs.text().strip()
            if is_valid_sample_rate(fs_str):
                self.args.incoming_fs = float(fs_str)
                self.args.sampling_rate = int(self.args.incoming_fs)
        except Exception:
            pass

        n_channels = self.combo_channel_count.currentData()
        if n_channels is None:
            n_channels = 3
        self.args.n_channels = int(n_channels)

        # 3 秒缓冲池
        self.eeg_processor = EEGBufferProcessor(
            incoming_fs=self.args.incoming_fs,
            window_duration=self.args.window_duration,
            n_channels=self.args.n_channels,
        )

        # 清空历史队列
        while True:
            try:
                self.shared_queue.get_nowait()
            except queue.Empty:
                break

        self.inference_stop_event = threading.Event()
        self.inference_thread = threading.Thread(
            name='InferenceWorker',
            target=self.inference_worker_loop,
            daemon=True,
        )
        self.inference_thread.start()
        self.result_timer.start()
        self.logger.info("Inference thread started (3s buffer, 1s stride).")

    def stop_inference(self):
        self.result_timer.stop()
        if self.inference_stop_event is not None:
            self.inference_stop_event.set()
        if self.inference_thread is not None and self.inference_thread.is_alive():
            self.inference_thread.join(timeout=2.0)
        self.inference_thread = None
        self.inference_stop_event = None
        self.eeg_processor = None

        # 清空队列
        while True:
            try:
                self.shared_queue.get_nowait()
            except queue.Empty:
                break
        while True:
            try:
                self.result_queue.get_nowait()
            except queue.Empty:
                break

        self.label_pred_value.setText("——")
        self.label_tbr_value.setText("——")
        self.label_probs_value.setText("——")

    # -------- 推理线程主体 --------

    def inference_worker_loop(self):
        if self.eeg_processor is None or self.inference_model is None or self.args is None:
            return

        band_power_calculator = EEGAnalyzer(self.args.target_fs)
        last_infer_time = time.monotonic()
        tbr_ema = None

        while self.inference_stop_event is not None and (not self.inference_stop_event.is_set()):
            # 取数据填入 3 秒缓冲
            try:
                packet = self.shared_queue.get(timeout=0.1)
                packets = [packet]
                while True:
                    try:
                        packets.append(self.shared_queue.get_nowait())
                    except queue.Empty:
                        break

                for pkt in packets:
                    ch = pkt.channel
                    samples = np.asarray(pkt.data, dtype=np.float32)
                    self.eeg_processor.update_channel_buffer(ch, samples)
            except queue.Empty:
                pass

            # 每秒做一次推理
            now = time.monotonic()
            if now - last_infer_time >= 1.0:
                last_infer_time = now
                if not self.eeg_processor.buffer_is_full():
                    self.logger.debug("Buffer not yet full (3s). Skipping inference this second.")
                    continue

                try:
                    corrected_data = self.eeg_processor.process_features(self.args)

                    # ====== 计算 TBR EMA ======
                    corrected_copy = corrected_data.copy()
                    channel_tbrs = []
                    for ch_idx in range(corrected_copy.shape[0]):
                        channel_data = corrected_copy[ch_idx, :]
                        tbr = band_power_calculator.calculate_tbr(channel_data)
                        channel_tbrs.append(tbr)
                    avg_tbr = float(np.mean(channel_tbrs)) if channel_tbrs else 0.0
                    if tbr_ema is None:
                        tbr_ema = avg_tbr
                    else:
                        tbr_ema = self.args.EMA_alpha * avg_tbr + (1 - self.args.EMA_alpha) * tbr_ema

                    # ====== 神经网络推理（返回所有类别概率） ======
                    pred_name, prob_dict = self.inference_model.predict(corrected_data, self.dataset_configs)

                    result = {
                        "timestamp": time.time(),
                        "tbr_ema": tbr_ema,
                        "pred_name": pred_name,
                        "probabilities": prob_dict,
                    }
                    self.result_queue.put(result)

                    self.logger.info(f"[NN] Prediction (last 3s): {pred_name}")
                    self.logger.info(f"[TBR] EMA: {tbr_ema:.2f}")
                    self.logger.debug(f"[PROBS] {prob_dict}")

                except Exception as e:
                    tbr_ema = None
                    self.logger.error(f"Inference error: {e}")

        self.logger.info("Inference thread stopped.")

    # -------- EEG 数据回调：画图 + 保存 + 推理队列 --------

    def on_eeg_packet(self, packet: EegDataPacket):
        """
        注意：
        - 画图和保存走 self.sample_rate_hz（UI 里填写，建议 1000Hz）
        - 推理走 self.shared_queue → EEGBufferProcessor（再在里面降采样到 target_fs）
        """
        if self.sample_rate_hz is None or self.sample_rate_hz <= 0:
            return

        ch = packet.channel

        # 第一次解析传感器序列号
        if (not self._sensor_serial_parsed) and packet.raw_packet:
            self.sensor_serial = self._parse_sensor_serial(packet.raw_packet)
            self._sensor_serial_parsed = True
            print(f"数据来自传感器序列号: {self.sensor_serial}")

        # 保存 CSV
        if self.is_saving:
            self._save_packet_samples(packet)

        # 初始化通道曲线
        if ch not in self.channel_data_x:
            self.channel_data_x[ch] = deque(maxlen=self.max_points)
            self.channel_data_y[ch] = deque(maxlen=self.max_points)
            self.channel_sample_index[ch] = 0
            color = self.channel_colors[len(self.channel_curves) % len(self.channel_colors)]
            curve = self.plot_widget.plot(pen=color, name=f"Ch {ch}")
            self.channel_curves[ch] = curve

        # 扫屏缓冲
        if ch not in self.sweep_buffers:
            self.sweep_buffers[ch] = [float("nan")] * self.window_points
            self.sweep_index[ch] = 0

        self.active_channels_in_plot.add(ch)

        # ------- 画图数据写入（始终使用原始数据，不做重采样） -------
        if self.scroll_mode == 1:
            # 滚动窗口：X 轴用“校正后的电脑时间”
            dt_s = 1.0 / self.sample_rate_hz if self.sample_rate_hz and self.sample_rate_hz > 0 else 0.0
            samples = packet.data
            n = len(samples)
            if n == 0:
                return
            base_ts = packet.system_timestamp if packet.system_timestamp > 0 else packet.hardware_timestamp
            if dt_s > 0:
                t_first = base_ts - (n - 1) * dt_s
            else:
                t_first = base_ts
            for j, v in enumerate(samples):
                self.channel_sample_index[ch] += 1
                t_s = t_first + j * dt_s
                self.channel_data_x[ch].append(t_s)
                self.channel_data_y[ch].append(v)
        else:
            # 扫屏重写模式：仅根据样点索引写入 buffer，时间轴统一用 sweep_x
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

        channels_sorted = sorted(self.active_channels_in_plot)
        visible_channels = []
        for c in channels_sorted:
            cb = self.channel_checkboxes.get(c)
            if cb is None or cb.isChecked():
                visible_channels.append(c)

        self.label_1.setText(
            f"{LabelStates.receiving.value} 当前显示通道: {visible_channels}"
        )
        self.label_1.setStyleSheet("color: #008000")

        # ------- 推理队列：把原始包扔给 3 秒缓冲池 -------
        try:
            self.shared_queue.put_nowait(packet)
        except Exception:
            pass

        # 限制刷新帧率
        now = time.time()
        if now - self.last_plot_time >= self.plot_interval:
            self.update_plot()
            self.last_plot_time = now

    # -------- 保存按钮逻辑 --------

    def toggle_save_data(self):
        if not self.is_saving:
            self.start_saving()
        else:
            self.stop_saving()

    def start_saving(self, save_dir: Optional[str] = None):
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

        if self.sample_rate_hz and self.sample_rate_hz > 0:
            dt_s = 1.0 / self.sample_rate_hz
        else:
            dt_s = 0.0

        samples = packet.data
        n = len(samples)
        if n == 0:
            return

        base_ts = packet.system_timestamp if packet.system_timestamp > 0 else packet.hardware_timestamp
        if dt_s > 0:
            t_first = base_ts - (n - 1) * dt_s
        else:
            t_first = base_ts

        idx = self.channel_save_index.get(ch, 0)

        for j, v in enumerate(samples):
            t_s = t_first + j * dt_s
            f.write(f"{t_s:.6f},{v:.6f}\n")

            if ch == 0 and self.marker_file is not None:
                self.marker_file.write(f"{t_s:.6f},0\n")

            idx += 1

        self.channel_save_index[ch] = idx

    # -------- 其他 UI 回调 --------

    def on_error(self, message: str):
        print("UDP 错误:", message)
        self.label_1.setText(message)
        self.label_1.setStyleSheet("color: red")

    def is_listening(self) -> bool:
        if self.receiver is None:
            return False
        if hasattr(self.receiver, "is_running"):
            try:
                return self.receiver.is_running()
            except Exception:
                return False
        return self.receiver.running

    def reset_y_axis_range(self):
        self.plot_widget.setYRange(-200, 200)

    # -------- 画图更新 --------

    def update_plot(self):
        if not self.channel_curves:
            return

        downsample = self.checkbox_downsample_plot.isChecked()

        # 模式1：滚动窗口（X 轴为“校正后的电脑时间”）
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

        # 模式2：扫屏重写
        else:
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
                if self.sweep_index and self.window_points > 0:
                    idx = next(iter(self.sweep_index.values()))
                    last_idx = (idx - 1) % self.window_points
                    if 0 <= last_idx < len(self.sweep_x):
                        x_pos = self.sweep_x[last_idx]
                        self.sweep_line.setValue(x_pos)

    # -------- 轮询推理结果，更新 UI --------

    def poll_inference_results(self):
        last_result = None
        while True:
            try:
                item = self.result_queue.get_nowait()
                last_result = item
            except queue.Empty:
                break
        if last_result is None:
            return

        pred = last_result.get("pred_name")
        tbr = last_result.get("tbr_ema")
        probs = last_result.get("probabilities")

        if pred is not None:
            self.label_pred_value.setText(str(pred))
        else:
            self.label_pred_value.setText("——")

        if tbr is not None:
            self.label_tbr_value.setText(f"{tbr:.2f}")
        else:
            self.label_tbr_value.setText("——")

        # 更新类别概率显示（单行）
        if isinstance(probs, dict) and probs:
            # 按类别名排序，拼成一行
            parts = [f"{cls}: {p:.3f}" for cls, p in sorted(probs.items(), key=lambda x: x[0])]
            self.label_probs_value.setText(" | ".join(parts))
        else:
            self.label_probs_value.setText("——")

    # -------- 生命周期清理 --------

    def closeEvent(self, event):
        if self.receiver is not None:
            self.receiver.stop()
            self.receiver.deleteLater()
            self.receiver = None
        if self.is_saving:
            self.stop_saving()
        self.stop_inference()
        event.accept()


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    app = QtWidgets.QApplication(sys.argv)
    w = Page10Widget()
    w.resize(1000, 700)
    w.show()
    sys.exit(app.exec())


# 这是我目前page10的代码，你帮我把page10的代码接收数据，画图的形式，改的跟page2一样，同时也要加入模拟网络不稳定相关参数（默认开启丢包）的代码，

# 你认真改，把修改完后的完整代码展示给我