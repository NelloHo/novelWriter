"""
novelWriter – Other Dialog Classes Tester
=========================================

This file is a part of novelWriter
Copyright 2018–2023, Veronica Berglyd Olsen

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful, but
WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.
"""

import pytest

from PyQt5.QtCore import QItemSelectionModel
from PyQt5.QtWidgets import QAction, QListWidgetItem, QDialog

from novelwriter.dialogs.quotes import GuiQuoteSelect
from novelwriter.dialogs.updates import GuiUpdates
from novelwriter.dialogs.editlabel import GuiEditLabel


@pytest.mark.gui
def testDlgOther_QuoteSelect(qtbot, nwGUI):
    """Test the quote symbols dialog.
    """
    nwQuot = GuiQuoteSelect(nwGUI)
    nwQuot.show()

    lastItem = ""
    for i in range(nwQuot.listBox.count()):
        anItem = nwQuot.listBox.item(i)
        assert isinstance(anItem, QListWidgetItem)
        nwQuot.listBox.clearSelection()
        nwQuot.listBox.setCurrentItem(anItem, QItemSelectionModel.Select)
        lastItem = anItem.text()[2]
        assert nwQuot.previewLabel.text() == lastItem

    nwQuot._doAccept()
    assert nwQuot.result() == QDialog.Accepted
    assert nwQuot.selectedQuote == lastItem

    # qtbot.stop()
    nwQuot._doReject()
    nwQuot.close()

# END Test testDlgOther_QuoteSelect


@pytest.mark.gui
def testDlgOther_Updates(qtbot, monkeypatch, nwGUI):
    """Test the check for updates dialog.
    """
    nwUpdate = GuiUpdates(nwGUI)
    nwUpdate.show()

    class mockData:
        def decode(self):
            return '{"tag_name": "v1.0", "created_at": "2021-01-01T12:00:00Z"}'

    class mockPayload:
        def read(self):
            return mockData()

    def mockUrlopenA(*a, **k):
        return None

    def mockUrlopenB(*a, **k):
        return mockPayload()

    # Faulty Return
    monkeypatch.setattr("novelwriter.dialogs.updates.urlopen", mockUrlopenA)
    nwUpdate.checkLatest()

    # Valid Return
    monkeypatch.setattr("novelwriter.dialogs.updates.urlopen", mockUrlopenB)
    nwUpdate.checkLatest()
    assert nwUpdate.latestValue.text().startswith("novelWriter v1.0")

    # Trigger from Menu
    nwGUI.mainMenu.aUpdates.activate(QAction.Trigger)

    # qtbot.stop()
    nwUpdate._doClose()

# END Test testDlgOther_Updates


@pytest.mark.gui
def testDlgOther_EditLabel(qtbot, monkeypatch):
    """Test the label editor dialog.
    """
    monkeypatch.setattr(GuiEditLabel, "exec_", lambda *a: None)

    with monkeypatch.context() as mp:
        mp.setattr(GuiEditLabel, "result", lambda *a: QDialog.Accepted)
        newLabel, dlgOk = GuiEditLabel.getLabel(None, text="Hello World")
        assert dlgOk is True
        assert newLabel == "Hello World"

    with monkeypatch.context() as mp:
        mp.setattr(GuiEditLabel, "result", lambda *a: QDialog.Rejected)
        newLabel, dlgOk = GuiEditLabel.getLabel(None, text="Hello World")
        assert dlgOk is False
        assert newLabel == "Hello World"

# END Test testDlgOther_EditLabel
