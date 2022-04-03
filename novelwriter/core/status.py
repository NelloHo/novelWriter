"""
novelWriter – Project Item Status Class
=======================================
Data class for the status/importance settings of a project item

File History:
Created: 2019-05-19 [0.1.3]

This file is a part of novelWriter
Copyright 2018–2022, Veronica Berglyd Olsen

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

import logging
import novelwriter

from lxml import etree

from PyQt5.QtGui import QIcon, QPixmap, QColor

from novelwriter.common import checkInt

logger = logging.getLogger(__name__)


class NWStatus():

    def __init__(self):

        self._theLabels = []
        self._theColours = []
        self._theCounts = []
        self._theIcons = []
        self._theMap = {}
        self._theLength = 0
        self._theIndex = 0
        self._iconSize = novelwriter.CONFIG.pxInt(32)

        return

    def addEntry(self, theLabel, theColours):
        """Add a status entry to the status object, but ensure it isn't
        a duplicate.
        """
        theLabel = theLabel.strip()
        if self._getIndex(theLabel) is None:
            theIcon = QPixmap(self._iconSize, self._iconSize)
            theIcon.fill(QColor(*theColours))
            self._theIcons.append(QIcon(theIcon))
            self._theLabels.append(theLabel)
            self._theColours.append(theColours)
            self._theCounts.append(0)
            self._theMap[theLabel] = self._theLength
            self._theLength += 1

        return True

    def checkEntry(self, theStatus):
        """Check if a status value is valid, and returns the safe
        reference to be used internally.
        """
        if isinstance(theStatus, str):
            if self._getIndex(theStatus) is not None:
                return theStatus.strip()
        return self._theLabels[0]

    def getIcon(self, theLabel):
        """Return the icon for the given status item.
        """
        theIndex = self._getIndex(theLabel)
        if theIndex is not None:
            return self._theIcons[theIndex]
        return QIcon()

    def setNewEntries(self, newList):
        """Update the list of entries after they have been modified by
        the GUI tool.
        """
        replaceMap = {}

        if newList is not None:
            self._theLabels = []
            self._theColours = []
            self._theCounts = []
            self._theIcons = []
            self._theMap = {}
            self._theLength = 0
            self._theIndex = 0

            for nName, nR, nG, nB, oName in newList:
                self.addEntry(nName, (nR, nG, nB))
                if nName != oName and oName is not None:
                    replaceMap[oName] = nName

        return replaceMap

    def resetCounts(self):
        """Clear the counts of references to the status entries.
        """
        self._theCounts = [0]*self._theLength
        return

    def countEntry(self, theLabel):
        """Increment the counter for a given label. This should be used
        together with resetCounts in a loop over project items.
        """
        theIndex = self._getIndex(theLabel)
        if theIndex is not None:
            self._theCounts[theIndex] += 1
        return

    def packXML(self, xParent):
        """Pack the status entries into an XML object for saving to the
        main project file.
        """
        for n in range(self._theLength):
            xSub = etree.SubElement(xParent, "entry", attrib={
                "red":   str(self._theColours[n][0]),
                "green": str(self._theColours[n][1]),
                "blue":  str(self._theColours[n][2]),
            })
            xSub.text = self._theLabels[n]
        return True

    def unpackXML(self, xParent):
        """Unpack an XML tree and set the class values.
        """
        theLabels  = []
        theColours = []

        for xChild in xParent:
            theLabels.append(xChild.text)
            cR = checkInt(xChild.attrib.get("red", 0), 0, False)
            cG = checkInt(xChild.attrib.get("green", 0), 0, False)
            cB = checkInt(xChild.attrib.get("blue", 0), 0, False)
            theColours.append((cR, cG, cB))

        if len(theLabels) > 0:
            self._theLabels = []
            self._theColours = []
            self._theCounts = []
            self._theIcons = []
            self._theMap = {}
            self._theLength = 0
            self._theIndex = 0

            for n in range(len(theLabels)):
                self.addEntry(theLabels[n], theColours[n])

        return True

    ##
    #  Internal Functions
    ##

    def _getIndex(self, theLabel):
        """Look up a status entry in the object lists, and return it if
        it exists.
        """
        if theLabel is None:
            return None
        return self._theMap.get(theLabel.strip(), None)

    ##
    #  Iterator Bits
    ##

    def __getitem__(self, n):
        """Return an entry by its index.
        """
        if n >= 0 and n < self._theLength:
            return self._theLabels[n], self._theColours[n], self._theCounts[n], self._theIcons[n]
        return None, None, None, QIcon()

    def __iter__(self):
        """Initialise the iterator.
        """
        self._theIndex = 0
        return self

    def __next__(self):
        """Return the next entry for the iterator.
        """
        if self._theIndex < self._theLength:
            theLabel, theColour, theCount, theIcon = self.__getitem__(self._theIndex)
            self._theIndex += 1
            return theLabel, theColour, theCount, theIcon
        else:
            raise StopIteration

# END Class NWStatus
