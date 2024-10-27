from PyQt6 import QtWidgets, QtGui, QtCore
from PyQt6.QtCore import QUrl, Qt, QTimer
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import QFrame, QVBoxLayout, QWidget, QHBoxLayout, QLabel, QDialog, QFormLayout, QLineEdit, \
    QPushButton, QRadioButton, QButtonGroup, QApplication, QFileDialog


def load_qss(app: QApplication):
    with open('styles/styles.qss', 'r', encoding='utf-8') as file:
        qss = file.read()
        app.setStyleSheet(qss)

class SurveyDialog(QDialog):
    def __init__(self, parent=None):
        super(SurveyDialog, self).__init__(parent)
        self.setWindowTitle("Questionnaire")
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        # 问卷布局 - 设置 QFormLayout 作为主布局
        layout = QFormLayout(self)

        # 问题 1 - 文本输入，直接添加到 QVBoxLayout，无需多余的 QWidget
        self.question1_str = "问题 1：请描述您的观看体验"
        question1_label = QLabel(self.question1_str)
        self.question1_line_edit = QLineEdit()

        question1_layout = QVBoxLayout()
        question1_layout.addWidget(question1_label)
        question1_layout.addWidget(self.question1_line_edit)

        layout.addRow(question1_layout)

        # 问题 2 - 单选按钮，保持两行布局
        self.question2_str = "问题 2：您是否愿意观看更多此类视频？"
        question2_label = QLabel(self.question2_str)

        self.radio_button_yes = QRadioButton("是")
        self.radio_button_no = QRadioButton("否")

        # 将单选按钮添加到按钮组
        self.button_group = QButtonGroup(self)
        self.button_group.addButton(self.radio_button_yes)
        self.button_group.addButton(self.radio_button_no)

        question2_layout = QVBoxLayout()
        question2_layout.addWidget(question2_label)
        question2_layout.addWidget(self.radio_button_yes)
        question2_layout.addWidget(self.radio_button_no)

        layout.addRow(question2_layout)

        # 提交按钮，直接添加到布局
        self.submit_button = QPushButton("提交")
        self.submit_button.clicked.connect(self.accept)
        layout.addWidget(self.submit_button)

    def get_answers(self, index):
        return {
            "video_name": index,
            self.question1_str: self.question1_line_edit.text(),
            self.question2_str: "是" if self.radio_button_yes.isChecked() else "否"
        }

class Page1Widget(QWidget):
    def __init__(self, parent=None):

        super(Page1Widget, self).__init__(parent)

        self.current_video_index = 0

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(4)

        # 姓名输入框和提交按钮
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("请输入您的姓名")
        self.name_input.setFixedWidth(200)

        # 选择文件夹按钮和显示文件夹路径的标签
        self.folder_button = QPushButton("选择文件夹")
        self.folder_button.setFixedWidth(100)
        self.folder_label = QLabel("未选择文件夹")
        self.folder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.folder_label.setObjectName("folderLabel")

        folder_layout = QHBoxLayout()
        folder_layout.addWidget(self.folder_button)
        folder_layout.addWidget(self.folder_label)

        self.submit_button = QPushButton("开始")
        self.submit_button.setFixedWidth(80)

        # 视频播放组件
        self.video_widget = QVideoWidget()
        self.video_widget.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        self.video_widget.hide()
        self.audio_output = QAudioOutput(self)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self.video_widget)

        # 将控件添加到布局
        self.main_layout.addWidget(self.name_input, alignment=Qt.AlignmentFlag.AlignCenter)
        self.main_layout.addLayout(folder_layout)
        self.main_layout.addWidget(self.submit_button, alignment=Qt.AlignmentFlag.AlignCenter)
        self.main_layout.addWidget(self.video_widget)

        # 视频列表和索引
        self.video_list = [r'D:\movies\testing_1.mp4', r'D:\movies\testing_2.mp4']  # 视频路径列表
        self.responses = []

        # 连接按钮点击事件
        self.submit_button.clicked.connect(self.submit_)
        self.folder_button.clicked.connect(self.select_folder)
        self.player.mediaStatusChanged.connect(self.on_media_status_changed_)

        # 双击和单击事件
        self.is_full_screen = False
        self.single_click_timer = QTimer()
        self.single_click_timer.setSingleShot(True)
        self.single_click_timer.timeout.connect(self.handle_single_click)
        self.video_widget.mousePressEvent = self.single_click
        self.video_widget.mouseDoubleClickEvent = self.toggle_full_screen

    def select_folder(self):
        # 打开文件夹选择对话框
        folder_path = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if folder_path:
            # 显示所选文件夹路径
            self.folder_label.setText(folder_path)
            # 可以在这里将文件夹路径保存到视频列表或其他逻辑中
            self.video_list = [folder_path + f"/video_{i}.mp4" for i in range(1, 3)]  # 示例用途

    def single_click(self, event):
        self.single_click_timer.start(200)

    def handle_single_click(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def toggle_full_screen(self, event):
        self.single_click_timer.stop()
        self.is_full_screen = not self.is_full_screen
        self.video_widget.setFullScreen(self.is_full_screen)

    def submit_(self):
        name = self.name_input.text().strip()
        if name:
            self.current_video_index = 0  # 当前播放的视频索引
            self.responses = []
            self.playVideo()
        else:
            QtWidgets.QMessageBox.warning(self, "错误", "请输入姓名！")

    def playVideo(self):
        self.name_input.hide()
        self.submit_button.hide()
        self.video_widget.show()

        video_file_path = self.video_list[self.current_video_index]
        self.player.setSource(QUrl.fromLocalFile(video_file_path))
        self.player.play()

    def on_media_status_changed_(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            survey_dialog = SurveyDialog(self)
            if survey_dialog.exec() == QDialog.DialogCode.Accepted:
                answers = survey_dialog.get_answers(self.video_list[self.current_video_index])
                name = self.name_input.text().strip()

                # 将姓名和答案存入 responses 列表
                self.responses.append(answers)
                # print("调查结果：", self.responses)  # 打印累积的调查结果

                # 播放下一个视频或显示输入框和按钮
                self.current_video_index += 1
                if self.current_video_index < len(self.video_list):
                    self.playVideo()
                else:
                    self.video_widget.hide()
                    self.name_input.show()
                    self.submit_button.show()
                    self.update()
                    print("全部调查结果：", {name: self.responses})  # 打印最终结果

