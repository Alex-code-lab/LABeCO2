import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QLabel, QMessageBox
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

class TestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Test Sources Label")

        # Créer un layout principal
        main_widget = QWidget()
        main_layout = QVBoxLayout()
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

        # -- Créer le label "Sources" --
        self.sources_label = QLabel('<a href="#">Sources</a>')
        self.sources_label.setTextFormat(Qt.RichText)
        self.sources_label.setOpenExternalLinks(False)
        # Activer le clic sur le lien
        self.sources_label.setTextInteractionFlags(Qt.TextBrowserInteraction | Qt.LinksAccessibleByMouse)
        # Style éventuel (pour être sûr que la couleur est visible)
        self.sources_label.setStyleSheet("QLabel { color: blue; }")

        # Connecter le clic
        self.sources_label.linkActivated.connect(self.on_sources_link_clicked)

        # Ajouter dans le layout
        main_layout.addWidget(self.sources_label)

        self.resize(400, 200)

    def on_sources_link_clicked(self, link):
        """
        Quand l'utilisateur clique sur le lien "Sources"
        """
        QMessageBox.information(self, "Sources", "Petit pop-up avec mes références.")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TestWindow()
    window.show()
    sys.exit(app.exec())