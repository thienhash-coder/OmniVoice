import os
import sys
import traceback
import requests
import webbrowser

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl
from PyQt6.QtGui import QFont
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QProgressBar,
    QPushButton, QStackedWidget, QTextEdit, QVBoxLayout, QWidget, QTextBrowser
)

# ==========================================
# 🛠 CẤU HÌNH GITHUB RELEASES
# ==========================================
APP_VERSION = "v2.0.1"

# Thay bằng tên tài khoản và tên Repository của bạn trên Github
GITHUB_OWNER = "thienhash-coder"  # VD: "nguyenvana"
GITHUB_REPO = "OmniVoice"        # VD: "OmniVoice-Cloud"
# ==========================================

class CheckUpdateWorker(QThread):
    # Truyền về: Lời nhắn, Thành công hay không, Có bản mới không, Link tải, Tên phiên bản
    result_signal = pyqtSignal(str, bool, bool, str, str)

    def __init__(self, is_startup=False):
        super().__init__()
        self.is_startup = is_startup

    def run(self):
        try:
            if not GITHUB_OWNER or not GITHUB_REPO:
                if not self.is_startup:
                    self.result_signal.emit("Chưa cấu hình tài khoản GitHub.", False, False, "", "")
                return
                
            api_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
            response = requests.get(api_url, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                online_version = data.get("tag_name", "")
                
                # Tìm link tải trực tiếp của file .exe trong mục Assets
                download_url = data.get("html_url", "") # Mặc định là trang web
                for asset in data.get("assets", []):
                    if asset["name"].endswith(".exe"):
                        download_url = asset["browser_download_url"]
                        break
                
                if online_version and online_version.lower() != APP_VERSION.lower():
                    msg = f"Có bản cập nhật mới ({online_version}). Bạn có muốn tải phiên bản mới nhất không?"
                    self.result_signal.emit(msg, True, True, download_url, online_version)
                else:
                    if not self.is_startup:
                        self.result_signal.emit("✅ Phần mềm của bạn đang ở phiên bản mới nhất!", True, False, "", "")
            else:
                if not self.is_startup:
                    self.result_signal.emit(f"❌ Lỗi truy xuất GitHub API: {response.status_code}", False, False, "", "")
        except Exception as e:
            if not self.is_startup:
                self.result_signal.emit(f"❌ Lỗi mạng khi kiểm tra cập nhật:\n{str(e)}", False, False, "", "")

class DownloadWorker(QThread):
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)

    def __init__(self, url, save_path):
        super().__init__()
        self.url = url
        self.save_path = save_path

    def run(self):
        try:
            response = requests.get(self.url, stream=True, timeout=10)
            response.raise_for_status()
            total_size = int(response.headers.get('content-length', 0))
            
            downloaded = 0
            with open(self.save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            progress = int((downloaded / total_size) * 100)
                            self.progress_signal.emit(progress)
            self.finished_signal.emit(self.save_path)
        except Exception as e:
            self.error_signal.emit(str(e))
class EngineInitWorker(QThread):
    success_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)

    def __init__(self, api_url):
        super().__init__()
        self.api_url = api_url

    def run(self):
        try:
            base_url = self.api_url.replace("/generate", "").rstrip("/")
            requests.get(base_url, timeout=7)
            self.success_signal.emit("COLAB GPU T4 (Cloud)")
        except Exception as e:
            self.error_signal.emit(str(e))

class GenerateWorker(QThread):
    finished_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)

    def __init__(self, texts_to_process, mode, api_url, ref_text="", instruct="", output_dir="outputs"):
        super().__init__()
        self.texts_to_process = texts_to_process  
        self.mode = mode
        self.api_url = api_url
        self.ref_text = ref_text
        self.instruct = instruct
        self.output_dir = output_dir

    def run(self):
        try:
            os.makedirs(self.output_dir, exist_ok=True)
            last_output_path = ""
            total = len(self.texts_to_process)
            
            api_endpoint = self.api_url.rstrip("/")
            if not api_endpoint.endswith("/generate"):
                api_endpoint += "/generate"

            for idx, (task_name, text_content, ref_audio_path) in enumerate(self.texts_to_process, 1):
                if not text_content.strip():
                    continue

                self.progress_signal.emit(f"⏳ Đang xử lý ({idx}/{total}): {task_name}...")

                data = {
                    "text": text_content,
                    "mode": self.mode,
                    "instruct": self.instruct,
                    "ref_text": self.ref_text
                }
                
                files = {}
                if self.mode == "clone" and ref_audio_path and os.path.exists(ref_audio_path):
                    files["ref_audio"] = open(ref_audio_path, "rb")

                if files:
                    response = requests.post(api_endpoint, data=data, files=files)
                    for f in files.values():
                        f.close()
                else:
                    response = requests.post(api_endpoint, data=data)
                
                if response.status_code == 200:
                    output_path = os.path.join(self.output_dir, f"{task_name}.wav")
                    with open(output_path, "wb") as f:
                        f.write(response.content)
                    last_output_path = output_path
                else:
                    raise Exception(f"Lỗi từ Server Colab: {response.text}")

            if last_output_path:
                self.finished_signal.emit(last_output_path)
            else:
                raise ValueError("Không có nội dung hợp lệ nào được xử lý.")
                
        except Exception as e:
            traceback.print_exc()
            self.error_signal.emit(str(e))

class AudioPlayerWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.audio_path = ""
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.init_ui()

    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setStyleSheet("""
            QPushButton { background-color: #89b4fa; color: #11111b; border: none; border-radius: 6px; padding: 6px 15px; font-weight: bold; }
            QPushButton:hover { background-color: #b4befe; }
            QPushButton:disabled { background-color: #45475a; color: #a6adc8; }
            QLabel { color: #bac2de; border: none; background: transparent; }
        """)

        self.play_btn = QPushButton("▶ Phát Âm Thanh")
        self.play_btn.clicked.connect(self.toggle_play)
        self.play_btn.setEnabled(False)
        self.status_label = QLabel("Chưa có file âm thanh")

        layout.addWidget(self.play_btn)
        layout.addSpacing(10)
        layout.addWidget(self.status_label)
        layout.addStretch()

    def load_audio(self, path):
        self.audio_path = path
        if path and os.path.exists(path):
            self.player.setSource(QUrl.fromLocalFile(path))
            self.play_btn.setEnabled(True)
            self.play_btn.setText("▶ Phát")
            self.status_label.setText(f"Sẵn sàng: {os.path.basename(path)}")
        else:
            self.player.setSource(QUrl())
            self.play_btn.setEnabled(False)
            self.status_label.setText("File âm thanh trống hoặc không tồn tại")

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.play_btn.setText("▶ Tiếp tục")
        else:
            self.player.play()
            self.play_btn.setText("⏸ Tạm dừng")

class OmniVoiceMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"OmniVoice Studio - Cloud Edition ({APP_VERSION})")
        self.resize(1100, 780)
        self.setMinimumSize(950, 680)
        
        self.init_ui()
        self.apply_stylesheet()
        # Thêm dòng này để tự kiểm tra bản cập nhật (ngầm) khi vừa mở app
        self.run_check_update(is_startup=True)

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- TẠO THANH SIDEBAR ---
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(15, 30, 15, 30)
        sidebar_layout.setSpacing(10)

        app_logo = QLabel("🌍 OmniVoice Cloud")
        app_logo.setObjectName("AppLogo")
        app_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sidebar_layout.addWidget(app_logo)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background-color: #313244; max-height: 1px; margin: 15px 0;")
        sidebar_layout.addWidget(line)

        self.btn_design = QPushButton("  🎨  Thiết Kế Giọng")
        self.btn_design.setCheckable(True)
        self.btn_design.setChecked(True)
        self.btn_design.setObjectName("SidebarBtn")

        self.btn_clone = QPushButton("  🎭  Clone Giọng")
        self.btn_clone.setCheckable(True)
        self.btn_clone.setObjectName("SidebarBtn")

        self.btn_settings = QPushButton("  ⚙️  Kết Nối Colab")
        self.btn_settings.setCheckable(True)
        self.btn_settings.setObjectName("SidebarBtn")

        self.btn_guide = QPushButton("  📖  Hướng Dẫn & Cập Nhật")
        self.btn_guide.setCheckable(True)
        self.btn_guide.setObjectName("SidebarBtn")

        self.menu_buttons = [self.btn_design, self.btn_clone, self.btn_settings, self.btn_guide]
        for btn in self.menu_buttons:
            btn.clicked.connect(self.on_menu_click)
            sidebar_layout.addWidget(btn)

        sidebar_layout.addStretch()
        self.lbl_sdk_status = QLabel("Trạng thái: Chưa kết nối Server")
        self.lbl_sdk_status.setObjectName("StatusLabel")
        self.lbl_sdk_status.setStyleSheet("color: #fab387;")
        self.lbl_sdk_status.setWordWrap(True)
        sidebar_layout.addWidget(self.lbl_sdk_status)

        main_layout.addWidget(sidebar, stretch=1)

        # --- TẠO KHU VỰC NỘI DUNG ---
        self.content_stack = QStackedWidget()
        self.content_stack.setObjectName("ContentArea")

        self.create_design_page()
        self.create_clone_page()
        self.create_settings_page()
        self.create_guide_page()

        main_layout.addWidget(self.content_stack, stretch=4)

    def create_design_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(35, 25, 35, 25)

        title = QLabel("Thiết Kế Giọng Đọc (Voice Design & Auto)")
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        
        txt_source_layout = QHBoxLayout()
        self.txt_source_path = QLineEdit()
        self.txt_source_path.setPlaceholderText("Đường dẫn file .txt hoặc thư mục chứa các file .txt...")
        self.btn_browse_txt = QPushButton("📄 Chọn File TXT")
        self.btn_browse_txt.clicked.connect(self.browse_txt_file)
        self.btn_browse_dir = QPushButton("📁 Chọn Thư Mục TXT")
        self.btn_browse_dir.clicked.connect(self.browse_txt_dir)
        
        txt_source_layout.addWidget(self.txt_source_path)
        txt_source_layout.addWidget(self.btn_browse_txt)
        txt_source_layout.addWidget(self.btn_browse_dir)
        layout.addLayout(txt_source_layout)

        layout.addWidget(QLabel("Thuộc Tính Giọng (Instruct):"))
        self.txt_instruct = QLineEdit()
        self.txt_instruct.setPlaceholderText("Ví dụ: male, high pitch, whisper...")
        layout.addWidget(self.txt_instruct)

        layout.addWidget(QLabel("Hoặc Nhập Văn Bản Trực Tiếp:"))
        self.txt_design_input = QTextEdit()
        self.txt_design_input.setPlaceholderText("Nhập nội dung văn bản trực tiếp vào đây...")
        layout.addWidget(self.txt_design_input)

        self.design_player = AudioPlayerWidget()
        layout.addWidget(self.design_player)

        self.lbl_design_status = QLabel("")
        self.lbl_design_status.setStyleSheet("color: #a6e3a1; font-weight: bold;")
        layout.addWidget(self.lbl_design_status)

        self.design_progress = QProgressBar()
        self.design_progress.setRange(0, 0)
        self.design_progress.setVisible(False)
        self.design_progress.setFixedHeight(18)
        layout.addWidget(self.design_progress)

        self.btn_run_design = QPushButton("⚡ TẠO ÂM THANH (CLOUD GPU)")
        self.btn_run_design.setObjectName("PrimaryActionBtn")
        self.btn_run_design.setEnabled(False)
        self.btn_run_design.clicked.connect(self.run_design_task)
        layout.addWidget(self.btn_run_design)

        self.content_stack.addWidget(page)

    def create_clone_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(35, 25, 35, 25)

        title = QLabel("Nhại Giọng AI (Tự Động Ghép Cặp)")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        ref_dir_layout = QHBoxLayout()
        # Đã loại bỏ mặc định giong-doc, hiển thị ô trống
        self.txt_ref_dir_path = QLineEdit()
        self.txt_ref_dir_path.setPlaceholderText("Đường dẫn thư mục chứa các giọng mẫu...")
        
        self.btn_browse_ref_dir = QPushButton("📁 Chọn Thư Mục Giọng")
        self.btn_browse_ref_dir.clicked.connect(self.browse_ref_dir)
        
        ref_dir_layout.addWidget(self.txt_ref_dir_path)
        ref_dir_layout.addWidget(self.btn_browse_ref_dir)
        layout.addLayout(ref_dir_layout)

        layout.addWidget(QLabel("Văn Bản Của Âm Thanh Mẫu (Ref Text - Tùy chọn):"))
        self.txt_ref_text = QLineEdit()
        self.txt_ref_text.setPlaceholderText("Gõ lại nội dung nếu các file mẫu dùng chung 1 văn bản gốc...")
        layout.addWidget(self.txt_ref_text)

        txt_clone_source_layout = QHBoxLayout()
        self.txt_clone_source_path = QLineEdit()
        self.txt_clone_source_path.setPlaceholderText("Đường dẫn file .txt hoặc thư mục chứa các file .txt nội dung...")
        self.btn_browse_clone_txt = QPushButton("📄 Chọn TXT")
        self.btn_browse_clone_txt.clicked.connect(self.browse_clone_txt_file)
        self.btn_browse_clone_dir = QPushButton("📁 Chọn Thư Mục TXT")
        self.btn_browse_clone_dir.clicked.connect(self.browse_clone_txt_dir)
        
        txt_clone_source_layout.addWidget(self.txt_clone_source_path)
        txt_clone_source_layout.addWidget(self.btn_browse_clone_txt)
        txt_clone_source_layout.addWidget(self.btn_browse_clone_dir)
        layout.addLayout(txt_clone_source_layout)

        layout.addWidget(QLabel("Hoặc Nhập Văn Bản Đọc Trực Tiếp:"))
        self.txt_clone_input = QTextEdit()
        self.txt_clone_input.setPlaceholderText("Nhập văn bản trực tiếp...")
        layout.addWidget(self.txt_clone_input)

        self.clone_player = AudioPlayerWidget()
        layout.addWidget(self.clone_player)

        self.lbl_clone_status = QLabel("")
        self.lbl_clone_status.setStyleSheet("color: #a6e3a1; font-weight: bold;")
        layout.addWidget(self.lbl_clone_status)

        self.clone_progress = QProgressBar()
        self.clone_progress.setRange(0, 0)
        self.clone_progress.setVisible(False)
        self.clone_progress.setFixedHeight(18)
        layout.addWidget(self.clone_progress)

        self.btn_run_clone = QPushButton("🎭 TIẾN HÀNH CLONE TRÊN CLOUD")
        self.btn_run_clone.setObjectName("PrimaryActionBtn")
        self.btn_run_clone.setEnabled(False)
        self.btn_run_clone.clicked.connect(self.run_clone_task)
        layout.addWidget(self.btn_run_clone)

        self.content_stack.addWidget(page)

    def create_settings_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(35, 30, 35, 30)

        title = QLabel("Cài Đặt Hệ Thống & API")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(15)

        grid.addWidget(QLabel("Đường dẫn API (Ngrok URL):"), 0, 0)
        self.txt_api_url = QLineEdit("https://headphone-drizzle-sculpture.ngrok-free.dev")
        self.txt_api_url.setPlaceholderText("Dán link ngrok của bạn (hoặc bạn bè) vào đây...")
        self.txt_api_url.setStyleSheet("border: 1px solid #f38ba8; color: #f38ba8;") 
        grid.addWidget(self.txt_api_url, 0, 1)

        grid.addWidget(QLabel("Thư Mục Lưu Audio (Output):"), 1, 0)
        self.txt_output_dir = QLineEdit(os.path.abspath("outputs"))
        self.btn_browse_out = QPushButton("📁 Chọn Thư Mục")
        self.btn_browse_out.clicked.connect(self.browse_output_dir)

        out_layout = QHBoxLayout()
        out_layout.addWidget(self.txt_output_dir)
        out_layout.addWidget(self.btn_browse_out)
        grid.addLayout(out_layout, 1, 1)

        layout.addLayout(grid)
        layout.addSpacing(20)

        guide_box = QFrame()
        guide_box.setObjectName("GuideBox")
        guide_layout = QVBoxLayout(guide_box)
        guide_layout.addWidget(QLabel("🚀 KẾT NỐI VỚI GOOGLE COLAB SERVER"))
        guide_layout.addWidget(QLabel("Hãy dán chính xác đường link Ngrok được cấp từ Google Colab vào ô phía trên.\nSau đó bấm nút bên dưới để kiểm tra xem máy tính đã thông mạng với Colab chưa."))
        guide_layout.itemAt(0).widget().setStyleSheet("color: #a6e3a1; font-weight: bold; font-size: 16px;")
        guide_layout.itemAt(1).widget().setStyleSheet("color: #bac2de; font-size: 13px;")
        
        self.btn_load_model = QPushButton("🔗 KIỂM TRA & KẾT NỐI SERVER CLOUD")
        self.btn_load_model.setStyleSheet("background-color: #f9e2af; color: #11111b; font-weight: bold; padding: 15px; border-radius: 10px; margin-top: 10px;")
        self.btn_load_model.clicked.connect(self.load_model_async)
        guide_layout.addWidget(self.btn_load_model)
        
        layout.addWidget(guide_box)
        layout.addStretch()

        self.content_stack.addWidget(page)

    def create_guide_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(35, 25, 35, 25)

        title = QLabel("📖 Hướng Dẫn Sử Dụng & Cập Nhật")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        browser = QTextBrowser()
        browser.setStyleSheet("background-color: #1e1e2e; border: 1px solid #313244; border-radius: 8px; padding: 10px; color: #cdd6f4;")
        browser.setOpenExternalLinks(True)
        html_content = f"""
        <h2 style='color: #89b4fa;'>🚀 Quy trình 3 bước sử dụng OmniVoice Cloud</h2>
        <ol style='font-size: 14px; line-height: 1.6;'>
            <li><b>Bước 1: Khởi động Server Đám Mây</b><br>
            Mở file Google Colab của tác giả, bấm <code style='background: #313244; padding: 2px 4px;'>Runtime -> Run all</code>. Chờ vài phút để thấy link Ngrok.</li>
            <li><b>Bước 2: Kết nối Giao Diện Máy Tính</b><br>
            Sang tab <b>⚙️ Kết Nối Colab</b> trên phần mềm, dán link vừa copy vào ô Ngrok URL và bấm <b>Kiểm tra kết nối</b>.</li>
            <li><b>Bước 3: Bắt đầu Tạo Giọng Đọc</b><br>
            Sử dụng tab Thiết Kế hoặc Clone Giọng để tạo âm thanh.</li>
        </ol>
        <hr style='border: 1px solid #313244;'>
        <p style='color: #a6e3a1;'>💡 <b>Mẹo nhỏ:</b> Bản cập nhật (nếu có) sẽ được tự động đồng bộ từ kho GitHub Releases chính thức của phần mềm.</p>
        """
        browser.setHtml(html_content)
        layout.addWidget(browser)

        update_box = QFrame()
        update_box.setStyleSheet("background-color: #181825; border: 1px solid #45475a; border-radius: 8px;")
        update_layout = QHBoxLayout(update_box)
        
        lbl_version = QLabel(f"Phiên bản phần mềm: <b>{APP_VERSION}</b>")
        lbl_version.setStyleSheet("font-size: 14px; color: #bac2de;")
        
        self.btn_check_update = QPushButton("🔄 Kiểm Tra Bản Cập Nhật (GitHub)")
        self.btn_check_update.setStyleSheet("background-color: #f38ba8; color: #11111b; font-weight: bold; padding: 10px; border-radius: 6px;")
        self.btn_check_update.clicked.connect(self.run_check_update)

        update_layout.addWidget(lbl_version)
        update_layout.addStretch()
        update_layout.addWidget(self.btn_check_update)
        
        layout.addWidget(update_box)
        self.content_stack.addWidget(page)

    def on_menu_click(self):
        sender = self.sender()
        for btn in self.menu_buttons:
            btn.setChecked(btn == sender)

        if sender == self.btn_design:
            self.content_stack.setCurrentIndex(0)
        elif sender == self.btn_clone:
            self.content_stack.setCurrentIndex(1)
        elif sender == self.btn_settings:
            self.content_stack.setCurrentIndex(2)
        elif sender == self.btn_guide:
            self.content_stack.setCurrentIndex(3)

    def run_check_update(self, is_startup=False):
        if not is_startup:
            self.btn_check_update.setEnabled(False)
            self.btn_check_update.setText("⏳ Đang kiểm tra trên GitHub...")
        
        self.update_worker = CheckUpdateWorker(is_startup=is_startup)
        self.update_worker.result_signal.connect(self.on_update_finished)
        self.update_worker.start()

    def on_update_finished(self, msg, is_success, has_new_version, download_url, online_version):
        self.btn_check_update.setEnabled(True)
        self.btn_check_update.setText("🔄 Kiểm Tra Bản Cập Nhật (GitHub)")
        
        if has_new_version:
            reply = QMessageBox.question(self, "Có Bản Cập Nhật Mới", msg, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self.start_downloading_update(download_url, online_version)
        elif not self.update_worker.is_startup:
            if is_success:
                QMessageBox.information(self, "Cập nhật", msg)
            else:
                QMessageBox.warning(self, "Thông báo", msg)

    def start_downloading_update(self, url, version):
        if not url.endswith(".exe"):
            # Nếu GitHub không có file .exe, mở trình duyệt
            webbrowser.open(url)
            return
            
        # Lưu file mới ra ngay cùng thư mục chứa app hiện tại
        current_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        save_path = os.path.join(current_dir, f"OmniVoice_Cloud_{version}.exe")
        
        self.progress_dialog = QProgressBar(self)
        self.progress_dialog.setRange(0, 100)
        self.progress_dialog.setWindowTitle("Đang tải bản cập nhật...")
        self.progress_dialog.resize(400, 30)
        self.progress_dialog.show()

        self.btn_check_update.setText("⏳ Đang tải...")
        self.btn_check_update.setEnabled(False)

        self.download_worker = DownloadWorker(url, save_path)
        self.download_worker.progress_signal.connect(self.progress_dialog.setValue)
        self.download_worker.finished_signal.connect(self.on_download_success)
        self.download_worker.error_signal.connect(self.on_download_error)
        self.download_worker.start()

    def on_download_success(self, save_path):
        self.progress_dialog.hide()
        self.btn_check_update.setText("🔄 Kiểm Tra Bản Cập Nhật (GitHub)")
        self.btn_check_update.setEnabled(True)
        QMessageBox.information(self, "Tải thành công", f"Đã tải phiên bản mới thành công!\n\nFile được lưu tại:\n{save_path}\n\nHãy tắt phần mềm cũ và chạy file mới nhé.")

    def on_download_error(self, err_msg):
        self.progress_dialog.hide()
        self.btn_check_update.setText("🔄 Kiểm Tra Bản Cập Nhật (GitHub)")
        self.btn_check_update.setEnabled(True)
        QMessageBox.critical(self, "Lỗi tải xuống", f"Không thể tải bản cập nhật:\n{err_msg}")

    def browse_txt_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Chọn File TXT", "", "Text Files (*.txt);;All Files (*.*)")
        if file_path:
            self.txt_source_path.setText(file_path)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    self.txt_design_input.setPlainText(f.read())
            except Exception as e:
                QMessageBox.warning(self, "Lỗi đọc file", str(e))

    def browse_txt_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Chọn Thư Mục Chứa Các File TXT")
        if dir_path:
            self.txt_source_path.setText(dir_path)

    def browse_clone_txt_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Chọn File TXT", "", "Text Files (*.txt);;All Files (*.*)")
        if file_path:
            self.txt_clone_source_path.setText(file_path)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    self.txt_clone_input.setPlainText(f.read())
            except Exception as e:
                QMessageBox.warning(self, "Lỗi đọc file", str(e))

    def browse_clone_txt_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Chọn Thư Mục Chứa Các File TXT")
        if dir_path:
            self.txt_clone_source_path.setText(dir_path)
            
    def browse_ref_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Chọn Thư Mục Chứa Giọng Mẫu")
        if dir_path:
            self.txt_ref_dir_path.setText(dir_path)

    def browse_output_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Chọn Thư Mục Lưu Kết Quả")
        if dir_path:
            self.txt_output_dir.setText(dir_path)

    def load_model_async(self):
        api_url = self.txt_api_url.text().strip()
        if not api_url:
            QMessageBox.warning(self, "Thiếu thông tin", "Vui lòng nhập đường link API Ngrok trước khi kết nối!")
            return

        self.btn_load_model.setEnabled(False)
        self.btn_load_model.setText("⏳ ĐANG KẾT NỐI SERVER...")
        self.lbl_sdk_status.setText("Trạng thái: Đang kiểm tra kết nối API...")
        self.lbl_sdk_status.setStyleSheet("color: #fab387;")

        self.init_thread = EngineInitWorker(api_url=api_url)
        self.init_thread.success_signal.connect(self.on_model_loaded)
        self.init_thread.error_signal.connect(self.on_model_failed)
        self.init_thread.start()

    def on_model_loaded(self, device):
        self.lbl_sdk_status.setText(f"🟢 API Hoạt Động Tốt ({device})")
        self.lbl_sdk_status.setStyleSheet("color: #a6e3a1;")
        self.btn_load_model.setText("✅ ĐÃ KẾT NỐI THÀNH CÔNG")
        self.txt_api_url.setStyleSheet("border: 1px solid #a6e3a1; color: #a6e3a1;")
        
        self.btn_run_design.setEnabled(True)
        self.btn_run_clone.setEnabled(True)

    def on_model_failed(self, err_msg):
        self.btn_load_model.setEnabled(True)
        self.btn_load_model.setText("❌ KẾT NỐI LỖI, THỬ LẠI")
        self.lbl_sdk_status.setText("🔴 Lỗi: Không thể kết nối tới link API!")
        self.lbl_sdk_status.setStyleSheet("color: #f38ba8;")
        self.txt_api_url.setStyleSheet("border: 1px solid #f38ba8; color: #f38ba8;")
        QMessageBox.critical(self, "Lỗi Kết Nối", "Vui lòng kiểm tra lại đường link Ngrok hoặc đảm bảo Colab đang chạy.\n\nChi tiết lỗi: " + err_msg)

    def prepare_tasks(self, source_path_str, text_box_content):
        tasks = []
        source_path = source_path_str.strip()

        if source_path and os.path.exists(source_path):
            if os.path.isdir(source_path):
                txt_files = sorted([f for f in os.listdir(source_path) if f.endswith(".txt")])
                for file_name in txt_files:
                    full_path = os.path.join(source_path, file_name)
                    task_name = os.path.splitext(file_name)[0]
                    try:
                        with open(full_path, "r", encoding="utf-8") as f:
                            content = f.read().strip()
                            if content:
                                tasks.append((task_name, content))
                    except Exception:
                        pass
            elif os.path.isfile(source_path) and source_path.endswith(".txt"):
                task_name = os.path.splitext(os.path.basename(source_path))[0]
                with open(source_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        tasks.append((task_name, content))
        
        if not tasks and text_box_content.strip():
            tasks.append(("omnivoice_output", text_box_content.strip()))

        return tasks

    def on_design_progress(self, msg):
        self.lbl_design_status.setText(msg)

    def on_clone_progress(self, msg):
        self.lbl_clone_status.setText(msg)

    def run_design_task(self):
        api_url = self.txt_api_url.text().strip()
        source_path = self.txt_source_path.text()
        text_content = self.txt_design_input.toPlainText()
        instruct = self.txt_instruct.text().strip()
        
        raw_tasks = self.prepare_tasks(source_path, text_content)
        tasks_with_audio = [(name, txt, None) for name, txt in raw_tasks]
        
        if not tasks_with_audio:
            QMessageBox.warning(self, "Cảnh báo", "Vui lòng nhập văn bản hoặc chọn file/thư mục .txt hợp lệ!")
            return

        mode = "design" if instruct else "auto"
        output_dir = self.txt_output_dir.text()

        self.btn_run_design.setEnabled(False)
        self.lbl_design_status.setText("⏳ Đang gửi tác vụ lên API...")
        self.design_progress.setVisible(True)

        self.gen_thread = GenerateWorker(texts_to_process=tasks_with_audio, mode=mode, api_url=api_url, instruct=instruct, output_dir=output_dir)
        self.gen_thread.progress_signal.connect(self.on_design_progress)
        self.gen_thread.finished_signal.connect(self.on_design_success)
        self.gen_thread.error_signal.connect(self.on_design_error)
        self.gen_thread.start()

    def on_design_success(self, file_path):
        self.btn_run_design.setEnabled(True)
        self.design_progress.setVisible(False)
        self.lbl_design_status.setText(f"🎉 Hoàn thành xử lý! File cuối lưu tại: {file_path}")
        self.design_player.load_audio(file_path)

    def on_design_error(self, err_msg):
        self.btn_run_design.setEnabled(True)
        self.design_progress.setVisible(False)
        self.lbl_design_status.setText(f"❌ Lỗi: {err_msg[:50]}...")
        QMessageBox.critical(self, "Lỗi API", err_msg)

    def run_clone_task(self):
        api_url = self.txt_api_url.text().strip()
        ref_source = self.txt_ref_dir_path.text().strip()
        source_path = self.txt_clone_source_path.text().strip()
        text_content = self.txt_clone_input.toPlainText()
        ref_text = self.txt_ref_text.text().strip()
        
        if not ref_source or not os.path.exists(ref_source):
            QMessageBox.warning(self, "Cảnh báo", "Vui lòng chọn thư mục chứa giọng mẫu hợp lệ!")
            return

        raw_tasks = self.prepare_tasks(source_path, text_content)
        if not raw_tasks:
            QMessageBox.warning(self, "Cảnh báo", "Vui lòng nhập văn bản hoặc chọn file/thư mục .txt để clone!")
            return

        # 🛠 Tự động lấy tất cả audio và ghép cặp tuần tự
        exts = (".wav", ".mp3", ".m4a")
        ref_audio_files = sorted([os.path.join(ref_source, f) for f in os.listdir(ref_source) if f.lower().endswith(exts)])
        
        if not ref_audio_files:
            QMessageBox.warning(self, "Cảnh báo", "Không tìm thấy file âm thanh nào trong thư mục giọng mẫu!")
            return
            
        paired_tasks = []
        for idx, (task_name, content) in enumerate(raw_tasks):
            chosen_audio = ref_audio_files[idx % len(ref_audio_files)]
            paired_tasks.append((task_name, content, chosen_audio))

        output_dir = self.txt_output_dir.text()
        self.btn_run_clone.setEnabled(False)
        self.lbl_clone_status.setText("⏳ Đang gửi lệnh clone sang API...")
        self.clone_progress.setVisible(True)

        self.gen_thread = GenerateWorker(texts_to_process=paired_tasks, mode="clone", api_url=api_url, ref_text=ref_text, output_dir=output_dir)
        self.gen_thread.progress_signal.connect(self.on_clone_progress)
        self.gen_thread.finished_signal.connect(self.on_clone_success)
        self.gen_thread.error_signal.connect(self.on_clone_error)
        self.gen_thread.start()

    def on_clone_success(self, file_path):
        self.btn_run_clone.setEnabled(True)
        self.clone_progress.setVisible(False)
        self.lbl_clone_status.setText(f"🎉 Clone hoàn tất! File cuối lưu tại: {file_path}")
        self.clone_player.load_audio(file_path)

    def on_clone_error(self, err_msg):
        self.btn_run_clone.setEnabled(True)
        self.clone_progress.setVisible(False)
        self.lbl_clone_status.setText(f"❌ Lỗi Clone: {err_msg[:50]}...")
        QMessageBox.critical(self, "Lỗi Clone Giọng", err_msg)

    def apply_stylesheet(self):
        style = """
        QMainWindow { background-color: #11111b; }
        QWidget { color: #cdd6f4; font-family: 'Segoe UI', system-ui, sans-serif; font-size: 13px; }
        #PageTitle { font-size: 24px; font-weight: bold; color: #f5e0dc; margin-bottom: 5px; }
        #PageDesc { font-size: 14px; color: #bac2de; margin-bottom: 15px; }
        #Sidebar { background-color: #181825; border-right: 1px solid #313244; }
        #AppLogo { font-size: 20px; font-weight: bold; color: #a6e3a1; margin-top: 10px; }
        #SidebarBtn { color: #cdd6f4; background-color: transparent; border: none; border-radius: 8px; padding: 12px 15px; font-size: 14px; text-align: left; }
        #SidebarBtn:hover { background-color: #313244; }
        #SidebarBtn:checked { background-color: #a6e3a1; color: #11111b; font-weight: bold; }
        #StatusLabel { font-size: 12px; font-weight: bold; }
        #ContentArea { background-color: #11111b; }
        QTextEdit, QLineEdit { background-color: #1e1e2e; border: 1px solid #45475a; border-radius: 8px; padding: 8px 10px; color: #cdd6f4; }
        QTextEdit:focus, QLineEdit:focus { border: 1px solid #a6e3a1; }
        QLabel { font-weight: 500; color: #b4befe; }
        QPushButton { background-color: #313244; border: 1px solid #45475a; border-radius: 8px; padding: 8px 16px; color: #cdd6f4; font-weight: 600; }
        QPushButton:hover { background-color: #45475a; }
        #PrimaryActionBtn { background-color: #a6e3a1; color: #11111b; border: none; padding: 14px; font-size: 14px; letter-spacing: 1px; border-radius: 10px; }
        #PrimaryActionBtn:hover { background-color: #94e2d5; }
        #PrimaryActionBtn:disabled { background-color: #45475a; color: #a6adc8; }
        #GuideBox { background-color: #181825; border: 1px solid #f38ba8; border-radius: 10px; padding: 15px; margin-top: 15px; }
        QProgressBar { border: 1px solid #313244; border-radius: 9px; text-align: center; color: #11111b; background-color: #181825; height: 18px; font-weight: 800; font-size: 10px; }
        QProgressBar::chunk { background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #a6e3a1, stop:1 #89b4fa); border-radius: 8px; }
        """
        self.setStyleSheet(style)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    default_font = QFont("Segoe UI", 10)
    app.setFont(default_font)

    window = OmniVoiceMainWindow()
    window.show()
    sys.exit(app.exec())