import enum
import re
import threading
from collections import deque

from PyQt6 import QtWidgets
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QHBoxLayout
import pyqtgraph as pg

from util.EEGReceiver import EEGReceiverTCPWithUI


class LabelStates(enum.Enum):
    disconnected = "未连接"
    connected = "已连接，接收数据中..."
    connecting = "等待TCP连接中..."

class ButtonStates(enum.Enum):
    start = "开始检测TCP信号"
    stop = "停止检测TCP信号"

def is_valid_ip(ip):
    IP_REGEX = r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$"
    if not re.match(IP_REGEX, ip):
        return False
    # 检查每个段是否在 0-255 之间
    segments = ip.split('.')
    for segment in segments:
        if not 0 <= int(segment) <= 255:
            return False
    return True

def is_valid_port(port):
    return port.isdigit() and 1 <= int(port) <= 65535


class Page2Widget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(Page2Widget, self).__init__(parent)
        # 创建按钮和布局
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(4)

        # layout_1
        self.layout_1 = QHBoxLayout()
        self.input_ip = QtWidgets.QLineEdit()
        self.input_ip.setFixedWidth(150)
        self.input_ip.setPlaceholderText("IP")
        self.input_ip.setText("127.0.0.1")
        self.input_port = QtWidgets.QLineEdit()
        self.input_port.setFixedWidth(80)
        self.input_port.setPlaceholderText("Port")
        self.input_port.setText("12345")
        self.button_1 = QtWidgets.QPushButton(ButtonStates.start.value)
        self.button_1.setFixedWidth(200)
        self.label_1 = QtWidgets.QLabel(LabelStates.disconnected.value)
        self.label_1.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)

        self.layout_1.addWidget(self.input_ip)
        self.layout_1.addWidget(self.input_port)
        self.layout_1.addWidget(self.button_1)
        self.layout_1.addWidget(self.label_1)
        # layout_1

        # layout_2
        self.max_points = 1000  # 最多显示的点数
        self.data_x = deque(maxlen=self.max_points)
        self.data_y = deque(maxlen=self.max_points)
        self.plot_widget = pg.PlotWidget()
        self.plot_curve = self.plot_widget.plot(pen='r')  # 创建一个画笔, 设置颜色为黄色

        # self.timer = QTimer()
        # self.timer.timeout.connect(self.update_plot)  # 定时器的timeout信号

        # layout_2

        self.main_layout.addLayout(self.layout_1)
        self.main_layout.addWidget(self.plot_widget)

        # signal and slot
        self.button_1.clicked.connect(self.start_tcp_receiving)

        self.receiver = None

    def process_data_(self, data):
        try:
            data_ = data.decode("utf-8").strip()
            data_parts = data_.split(',')
            self.data_x.append(float(data_parts[0]))
            self.data_y.append(float(data_parts[1]))
            self.update_plot()
        except ValueError:
            print("Received non-numeric data:", data)

    # def update_plot(self):
    #     # 更新曲线数据
    #     self.plot_curve.setData(list(self.data))

    def update_plot(self):
        # self.data已经是最新的数据
        y_data = list(self.data_y)

        # 创建对应长度的 x 轴数据
        # x_data = list(range(len(y_data)))
        x_data = list(self.data_x)

        self.plot_curve.setData(x=x_data, y=y_data)

        # 只显示最近的 1000 个数据点（times 中的最新时间值范围）
        if len(x_data) > 0:
            self.plot_widget.setXRange(x_data[0], x_data[0] + self.max_points - 1)

    def start_tcp_receiving(self):
        ip = self.input_ip.text()
        port = self.input_port.text()

        if not ip or not port:
            self.label_1.setText("请输入ip和port")
            self.label_1.setStyleSheet("color: red")
            return
        if not is_valid_ip(ip):
            self.label_1.setText("请输入合法的ip")
            self.label_1.setStyleSheet("color: red")
            return
        if not is_valid_port(port):
            self.label_1.setText("请输入合法的port")
            self.label_1.setStyleSheet("color: red")
            return
        self.label_1.setStyleSheet("color: #5d5d5d")


        if self.button_1.text() == ButtonStates.start.value:   # "开始检测TCP信号"


            self.receiver = EEGReceiverTCPWithUI(ip, int(port), self.update_ui)

            if self.receiver.start_receiving(self.process_data_):
                self.label_1.setText(LabelStates.connecting.value)  # "等待TCP连接中..."
                self.button_1.setText(ButtonStates.stop.value)  # "停止检测TCP信号"
                self.input_ip.setDisabled(True)
                self.input_port.setDisabled(True)

                # self.timer.start(10)  # 启动timer, 每隔10ms发送一次timeout signal

        elif self.button_1.text() == ButtonStates.stop.value:  # "停止检测TCP信号"
            if self.receiver:
                self.input_ip.setDisabled(False)
                self.input_port.setDisabled(False)
                self.label_1.setText(LabelStates.disconnected.value)  # "未连接"
                self.button_1.setText(ButtonStates.start.value)  # "开始检测TCP信号"

                self.receiver.stop_receiving()

                # 停止接收后停止定时器
                # if self.timer.isActive():
                #     self.timer.stop()

    def update_ui(self, is_connected):
        if is_connected:
            self.button_1.setText(ButtonStates.stop.value)  # "停止检测TCP信号"
            self.label_1.setText(LabelStates.connected.value)  # "已连接，接收数据中"

        else:
            self.button_1.setText(ButtonStates.start.value)  # "开始检测TCP信号"
            self.label_1.setText(LabelStates.disconnected.value)  # "未连接"
            # if self.timer.isActive():
            #     self.timer.stop()

