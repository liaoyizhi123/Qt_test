import sys
from datetime import datetime
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtWidgets import QApplication, QMainWindow

from page1 import Page1Widget
from page2_data_collection import Page2Widget
from page3 import Page3Widget
from page4_nback import Page4Widget
from page5_stroop import Page5Widget
from page6_ma import Page6Widget
from page7_mill import Page7Widget
from page8_miul import Page8Widget
from page9_eye import Page9Widget  # FIXME.


class Ui_MainWindow(QMainWindow):

    def __init__(self):
        super(Ui_MainWindow, self).__init__()
        self.setupUi(self)
        current_date = datetime.now().strftime("%Y年%m月%d日")
        self.proj_date.setText(current_date)

    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(814, 608)

        # 基础容器
        self.base_widget = QtWidgets.QWidget(parent=MainWindow)
        self.base_widget.setObjectName("base_widget")
        # 主垂直布局
        self.verticalLayout_3 = QtWidgets.QVBoxLayout(self.base_widget)
        self.verticalLayout_3.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout_3.setSpacing(0)
        self.verticalLayout_3.setObjectName("verticalLayout_3")
        # 应用主框架
        self.app_frame = QtWidgets.QFrame(parent=self.base_widget)
        self.app_frame.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.app_frame.setFrameShadow(QtWidgets.QFrame.Shadow.Raised)
        self.app_frame.setObjectName("app_frame")
        self.verticalLayout_2 = QtWidgets.QVBoxLayout(self.app_frame)
        self.verticalLayout_2.setSpacing(0)
        self.verticalLayout_2.setObjectName("verticalLayout_2")

        # ######################## top frame, base on the app frame
        self.top_frame = QtWidgets.QFrame(parent=self.app_frame)
        self.top_frame.setMinimumSize(QtCore.QSize(0, 50))
        self.top_frame.setMaximumSize(QtCore.QSize(16777215, 50))
        self.top_frame.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.top_frame.setFrameShadow(QtWidgets.QFrame.Shadow.Raised)
        self.top_frame.setObjectName("top_frame")
        self.horizontalLayout = QtWidgets.QHBoxLayout(self.top_frame)
        self.horizontalLayout.setContentsMargins(0, 0, 0, 0)
        self.horizontalLayout.setSpacing(0)
        self.horizontalLayout.setObjectName("horizontalLayout")
        # top left frame, base on the top frame
        self.top_left = QtWidgets.QFrame(parent=self.top_frame)
        self.top_left.setMinimumSize(QtCore.QSize(40, 40))
        self.top_left.setMaximumSize(QtCore.QSize(40, 40))
        self.top_left.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.top_left.setFrameShadow(QtWidgets.QFrame.Shadow.Raised)
        self.top_left.setObjectName("top_left")
        self.verticalLayout_4 = QtWidgets.QVBoxLayout(self.top_left)
        self.verticalLayout_4.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout_4.setSpacing(0)
        self.verticalLayout_4.setObjectName("verticalLayout_4")
        self.logo_image = QtWidgets.QLabel(parent=self.top_left)
        self.logo_image.setText("")
        self.logo_image.setPixmap(QtGui.QPixmap("resources/icons/pikachu.png"))
        self.logo_image.setScaledContents(True)
        self.logo_image.setObjectName("logo_image")
        self.verticalLayout_4.addWidget(self.logo_image)
        self.horizontalLayout.addWidget(self.top_left, 0, QtCore.Qt.AlignmentFlag.AlignLeft)
        # top center frame, base on the top frame
        self.top_center = QtWidgets.QFrame(parent=self.top_frame)
        sizePolicy = QtWidgets.QSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred
        )
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.top_center.sizePolicy().hasHeightForWidth())
        self.top_center.setSizePolicy(sizePolicy)
        self.top_center.setMinimumSize(QtCore.QSize(0, 50))
        self.top_center.setMaximumSize(QtCore.QSize(16777215, 50))
        self.top_center.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.top_center.setFrameShadow(QtWidgets.QFrame.Shadow.Raised)
        self.top_center.setObjectName("top_center")
        self.verticalLayout_5 = QtWidgets.QVBoxLayout(self.top_center)
        self.verticalLayout_5.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout_5.setSpacing(0)
        self.verticalLayout_5.setObjectName("verticalLayout_5")
        self.proj_title = QtWidgets.QLabel(parent=self.top_center)
        self.proj_title.setObjectName("proj_title")
        self.verticalLayout_5.addWidget(self.proj_title)
        self.horizontalLayout.addWidget(self.top_center)
        # top right frame, base on the top frame
        self.top_right = QtWidgets.QFrame(parent=self.top_frame)
        self.top_right.setMinimumSize(QtCore.QSize(200, 50))
        self.top_right.setMaximumSize(QtCore.QSize(200, 50))
        self.top_right.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.top_right.setFrameShadow(QtWidgets.QFrame.Shadow.Raised)
        self.top_right.setObjectName("top_right")
        self.verticalLayout_6 = QtWidgets.QVBoxLayout(self.top_right)
        self.verticalLayout_6.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout_6.setSpacing(0)
        self.verticalLayout_6.setObjectName("verticalLayout_6")
        self.proj_date = QtWidgets.QLabel(parent=self.top_right)
        self.proj_date.setObjectName("proj_date")
        self.verticalLayout_6.addWidget(self.proj_date)
        self.horizontalLayout.addWidget(self.top_right, 0, QtCore.Qt.AlignmentFlag.AlignRight)
        self.verticalLayout_2.addWidget(self.top_frame)

        # ######################## content box, base on the app frame
        self.content_box = QtWidgets.QFrame(parent=self.app_frame)
        sizePolicy = QtWidgets.QSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Expanding
        )
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.content_box.sizePolicy().hasHeightForWidth())
        self.content_box.setSizePolicy(sizePolicy)
        self.content_box.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.content_box.setFrameShadow(QtWidgets.QFrame.Shadow.Raised)
        self.content_box.setObjectName("content_box")
        self.horizontalLayout_2 = QtWidgets.QHBoxLayout(self.content_box)
        self.horizontalLayout_2.setContentsMargins(0, 0, 0, 0)
        self.horizontalLayout_2.setSpacing(0)
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        # left frame, base on the content box
        self.left_frame = QtWidgets.QFrame(parent=self.content_box)
        self.left_frame.setMinimumSize(QtCore.QSize(0, 0))
        self.left_frame.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.left_frame.setFrameShadow(QtWidgets.QFrame.Shadow.Raised)
        self.left_frame.setObjectName("left_frame")
        self.verticalLayout = QtWidgets.QVBoxLayout(self.left_frame)
        self.verticalLayout.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout.setSpacing(0)
        self.verticalLayout.setObjectName("verticalLayout")

        self.left_center = QtWidgets.QFrame(parent=self.left_frame)
        self.left_center.setMinimumSize(QtCore.QSize(50, 0))
        self.left_center.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.left_center.setFrameShadow(QtWidgets.QFrame.Shadow.Raised)
        self.left_center.setObjectName("left_center")
        self.verticalLayout_8 = QtWidgets.QVBoxLayout(self.left_center)
        self.verticalLayout_8.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout_8.setSpacing(0)
        self.verticalLayout_8.setObjectName("verticalLayout_8")
        # 左侧home按钮
        self.btn_lef_home = QtWidgets.QPushButton(parent=self.left_center)
        self.btn_lef_home.setMinimumSize(QtCore.QSize(0, 50))
        self.btn_lef_home.setMaximumSize(QtCore.QSize(16777215, 50))
        self.btn_lef_home.setText("")
        icon1 = QtGui.QIcon()
        icon1.addPixmap(QtGui.QPixmap("resources/icons/note.png"), QtGui.QIcon.Mode.Normal, QtGui.QIcon.State.Off)
        self.btn_lef_home.setIcon(icon1)
        self.btn_lef_home.setIconSize(QtCore.QSize(32, 32))
        self.btn_lef_home.setObjectName("btn_lef_home")
        self.verticalLayout_8.addWidget(self.btn_lef_home)
        self.btn_lef_home.hide()
        # 左侧new按钮
        self.btn_lef_new = QtWidgets.QPushButton(parent=self.left_center)
        self.btn_lef_new.setMinimumSize(QtCore.QSize(0, 50))
        self.btn_lef_new.setMaximumSize(QtCore.QSize(16777215, 50))
        self.btn_lef_new.setText("")
        icon2 = QtGui.QIcon()
        icon2.addPixmap(QtGui.QPixmap("resources/icons/data_view.png"), QtGui.QIcon.Mode.Normal, QtGui.QIcon.State.Off)
        self.btn_lef_new.setIcon(icon2)
        self.btn_lef_new.setIconSize(QtCore.QSize(32, 32))
        self.btn_lef_new.setObjectName("btn_lef_new")
        self.verticalLayout_8.addWidget(self.btn_lef_new)
        # 左侧save按钮
        self.btn_lef_save = QtWidgets.QPushButton(parent=self.left_center)
        self.btn_lef_save.setMinimumSize(QtCore.QSize(0, 50))
        self.btn_lef_save.setMaximumSize(QtCore.QSize(16777215, 50))
        self.btn_lef_save.setText("")
        icon3 = QtGui.QIcon()
        icon3.addPixmap(QtGui.QPixmap("resources/icons/flower.png"), QtGui.QIcon.Mode.Normal, QtGui.QIcon.State.Off)
        self.btn_lef_save.setIcon(icon3)
        self.btn_lef_save.setIconSize(QtCore.QSize(32, 32))
        self.btn_lef_save.setObjectName("btn_lef_save")
        self.verticalLayout_8.addWidget(self.btn_lef_save)
        self.btn_lef_save.hide()
        # 左侧exit按钮
        self.btn_lef_exit = QtWidgets.QPushButton(parent=self.left_center)
        self.btn_lef_exit.setMinimumSize(QtCore.QSize(0, 50))
        self.btn_lef_exit.setMaximumSize(QtCore.QSize(16777215, 50))
        self.btn_lef_exit.setText("")
        icon4 = QtGui.QIcon()
        icon4.addPixmap(QtGui.QPixmap("resources/icons/nback.png"), QtGui.QIcon.Mode.Normal, QtGui.QIcon.State.Off)
        self.btn_lef_exit.setIcon(icon4)
        self.btn_lef_exit.setIconSize(QtCore.QSize(32, 32))
        self.btn_lef_exit.setObjectName("btn_lef_exit")
        self.verticalLayout_8.addWidget(self.btn_lef_exit)
        # 左侧stroop按钮
        self.btn_lef_stroop = QtWidgets.QPushButton(parent=self.left_center)
        self.btn_lef_stroop.setMinimumSize(QtCore.QSize(0, 50))
        self.btn_lef_stroop.setMaximumSize(QtCore.QSize(16777215, 50))
        self.btn_lef_stroop.setText("")
        icon5 = QtGui.QIcon()
        icon5.addPixmap(QtGui.QPixmap("resources/icons/stroop.png"), QtGui.QIcon.Mode.Normal, QtGui.QIcon.State.Off)
        self.btn_lef_stroop.setIcon(icon5)
        self.btn_lef_stroop.setIconSize(QtCore.QSize(32, 32))
        self.btn_lef_stroop.setObjectName("btn_lef_stroop")
        self.verticalLayout_8.addWidget(self.btn_lef_stroop)
        # 左侧MA按钮
        self.btn_lef_ma = QtWidgets.QPushButton(parent=self.left_center)
        self.btn_lef_ma.setMinimumSize(QtCore.QSize(0, 50))
        self.btn_lef_ma.setMaximumSize(QtCore.QSize(16777215, 50))
        self.btn_lef_ma.setText("")
        icon6 = QtGui.QIcon()
        icon6.addPixmap(QtGui.QPixmap("resources/icons/ma.png"), QtGui.QIcon.Mode.Normal, QtGui.QIcon.State.Off)
        self.btn_lef_ma.setIcon(icon6)
        self.btn_lef_ma.setIconSize(QtCore.QSize(32, 32))
        self.btn_lef_ma.setObjectName("btn_lef_ma")
        self.verticalLayout_8.addWidget(self.btn_lef_ma)
        # 左侧MI(Lower Limb)按钮
        self.btn_lef_mi_lower = QtWidgets.QPushButton(parent=self.left_center)
        self.btn_lef_mi_lower.setMinimumSize(QtCore.QSize(0, 50))
        self.btn_lef_mi_lower.setMaximumSize(QtCore.QSize(16777215, 50))
        self.btn_lef_mi_lower.setText("")
        icon7 = QtGui.QIcon()
        icon7.addPixmap(QtGui.QPixmap("resources/icons/leg.png"), QtGui.QIcon.Mode.Normal, QtGui.QIcon.State.Off)
        self.btn_lef_mi_lower.setIcon(icon7)
        self.btn_lef_mi_lower.setIconSize(QtCore.QSize(32, 32))
        self.btn_lef_mi_lower.setObjectName("btn_lef_mi")
        self.verticalLayout_8.addWidget(self.btn_lef_mi_lower)
        # 左侧MI(Upper Limb)按钮
        self.btn_lef_mi_upper = QtWidgets.QPushButton(parent=self.left_center)
        self.btn_lef_mi_upper.setMinimumSize(QtCore.QSize(0, 50))
        self.btn_lef_mi_upper.setMaximumSize(QtCore.QSize(16777215, 50))
        self.btn_lef_mi_upper.setText("")
        icon8 = QtGui.QIcon()
        icon8.addPixmap(QtGui.QPixmap("resources/icons/hand.png"), QtGui.QIcon.Mode.Normal, QtGui.QIcon.State.Off)
        self.btn_lef_mi_upper.setIcon(icon8)
        self.btn_lef_mi_upper.setIconSize(QtCore.QSize(32, 32))
        self.btn_lef_mi_upper.setObjectName("btn_lef_mi_upper")
        self.verticalLayout_8.addWidget(self.btn_lef_mi_upper)
        # 左侧睁眼/闭眼按钮
        self.btn_lef_eye = QtWidgets.QPushButton(parent=self.left_center)
        self.btn_lef_eye.setMinimumSize(QtCore.QSize(0, 50))
        self.btn_lef_eye.setMaximumSize(QtCore.QSize(16777215, 50))
        self.btn_lef_eye.setText("")
        icon9 = QtGui.QIcon()
        icon9.addPixmap(QtGui.QPixmap("resources/icons/eye.png"), QtGui.QIcon.Mode.Normal, QtGui.QIcon.State.Off)
        self.btn_lef_eye.setIcon(icon9)
        self.btn_lef_eye.setIconSize(QtCore.QSize(32, 32))
        self.btn_lef_eye.setObjectName("btn_lef_eye")
        self.verticalLayout_8.addWidget(self.btn_lef_eye)
        # FIXME.

        # ⭐ 统一为导航按钮打上 nav 属性，交给 QSS 控制样式
        self.nav_buttons = [
            self.btn_lef_home,
            self.btn_lef_new,
            self.btn_lef_save,
            self.btn_lef_exit,
            self.btn_lef_stroop,
            self.btn_lef_ma,
            self.btn_lef_mi_lower,
            self.btn_lef_mi_upper,
            self.btn_lef_eye,
        ]
        for btn in self.nav_buttons:
            btn.setProperty("nav", True)

        # 左侧底部的按钮
        self.verticalLayout.addWidget(self.left_center, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        self.left_bottom = QtWidgets.QFrame(parent=self.left_frame)
        self.left_bottom.setMinimumSize(QtCore.QSize(50, 50))
        self.left_bottom.setMaximumSize(QtCore.QSize(16777215, 50))
        self.left_bottom.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.left_bottom.setFrameShadow(QtWidgets.QFrame.Shadow.Raised)
        self.left_bottom.setObjectName("left_bottom")
        self.verticalLayout.addWidget(self.left_bottom)
        self.horizontalLayout_2.addWidget(self.left_frame)

        # 主内容区，基于content box
        self.main_content = QtWidgets.QFrame(parent=self.content_box)
        sizePolicy = QtWidgets.QSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred
        )
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.main_content.sizePolicy().hasHeightForWidth())
        self.main_content.setSizePolicy(sizePolicy)
        self.main_content.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.main_content.setFrameShadow(QtWidgets.QFrame.Shadow.Raised)
        self.main_content.setObjectName("main_content")
        self.verticalLayout_9 = QtWidgets.QVBoxLayout(self.main_content)
        self.verticalLayout_9.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout_9.setSpacing(0)
        self.verticalLayout_9.setObjectName("verticalLayout_9")
        self.stackedWidget = QtWidgets.QStackedWidget(parent=self.main_content)
        self.stackedWidget.setObjectName("stackedWidget")

        self.page_1 = Page1Widget(self.stackedWidget)
        self.page_1.setObjectName("page_1")
        self.stackedWidget.addWidget(self.page_1)

        self.page_2 = Page2Widget(self.stackedWidget)
        self.page_2.setObjectName("page_2")
        self.stackedWidget.addWidget(self.page_2)

        self.page_3 = Page3Widget(self.stackedWidget)
        self.page_3.setObjectName("page_3")
        self.stackedWidget.addWidget(self.page_3)

        self.page_4 = Page4Widget(self.stackedWidget)
        self.page_4.setObjectName("page_4")
        self.page_4.eeg_page = self.page_2
        self.stackedWidget.addWidget(self.page_4)

        self.page_5 = Page5Widget(self.stackedWidget)
        self.page_5.setObjectName("page_5")
        self.page_5.eeg_page = self.page_2
        self.stackedWidget.addWidget(self.page_5)

        self.page_6 = Page6Widget(self.stackedWidget)
        self.page_6.setObjectName("page_6")
        self.page_6.eeg_page = self.page_2
        self.stackedWidget.addWidget(self.page_6)

        self.page_7 = Page7Widget(self.stackedWidget)
        self.page_7.setObjectName("page_7")
        self.page_7.eeg_page = self.page_2
        self.stackedWidget.addWidget(self.page_7)

        self.page_8 = Page8Widget(self.stackedWidget)
        self.page_8.setObjectName("page_8")
        self.page_8.eeg_page = self.page_2
        self.stackedWidget.addWidget(self.page_8)

        self.page_9 = Page9Widget(self.stackedWidget)
        self.page_9.setObjectName("page_9")
        self.page_9.eeg_page = self.page_2
        self.stackedWidget.addWidget(self.page_9)

        # FIXME.

        self.verticalLayout_9.addWidget(self.stackedWidget)
        self.horizontalLayout_2.addWidget(self.main_content)
        self.verticalLayout_2.addWidget(self.content_box)
        self.verticalLayout_3.addWidget(self.app_frame)
        MainWindow.setCentralWidget(self.base_widget)

        # 不再在这里设置 index=3，默认逻辑交给 change_btn_page 统一处理
        self.retranslateUi(MainWindow)
        QtCore.QMetaObject.connectSlotsByName(MainWindow)

        # 绑定按钮与页面
        self.switch_page(
            self.btn_lef_home,
            self.btn_lef_new,
            self.btn_lef_save,
            self.btn_lef_exit,
            self.btn_lef_stroop,
            self.btn_lef_ma,
            self.btn_lef_mi_lower,
            self.btn_lef_mi_upper,
            self.btn_lef_eye,  # FIXME.
            self.stackedWidget,
        )

        # ⭐ 关键：启动时默认展示 Page2（索引 1），并同步更新按钮样式和标题
        self.change_btn_page(1, self.stackedWidget)

    def switch_page(
        self,
        btn_lef_home,
        btn_lef_new,
        btn_lef_save,
        btn_lef_exit,
        btn_lef_stroop,
        btn_lef_ma,
        btn_lef_mi_lower,
        btn_lef_mi_upper,
        btn_lef_eye,  # FIXME.
        stackedWidget,
    ):
        btn_lef_home.clicked.connect(lambda: self.change_btn_page(0, stackedWidget))
        btn_lef_new.clicked.connect(lambda: self.change_btn_page(1, stackedWidget))
        btn_lef_save.clicked.connect(lambda: self.change_btn_page(2, stackedWidget))
        btn_lef_exit.clicked.connect(lambda: self.change_btn_page(3, stackedWidget))
        btn_lef_stroop.clicked.connect(lambda: self.change_btn_page(4, stackedWidget))
        btn_lef_ma.clicked.connect(lambda: self.change_btn_page(5, stackedWidget))
        btn_lef_mi_lower.clicked.connect(lambda: self.change_btn_page(6, stackedWidget))
        btn_lef_mi_upper.clicked.connect(lambda: self.change_btn_page(7, stackedWidget))
        btn_lef_eye.clicked.connect(lambda: self.change_btn_page(8, stackedWidget))  # FIXME.
        # ⭐ 这里不再设置 currentIndex，避免和 change_btn_page 冲突
        # stackedWidget.setCurrentIndex(1)

    # ⭐ 只通过属性 selected 控制导航按钮的高亮状态，不再直接 setStyleSheet
    def _set_nav_selected(self, button: QtWidgets.QPushButton, selected: bool):
        button.setProperty("selected", selected)
        # 触发 QSS 重新应用
        button.style().unpolish(button)
        button.style().polish(button)
        button.update()

    def change_btn_page(self, current_index, stackedWidget):
        stackedWidget.setCurrentIndex(current_index)

        # 先把所有导航按钮重置为未选中
        for btn in self.nav_buttons:
            self._set_nav_selected(btn, False)

        # 根据当前页面索引设置相应按钮的高亮颜色 & 标题
        if current_index == 0:
            self._set_nav_selected(self.btn_lef_home, True)
            self.proj_title.setText("Emotion Recognition")
        elif current_index == 1:
            self._set_nav_selected(self.btn_lef_new, True)
            self.proj_title.setText("Data Collection")
        elif current_index == 2:
            self._set_nav_selected(self.btn_lef_save, True)
            self.proj_title.setText("N Back (1)")
        elif current_index == 3:
            self._set_nav_selected(self.btn_lef_exit, True)
            self.proj_title.setText("N Back, 按下【Start Sequence】，会同时开始记录脑电信号")
        elif current_index == 4:
            self._set_nav_selected(self.btn_lef_stroop, True)
            self.proj_title.setText("Stroop Test, 按下【Start Stroop】，会同时开始记录脑电信号")
        elif current_index == 5:
            self._set_nav_selected(self.btn_lef_ma, True)
            self.proj_title.setText("Mental Arithmetic, 按下【Start Calculation】，会同时开始记录脑电信号")
        elif current_index == 6:
            self._set_nav_selected(self.btn_lef_mi_lower, True)
            self.proj_title.setText("Motor Imagery(Lower Limb), 按下【开始实验】，会同时开始记录脑电信号")
        elif current_index == 7:
            self._set_nav_selected(self.btn_lef_mi_upper, True)
            self.proj_title.setText("Motor Imagery(Upper Limb), 按下【开始实验】，会同时开始记录脑电信号")
        elif current_index == 8:  # FIXME.
            self._set_nav_selected(self.btn_lef_eye, True)
            self.proj_title.setText("睁眼/闭眼实验, 按下【开始实验】，会同时开始记录脑电信号")

    def retranslateUi(self, MainWindow):
        _translate = QtCore.QCoreApplication.translate
        MainWindow.setWindowTitle(_translate("MainWindow", "MainWindow"))
        # 初始标题无所谓，会在 change_btn_page(1, ...) 时被覆盖
        self.proj_title.setText(_translate("MainWindow", "Emotion Recognition"))
        self.proj_date.setText(_translate("MainWindow", "Date"))


def load_qss(app: QApplication):
    with open('styles/styles.qss', 'r', encoding='utf-8') as file:
        qss = file.read()
        app.setStyleSheet(qss)


if __name__ == '__main__':
    app = QApplication(sys.argv)

    load_qss(app)

    ui = Ui_MainWindow()
    ui.showMaximized()

    sys.exit(app.exec())
