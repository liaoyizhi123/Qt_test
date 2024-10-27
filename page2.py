from PyQt6 import QtWidgets


class Page2Widget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(Page2Widget, self).__init__(parent)

        # 创建按钮和布局
        self.layout = QtWidgets.QVBoxLayout(self)
        self.button = QtWidgets.QPushButton("Page 2 Button")
        self.layout.addWidget(self.button)
