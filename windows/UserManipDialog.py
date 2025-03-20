from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QDialogButtonBox

class UserManipDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nouvelle Manip Utilisateur")

        layout = QVBoxLayout(self)

        # 1) Label d’explication
        explanation_label = QLabel(
            "Sélectionnez les éléments de l'historique composant la nouvelle manip type,\n"
            "puis entrez ci-dessous un nom.\n\n"
            "Vous retrouverez ensuite cette manip dans 'Ajouter une manip type'."
        )
        explanation_label.setWordWrap(True)
        layout.addWidget(explanation_label)

        # 2) Champ de saisie pour le nom
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Nom de la manip...")
        layout.addWidget(self.name_edit)

        # 3) Boutons OK / Annuler
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            parent=self
        )
        layout.addWidget(button_box)

        # Connexions
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

    def get_manip_name(self):
        """Renvoie le nom saisi par l'utilisateur."""
        return self.name_edit.text().strip()