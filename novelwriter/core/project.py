"""
novelWriter – Project Wrapper
=============================
Data class for novelWriter projects

File History:
Created: 2018-09-29 [0.0.1]

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

import os
import json
import shutil
import logging
import novelwriter

from time import time
from lxml import etree
from functools import partial

from PyQt5.QtCore import QCoreApplication

from novelwriter.core.tree import NWTree
from novelwriter.core.item import NWItem
from novelwriter.core.index import NWIndex
from novelwriter.core.status import NWStatus
from novelwriter.core.options import OptionState
from novelwriter.core.document import NWDoc
from novelwriter.enum import nwItemType, nwItemClass, nwItemLayout, nwAlert
from novelwriter.error import logException
from novelwriter.common import (
    checkString, checkBool, checkInt, checkStringNone, isHandle, formatTimeStamp,
    makeFileNameSafe, hexToInt, minmax, simplified
)
from novelwriter.constants import trConst, nwFiles, nwLabels

logger = logging.getLogger(__name__)


class NWProject:

    FILE_VERSION = "1.4"  # The current project file format version

    def __init__(self, mainGui):

        # Internal
        self.mainConf = novelwriter.CONFIG
        self.mainGui  = mainGui

        # Core Elements
        self._optState  = OptionState(self)  # Project-specific GUI options
        self._projTree  = NWTree(self)       # The project tree
        self._projIndex = NWIndex(self)      # The projecty index
        self._langData  = {}                 # Localisation data

        # Project Status
        self.projOpened  = 0      # The time stamp of when the project file was opened
        self.projChanged = False  # The project has unsaved changes
        self.projAltered = False  # The project has been altered this session
        self.lockedBy    = None   # Data on which computer has the project open
        self.saveCount   = 0      # Meta data: number of saves
        self.autoCount   = 0      # Meta data: number of automatic saves
        self.editTime    = 0      # The accumulated edit time read from the project file

        # Class Settings
        self.projPath    = None  # The full path to where the currently open project is saved
        self.projMeta    = None  # The full path to the project's meta data folder
        self.projCache   = None  # The full path to the project's cache folder
        self.projContent = None  # The full path to the project's content folder
        self.projDict    = None  # The spell check dictionary
        self.projSpell   = None  # The spell check language, if different than default
        self.projLang    = None  # The project language, used for builds
        self.projFiles   = []    # A list of all files in the content folder on load

        # Project Meta
        self.projName    = ""  # Project name
        self.bookTitle   = ""  # The final title; should only be used for exports
        self.bookAuthors = []  # A list of book authors

        # Project Settings
        self.autoReplace = {}     # Text to auto-replace on exports
        self.titleFormat = {}     # The formatting of titles for exports
        self.spellCheck  = False  # Controls the spellcheck-as-you-type feature
        self.statusItems = None   # Novel file progress status values
        self.importItems = None   # Note file importance values
        self.lastEdited  = None   # The handle of the last file to be edited
        self.lastViewed  = None   # The handle of the last file to be viewed
        self.lastNovel   = None   # The handle of the last novel root viewed
        self.lastOutline = None   # The handle of the last outline root viewed
        self.lastWCount  = 0      # The project word count from last session
        self.lastNovelWC = 0      # The novel files word count from last session
        self.lastNotesWC = 0      # The note files word count from last session
        self.currWCount  = 0      # The project word count in current session
        self.currNovelWC = 0      # The novel files word count in cutrent session
        self.currNotesWC = 0      # The note files word count in cutrent session
        self.doBackup    = True   # Run project backup on exit

        # Internal Mapping
        self.tr = partial(QCoreApplication.translate, "NWProject")

        # Set Defaults
        self.clearProject()

        return

    ##
    #  Properties
    ##

    @property
    def index(self):
        return self._projIndex

    @property
    def tree(self):
        return self._projTree

    @property
    def options(self):
        return self._optState

    ##
    #  Item Methods
    ##

    def newRoot(self, itemClass, label=None):
        """Add a new root item. If label is None, use the class label.
        """
        if label is None:
            label = trConst(nwLabels.CLASS_NAME[itemClass])
        newItem = NWItem(self)
        newItem.setName(label)
        newItem.setType(nwItemType.ROOT)
        newItem.setClass(itemClass)
        self._projTree.append(None, None, newItem)
        self._projTree.updateItemData(newItem.itemHandle)
        return newItem.itemHandle

    def newFolder(self, label, pHandle):
        """Add a new folder with a given label and parent item.
        """
        if pHandle not in self._projTree:
            return None
        newItem = NWItem(self)
        newItem.setName(label)
        newItem.setType(nwItemType.FOLDER)
        self._projTree.append(None, pHandle, newItem)
        self._projTree.updateItemData(newItem.itemHandle)
        return newItem.itemHandle

    def newFile(self, label, pHandle):
        """Add a new file with a given label and parent item.
        """
        if pHandle not in self._projTree:
            return None
        newItem = NWItem(self)
        newItem.setName(label)
        newItem.setType(nwItemType.FILE)
        self._projTree.append(None, pHandle, newItem)
        self._projTree.updateItemData(newItem.itemHandle)
        return newItem.itemHandle

    def writeNewFile(self, tHandle, hLevel, isDocument, addText=""):
        """Write content to a new document after it is created. This
        will not run if the file exists and is not empty.
        """
        tItem = self._projTree[tHandle]
        if tItem is None:
            return False
        if not tItem.isFileType():
            return False

        newDoc = NWDoc(self, tHandle)
        if (newDoc.readDocument() or "").strip():
            return False

        hshText = "#"*minmax(hLevel, 1, 4)
        newText = f"{hshText} {tItem.itemName}\n\n{addText}"
        if tItem.isNovelLike() and isDocument:
            tItem.setLayout(nwItemLayout.DOCUMENT)
        else:
            tItem.setLayout(nwItemLayout.NOTE)

        newDoc.writeDocument(newText)
        self._projIndex.scanText(tHandle, newText)

        return True

    def removeItem(self, tHandle):
        """Remove an item from the project. This will delete both the
        project entry and a document file if it exists.
        """
        if self._projTree.checkType(tHandle, nwItemType.FILE):
            delDoc = NWDoc(self, tHandle)
            if not delDoc.deleteDocument():
                self.mainGui.makeAlert([
                    self.tr("Could not delete document file."), delDoc.getError()
                ], nwAlert.ERROR)
                return False

        self._projIndex.deleteHandle(tHandle)
        del self._projTree[tHandle]

        return True

    def trashFolder(self):
        """Add the special trash root folder to the project.
        """
        trashHandle = self._projTree.trashRoot()
        if trashHandle is None:
            newItem = NWItem(self)
            newItem.setName(trConst(nwLabels.CLASS_NAME[nwItemClass.TRASH]))
            newItem.setType(nwItemType.ROOT)
            newItem.setClass(nwItemClass.TRASH)
            self._projTree.append(None, None, newItem)
            self._projTree.updateItemData(newItem.itemHandle)
            return newItem.itemHandle

        return trashHandle

    ##
    #  Project Methods
    ##

    def clearProject(self):
        """Clear the data for the current project, and set them to
        default values.
        """
        # Project Status
        self.projOpened  = 0
        self.projChanged = False
        self.projAltered = False
        self.saveCount   = 0
        self.autoCount   = 0

        # Project Tree
        self._projTree.clear()

        # Project Settings
        self.projPath    = None
        self.projMeta    = None
        self.projCache   = None
        self.projContent = None
        self.projDict    = None
        self.projSpell   = None
        self.projLang    = None
        self.projFiles   = []
        self.projName    = ""
        self.bookTitle   = ""
        self.bookAuthors = []
        self.autoReplace = {}
        self.titleFormat = {
            "title":      "%title%",
            "chapter":    "%title%",
            "unnumbered": "%title%",
            "scene":      "* * *",
            "section":    "",
        }
        self.spellCheck  = False
        self.statusItems = NWStatus(NWStatus.STATUS)
        self.statusItems.write(None, self.tr("New"),      (100, 100, 100))
        self.statusItems.write(None, self.tr("Note"),     (200, 50,  0))
        self.statusItems.write(None, self.tr("Draft"),    (200, 150, 0))
        self.statusItems.write(None, self.tr("Finished"), (50,  200, 0))
        self.importItems = NWStatus(NWStatus.IMPORT)
        self.importItems.write(None, self.tr("New"),   (100, 100, 100))
        self.importItems.write(None, self.tr("Minor"), (200, 50,  0))
        self.importItems.write(None, self.tr("Major"), (200, 150, 0))
        self.importItems.write(None, self.tr("Main"),  (50,  200, 0))
        self.lastEdited = None
        self.lastViewed = None
        self.lastWCount = 0
        self.lastNovelWC = 0
        self.lastNotesWC = 0
        self.currWCount = 0
        self.currNovelWC = 0
        self.currNotesWC = 0

        return

    def newProject(self, projData):
        """Create a new project by populating the project tree with a
        few starter items.
        """
        if not isinstance(projData, dict):
            logger.error("Invalid call to newProject function")
            return False

        popMinimal = projData.get("popMinimal", True)
        popCustom = projData.get("popCustom", False)
        popSample = projData.get("popSample", False)

        # Check if we're extracting the sample project. This is handled
        # differently as it isn't actually a new project, so we forward
        # this to another function and return here.
        if popSample:
            return self.extractSampleProject(projData)

        # Project Settings
        projPath = projData.get("projPath", None)
        projName = projData.get("projName", self.tr("New Project"))
        projTitle = projData.get("projTitle", "")
        projAuthors = projData.get("projAuthors", "")

        if projPath is None:
            logger.error("No project path set for the new project")
            return False

        self.clearProject()
        if not self.setProjectPath(projPath, newProject=True):
            return False

        self.setProjectName(projName)
        self.setBookTitle(projTitle)
        self.setBookAuthors(projAuthors)

        hNovelRoot = self.newRoot(nwItemClass.NOVEL)
        hTitlePage = self.newFile(self.tr("Title Page"), hNovelRoot)

        titlePage = "#! %s\n\n" % (self.bookTitle if self.bookTitle else self.projName)
        if self.bookAuthors:
            titlePage = "%s>> %s %s <<\n" % (titlePage, self.tr("By"), self.getAuthors())

        aDoc = NWDoc(self, hTitlePage)
        aDoc.writeDocument(titlePage)

        if popMinimal:
            # Creating a minimal project with a few root folders and a
            # single chapter with a single scene.
            hChapter = self.newFile(self.tr("New Chapter"), hNovelRoot)
            aDoc = NWDoc(self, hChapter)
            aDoc.writeDocument("## %s\n\n" % self.tr("New Chapter"))

            hScene = self.newFile(self.tr("New Scene"), hChapter)
            aDoc = NWDoc(self, hScene)
            aDoc.writeDocument("### %s\n\n" % self.tr("New Scene"))

            self.newRoot(nwItemClass.PLOT)
            self.newRoot(nwItemClass.CHARACTER)
            self.newRoot(nwItemClass.WORLD)
            self.newRoot(nwItemClass.ARCHIVE)

        elif popCustom:
            # Create a project structure based on selected root folders
            # and a number of chapters and scenes selected in the
            # wizard's custom page.

            # Create chapters and scenes
            numChapters = projData.get("numChapters", 0)
            numScenes = projData.get("numScenes", 0)

            chSynop = self.tr("Summary of the chapter.")
            scSynop = self.tr("Summary of the scene.")

            # Create chapters
            if numChapters > 0:
                for ch in range(numChapters):
                    chTitle = self.tr("Chapter {0}").format(f"{ch+1:d}")
                    cHandle = self.newFile(chTitle, hNovelRoot)
                    aDoc = NWDoc(self, cHandle)
                    aDoc.writeDocument(f"## {chTitle}\n\n% Synopsis: {chSynop}\n\n")

                    # Create chapter scenes
                    if numScenes > 0:
                        for sc in range(numScenes):
                            scTitle = self.tr("Scene {0}").format(f"{ch+1:d}.{sc+1:d}")
                            sHandle = self.newFile(scTitle, cHandle)
                            aDoc = NWDoc(self, sHandle)
                            aDoc.writeDocument(f"### {scTitle}\n\n% Synopsis: {scSynop}\n\n")

            # Create scenes (no chapters)
            elif numScenes > 0:
                for sc in range(numScenes):
                    scTitle = self.tr("Scene {0}").format(f"{sc+1:d}")
                    sHandle = self.newFile(scTitle, hNovelRoot)
                    aDoc = NWDoc(self, sHandle)
                    aDoc.writeDocument(f"### {scTitle}\n\n% Synopsis: {scSynop}\n\n")

            # Create notes folders
            noteTitles = {
                nwItemClass.PLOT: self.tr("Main Plot"),
                nwItemClass.CHARACTER: self.tr("Protagonist"),
                nwItemClass.WORLD: self.tr("Main Location"),
            }

            addNotes = projData.get("addNotes", False)
            for newRoot in projData.get("addRoots", []):
                if newRoot in nwItemClass:
                    rHandle = self.newRoot(newRoot)
                    if addNotes:
                        aHandle = self.newFile(noteTitles[newRoot], rHandle)
                        ntTag = simplified(noteTitles[newRoot]).replace(" ", "")
                        aDoc = NWDoc(self, aHandle)
                        aDoc.writeDocument(f"# {noteTitles[newRoot]}\n\n@tag: {ntTag}\n\n")

            # Also add the archive and trash folders
            self.newRoot(nwItemClass.ARCHIVE)
            self.trashFolder()

        # Finalise
        if popCustom or popMinimal:
            self.projOpened = time()
            self.setProjectChanged(True)
            self.saveProject(autoSave=True)

        return True

    def openProject(self, fileName, overrideLock=False):
        """Open the project file provided. If it doesn't exist, assume
        it is a folder and look for the file within it. If successful,
        parse the XML of the file and populate the project variables and
        build the tree of project items.
        """
        if not os.path.isfile(fileName):
            fileName = os.path.join(fileName, nwFiles.PROJ_FILE)
            if not os.path.isfile(fileName):
                self.mainGui.makeAlert(self.tr(
                    "File not found: {0}"
                ).format(fileName), nwAlert.ERROR)
                return False

        self.clearProject()
        self.projPath = os.path.abspath(os.path.dirname(fileName))
        logger.info("Opening project: %s", self.projPath)

        # Standard Folders and Files
        # ==========================

        if not self.ensureFolderStructure():
            self.clearProject()
            return False

        self.projDict = os.path.join(self.projMeta, nwFiles.PROJ_DICT)

        # Check for Old Legacy Data
        # =========================

        legacyList = []  # Cleanup is done later
        for projItem in os.listdir(self.projPath):
            logger.debug("Project contains: %s", projItem)
            if projItem.startswith("data_") and len(projItem) == 6:
                legacyList.append(projItem)

        # Project Lock
        # ============

        if overrideLock:
            self._clearLockFile()

        lockStatus = self._readLockFile()
        if len(lockStatus) > 0:
            if lockStatus[0] == "ERROR":
                logger.warning("Failed to check lock file")
            else:
                logger.error("Project is locked, so not opening")
                self.lockedBy = lockStatus
                self.clearProject()
                return False
        else:
            logger.debug("Project is not locked")

        # Open The Project XML File
        # =========================

        try:
            nwXML = etree.parse(fileName)
        except Exception as exc:
            self.mainGui.makeAlert(self.tr(
                "Failed to parse project xml."
            ), nwAlert.ERROR, exception=exc)

            # Trying to open backup file instead
            backFile = fileName[:-3]+"bak"
            if os.path.isfile(backFile):
                self.mainGui.makeAlert(self.tr(
                    "Attempting to open backup project file instead."
                ), nwAlert.INFO)
                try:
                    nwXML = etree.parse(backFile)
                except Exception as exc:
                    self.mainGui.makeAlert(self.tr(
                        "Failed to parse project xml."
                    ), nwAlert.ERROR, exception=exc)
                    self.clearProject()
                    return False
            else:
                self.clearProject()
                return False

        xRoot = nwXML.getroot()
        nwxRoot = xRoot.tag

        appVersion  = xRoot.attrib.get("appVersion", self.tr("Unknown"))
        hexVersion  = xRoot.attrib.get("hexVersion", "0x0")
        fileVersion = xRoot.attrib.get("fileVersion", self.tr("Unknown"))

        logger.debug("XML root is '%s'", nwxRoot)
        logger.debug("File version is '%s'", fileVersion)

        # Check File Type
        # ===============

        if nwxRoot != "novelWriterXML":
            self.mainGui.makeAlert(self.tr(
                "Project file does not appear to be a novelWriterXML file."
            ), nwAlert.ERROR)
            self.clearProject()
            return False

        # Check Project Storage Version
        # =============================

        # Changes:
        # 1.0 : Original file format.
        # 1.1 : Changes the way documents are structured in the project
        #       folder from data_X, where X is the first hex value of
        #       the handle, to a single content folder.
        # 1.2 : Changes the way autoReplace entries are stored. The 1.1
        #       parser will lose the autoReplace settings if allowed to
        #       read the file. Introduced in version 0.10.
        # 1.3 : Reduces the number of layouts to only two. One for novel
        #       documents and one for project notes. Introduced in
        #       version 1.5.
        # 1.4 : Introduces a more compact format for storing items. All
        #       settings aside from name are now attributes. This format
        #       also changes the way satus and importance labels are
        #       stored and handled. Introduced in version 1.7.

        if fileVersion not in ("1.0", "1.1", "1.2", "1.3", "1.4"):
            self.mainGui.makeAlert(self.tr(
                "Unknown or unsupported novelWriter project file format. "
                "The project cannot be opened by this version of novelWriter. "
                "The file was saved with novelWriter version {0}."
            ).format(appVersion), nwAlert.ERROR)
            self.clearProject()
            return False

        if fileVersion != self.FILE_VERSION:
            msgYes = self.mainGui.askQuestion(
                self.tr("File Version"),
                self.tr(
                    "The file format of your project is about to be updated. "
                    "If you proceed, older versions of novelWriter will no "
                    "longer be able to open this project. Continue?"
                )
            )
            if not msgYes:
                self.clearProject()
                return False

        # Check novelWriter Version
        # =========================

        if hexToInt(hexVersion) > hexToInt(novelwriter.__hexversion__):
            msgYes = self.mainGui.askQuestion(
                self.tr("Version Conflict"),
                self.tr(
                    "This project was saved by a newer version of "
                    "novelWriter, version {0}. This is version {1}. If you "
                    "continue to open the project, some attributes and "
                    "settings may not be preserved, but the overall project "
                    "should be fine. Continue opening the project?"
                ).format(appVersion, novelwriter.__version__)
            )
            if not msgYes:
                self.clearProject()
                return False

        # Start Parsing the XML
        # =====================

        for xChild in xRoot:
            if xChild.tag == "project":
                logger.debug("Found project meta")
                for xItem in xChild:
                    if xItem.text is None:
                        continue
                    if xItem.tag == "name":
                        self.projName = simplified(checkString(xItem.text, ""))
                        logger.info("Project Name: '%s'", self.projName)
                    elif xItem.tag == "title":
                        self.bookTitle = simplified(checkString(xItem.text, ""))
                        logger.info("Project Title: '%s'", self.bookTitle)
                    elif xItem.tag == "author":
                        author = simplified(checkString(xItem.text, ""))
                        if author:
                            self.bookAuthors.append(author)
                            logger.debug("Author: '%s'", author)
                    elif xItem.tag == "saveCount":
                        self.saveCount = checkInt(xItem.text, 0)
                    elif xItem.tag == "autoCount":
                        self.autoCount = checkInt(xItem.text, 0)
                    elif xItem.tag == "editTime":
                        self.editTime = checkInt(xItem.text, 0)

            elif xChild.tag == "settings":
                logger.debug("Found project settings")
                for xItem in xChild:
                    if xItem.text is None:
                        continue
                    if xItem.tag == "doBackup":
                        self.doBackup = checkBool(xItem.text, False)
                    elif xItem.tag == "language":
                        self.projLang = checkStringNone(xItem.text, None)
                    elif xItem.tag == "spellCheck":
                        self.spellCheck = checkBool(xItem.text, False)
                    elif xItem.tag == "spellLang":
                        self.projSpell = checkStringNone(xItem.text, None)
                    elif xItem.tag == "lastEdited":
                        self.lastEdited = checkStringNone(xItem.text, None)
                    elif xItem.tag == "lastViewed":
                        self.lastViewed = checkStringNone(xItem.text, None)
                    elif xItem.tag == "lastNovel":
                        self.lastNovel = checkStringNone(xItem.text, None)
                    elif xItem.tag == "lastOutline":
                        self.lastOutline = checkStringNone(xItem.text, None)
                    elif xItem.tag == "lastWordCount":
                        self.lastWCount = checkInt(xItem.text, 0)
                    elif xItem.tag == "novelWordCount":
                        self.lastNovelWC = checkInt(xItem.text, 0)
                    elif xItem.tag == "notesWordCount":
                        self.lastNotesWC = checkInt(xItem.text, 0)
                    elif xItem.tag == "status":
                        self.statusItems.unpackXML(xItem)
                    elif xItem.tag == "importance":
                        self.importItems.unpackXML(xItem)
                    elif xItem.tag == "autoReplace":
                        for xEntry in xItem:
                            if xEntry.tag == "entry" and "key" in xEntry.attrib:
                                self.autoReplace[xEntry.attrib["key"]] = checkString(
                                    xEntry.text, "ERROR"
                                )
                    elif xItem.tag == "titleFormat":
                        titleFormat = self.titleFormat.copy()
                        for xEntry in xItem:
                            titleFormat[xEntry.tag] = checkString(xEntry.text, "")
                        self.setTitleFormat(titleFormat)

            elif xChild.tag == "content":
                logger.debug("Found project content")
                self._projTree.unpackXML(xChild)

        self._optState.loadSettings()

        # Sort out old file locations
        if legacyList:
            try:
                for projItem in legacyList:
                    self._legacyDataFolder(projItem)
            except Exception:
                self.mainGui.makeAlert(self.tr(
                    "There was an error updating the project. "
                    "Some data may not have been preserved."
                ), nwAlert.ERROR)

        # Clean up no longer used files
        self._deprecatedFiles()

        # Update recent projects
        self.mainConf.updateRecentCache(self.projPath, self.projName, self.lastWCount, time())
        self.mainConf.saveRecentCache()

        # Check the project tree consistency
        for tItem in self._projTree:
            tHandle = tItem.itemHandle
            logger.debug("Checking item '%s'", tHandle)
            if not self._projTree.updateItemData(tHandle):
                logger.error("There was a problem item '%s', and it has been removed", tHandle)
                del self._projTree[tHandle]  # The file will be re-added as orphaned

        self._scanProjectFolder()
        self._loadProjectLocalisation()
        self.updateWordCounts()

        self.projOpened = time()
        self.projAltered = False

        self._writeLockFile()
        self.setProjectChanged(False)
        self.mainGui.setStatus(self.tr("Opened Project: {0}").format(self.projName))

        return True

    def saveProject(self, autoSave=False):
        """Save the project main XML file. The saving command itself
        uses a temporary filename, and the file is replaced afterwards
        to make sure if the save fails, we're not left with a truncated
        file.
        """
        if self.projPath is None:
            self.mainGui.makeAlert(self.tr(
                "Project path not set, cannot save project."
            ), nwAlert.ERROR)
            return False

        saveTime = time()
        if not self.ensureFolderStructure():
            return False

        logger.info("Saving project: %s", self.projPath)

        if autoSave:
            self.autoCount += 1
        else:
            self.saveCount += 1

        # Root element and project details
        logger.debug("Writing project meta")
        nwXML = etree.Element("novelWriterXML", attrib={
            "appVersion":  str(novelwriter.__version__),
            "hexVersion":  str(novelwriter.__hexversion__),
            "fileVersion": self.FILE_VERSION,
            "timeStamp":   formatTimeStamp(saveTime),
        })

        self.updateWordCounts()
        editTime = int(self.editTime + saveTime - self.projOpened)

        # Save Project Meta
        xProject = etree.SubElement(nwXML, "project")
        self._packProjectValue(xProject, "name", self.projName)
        self._packProjectValue(xProject, "title", self.bookTitle)
        self._packProjectValue(xProject, "author", self.bookAuthors)
        self._packProjectValue(xProject, "saveCount", str(self.saveCount))
        self._packProjectValue(xProject, "autoCount", str(self.autoCount))
        self._packProjectValue(xProject, "editTime", str(editTime))

        # Save Project Settings
        xSettings = etree.SubElement(nwXML, "settings")
        self._packProjectValue(xSettings, "doBackup", self.doBackup)
        self._packProjectValue(xSettings, "language", self.projLang)
        self._packProjectValue(xSettings, "spellCheck", self.spellCheck)
        self._packProjectValue(xSettings, "spellLang", self.projSpell)
        self._packProjectValue(xSettings, "lastEdited", self.lastEdited)
        self._packProjectValue(xSettings, "lastViewed", self.lastViewed)
        self._packProjectValue(xSettings, "lastNovel", self.lastNovel)
        self._packProjectValue(xSettings, "lastOutline", self.lastOutline)
        self._packProjectValue(xSettings, "lastWordCount", self.currWCount)
        self._packProjectValue(xSettings, "novelWordCount", self.currNovelWC)
        self._packProjectValue(xSettings, "notesWordCount", self.currNotesWC)
        self._packProjectKeyValue(xSettings, "autoReplace", self.autoReplace)

        xTitleFmt = etree.SubElement(xSettings, "titleFormat")
        for aKey, aValue in self.titleFormat.items():
            if len(aKey) > 0:
                self._packProjectValue(xTitleFmt, aKey, aValue)

        # Save Status/Importance
        self.countStatus()
        xStatus = etree.SubElement(xSettings, "status")
        self.statusItems.packXML(xStatus)
        xStatus = etree.SubElement(xSettings, "importance")
        self.importItems.packXML(xStatus)

        # Save Tree Content
        logger.debug("Writing project content")
        self._projTree.packXML(nwXML)

        # Write the xml tree to file
        tempFile = os.path.join(self.projPath, nwFiles.PROJ_FILE+"~")
        saveFile = os.path.join(self.projPath, nwFiles.PROJ_FILE)
        backFile = os.path.join(self.projPath, nwFiles.PROJ_FILE[:-3]+"bak")
        try:
            with open(tempFile, mode="wb") as outFile:
                outFile.write(etree.tostring(
                    nwXML,
                    pretty_print=True,
                    encoding="utf-8",
                    xml_declaration=True
                ))
        except Exception as exc:
            self.mainGui.makeAlert(self.tr(
                "Failed to save project."
            ), nwAlert.ERROR, exception=exc)
            return False

        # If we're here, the file was successfully saved,
        # so let's sort out the temps and backups
        try:
            if os.path.isfile(saveFile):
                os.replace(saveFile, backFile)
            os.replace(tempFile, saveFile)
        except OSError as exc:
            self.mainGui.makeAlert(self.tr(
                "Failed to save project."
            ), nwAlert.ERROR, exception=exc)
            return False

        # Save project GUI options
        self._optState.saveSettings()

        # Update recent projects
        self.mainConf.updateRecentCache(self.projPath, self.projName, self.currWCount, saveTime)
        self.mainConf.saveRecentCache()

        self._writeLockFile()
        self.mainGui.setStatus(self.tr("Saved Project: {0}").format(self.projName))
        self.setProjectChanged(False)

        return True

    def closeProject(self, idleTime=0):
        """Close the current project and clear all meta data.
        """
        logger.info("Closing project: %s", self.projPath)
        self._optState.saveSettings()
        self._projTree.writeToCFile()
        self._appendSessionStats(idleTime)
        self._clearLockFile()
        self.clearProject()
        self.lockedBy = None
        return True

    def ensureFolderStructure(self):
        """Ensure that all necessary folders exist in the project
        folder.
        """
        if self.projPath is None or self.projPath == "":
            return False

        self.projMeta    = os.path.join(self.projPath, "meta")
        self.projCache   = os.path.join(self.projPath, "cache")
        self.projContent = os.path.join(self.projPath, "content")

        if self.projPath == os.path.expanduser("~"):
            # Don't make a mess in the user's home folder
            return False

        if not self._checkFolder(self.projMeta):
            return False
        if not self._checkFolder(self.projCache):
            return False
        if not self._checkFolder(self.projContent):
            return False

        return True

    ##
    #  Zip/Unzip Project
    ##

    def zipIt(self, doNotify):
        """Create a zip file of the entire project.
        """
        if not self.mainGui.hasProject:
            logger.error("No project open")
            return False

        logger.info("Backing up project")
        self.mainGui.setStatus(self.tr("Backing up project ..."))

        if not (self.mainConf.backupPath and os.path.isdir(self.mainConf.backupPath)):
            self.mainGui.makeAlert(self.tr(
                "Cannot backup project because no valid backup path is set. "
                "Please set a valid backup location in Preferences."
            ), nwAlert.ERROR)
            return False

        if not self.projName:
            self.mainGui.makeAlert(self.tr(
                "Cannot backup project because no project name is set. "
                "Please set a Working Title in Project Settings."
            ), nwAlert.ERROR)
            return False

        cleanName = makeFileNameSafe(self.projName)
        baseDir = os.path.abspath(os.path.join(self.mainConf.backupPath, cleanName))
        if not os.path.isdir(baseDir):
            try:
                os.mkdir(baseDir)
                logger.debug("Created folder: %s", baseDir)
            except Exception as exc:
                self.mainGui.makeAlert(self.tr(
                    "Could not create backup folder."
                ), nwAlert.ERROR, exception=exc)
                return False

        if baseDir and baseDir.startswith(self.projPath):
            self.mainGui.makeAlert(self.tr(
                "Cannot backup project because the backup path is within the "
                "project folder to be backed up. Please choose a different "
                "backup path in Preferences."
            ), nwAlert.ERROR)
            return False

        archName = self.tr("Backup from {0}").format(formatTimeStamp(time(), fileSafe=True))
        baseName = os.path.join(baseDir, archName)

        try:
            self._clearLockFile()
            shutil.make_archive(baseName, "zip", self.projPath, ".")
            self._writeLockFile()
            logger.info("Backup written to: %s", archName)
            if doNotify:
                self.mainGui.makeAlert(self.tr(
                    "Backup archive file written to: {0}"
                ).format(f"{os.path.join(cleanName, archName)}.zip"), nwAlert.INFO)

        except Exception as exc:
            self.mainGui.makeAlert(self.tr(
                "Could not write backup archive."
            ), nwAlert.ERROR, exception=exc)
            return False

        self.mainGui.setStatus(self.tr(
            "Project backed up to '{0}'"
        ).format(f"{baseName}.zip"))

        return True

    def extractSampleProject(self, projData):
        """Make a copy of the sample project.
        First, look for the sample.zip file in the assets folder and
        unpack it. If it doesn't exist, try to copy the content of the
        sample folder to the new project path. If neither exits, error.
        """
        projPath = projData.get("projPath", None)
        if projPath is None:
            logger.error("No project path set for the example project")
            return False

        srcSample = os.path.abspath(os.path.join(self.mainConf.appRoot, "sample"))
        pkgSample = os.path.join(self.mainConf.assetPath, "sample.zip")

        isSuccess = False
        if os.path.isfile(pkgSample):

            self.setProjectPath(projPath, newProject=True)
            try:
                shutil.unpack_archive(pkgSample, projPath)
                isSuccess = True
            except Exception as exc:
                self.mainGui.makeAlert(self.tr(
                    "Failed to create a new example project."
                ), nwAlert.ERROR, exception=exc)

        elif os.path.isdir(srcSample):

            self.setProjectPath(projPath, newProject=True)
            try:
                srcProj = os.path.join(srcSample, nwFiles.PROJ_FILE)
                dstProj = os.path.join(projPath, nwFiles.PROJ_FILE)
                shutil.copyfile(srcProj, dstProj)

                srcContent = os.path.join(srcSample, "content")
                dstContent = os.path.join(projPath, "content")
                for srcFile in os.listdir(srcContent):
                    srcDoc = os.path.join(srcContent, srcFile)
                    dstDoc = os.path.join(dstContent, srcFile)
                    shutil.copyfile(srcDoc, dstDoc)

                isSuccess = True

            except Exception as exc:
                self.mainGui.makeAlert(self.tr(
                    "Failed to create a new example project."
                ), nwAlert.ERROR, exception=exc)

        else:
            self.mainGui.makeAlert(self.tr(
                "Failed to create a new example project. "
                "Could not find the necessary files. "
                "They seem to be missing from this installation."
            ), nwAlert.ERROR)

        if isSuccess:
            self.clearProject()
            self.mainGui.openProject(projPath)
            self.mainGui.rebuildIndex()

        return isSuccess

    ##
    #  Setters
    ##

    def setProjectPath(self, projPath, newProject=False):
        """Set the project storage path, and also expand ~ to the user
        directory using the path library.
        """
        if projPath is None or projPath == "":
            self.projPath = None
        else:
            if projPath.startswith("~"):
                projPath = os.path.expanduser(projPath)
            self.projPath = os.path.abspath(projPath)

        if newProject:
            if not os.path.isdir(projPath):
                try:
                    os.mkdir(projPath)
                    logger.debug("Created folder: %s", projPath)
                except Exception as exc:
                    self.mainGui.makeAlert(self.tr(
                        "Could not create new project folder."
                    ), nwAlert.ERROR, exception=exc)
                    return False

            if os.path.isdir(projPath):
                if os.listdir(self.projPath):
                    self.mainGui.makeAlert(self.tr(
                        "New project folder is not empty. "
                        "Each project requires a dedicated project folder."
                    ), nwAlert.ERROR)
                    return False

        self.ensureFolderStructure()
        self.setProjectChanged(True)

        return True

    def setProjectName(self, projName):
        """Set the project name, This is the the name used for backup
        files etc.
        """
        self.projName = simplified(projName)
        self.setProjectChanged(True)
        return True

    def setBookTitle(self, bookTitle):
        """Set the book title, that is, the title to include in exports.
        """
        self.bookTitle = simplified(bookTitle)
        self.setProjectChanged(True)
        return True

    def setBookAuthors(self, bookAuthors):
        """A line-separated list of authors, parsed into an array.
        """
        if not isinstance(bookAuthors, str):
            return False

        self.bookAuthors = []
        for bookAuthor in bookAuthors.splitlines():
            bookAuthor = simplified(bookAuthor)
            if bookAuthor == "":
                continue
            self.bookAuthors.append(bookAuthor)

        self.setProjectChanged(True)

        return True

    def setProjBackup(self, doBackup):
        """Set whether projects should be backed up or not. The user
        will be notified in case required settings are missing.
        """
        self.doBackup = doBackup
        if doBackup:
            if not os.path.isdir(self.mainConf.backupPath):
                self.mainGui.makeAlert(self.tr(
                    "You must set a valid backup path in Preferences to use "
                    "the automatic project backup feature."
                ), nwAlert.WARN)
                return False

            if self.projName == "":
                self.mainGui.makeAlert(self.tr(
                    "You must set a valid project name in Project Settings to "
                    "use the automatic project backup feature."
                ), nwAlert.WARN)
                return False

        return True

    def setSpellCheck(self, theMode):
        """Enable/disable spell checking.
        """
        if self.spellCheck != theMode:
            self.spellCheck = theMode
            self.setProjectChanged(True)
        return self.spellCheck

    def setSpellLang(self, theLang):
        """Set the project-specific spell check language.
        """
        theLang = checkStringNone(theLang, None)
        if self.projSpell != theLang:
            self.projSpell = theLang
            self.setProjectChanged(True)
            return True
        return False

    def setProjectLang(self, theLang):
        """Set the project-specific language.
        """
        theLang = checkStringNone(theLang, None)
        if self.projLang != theLang:
            self.projLang = theLang
            self._loadProjectLocalisation()
            self.setProjectChanged(True)
        return True

    def setTreeOrder(self, newOrder):
        """A list representing the linear/flattened order of project
        items in the GUI project tree. The user can rearrange the order
        by drag-and-drop. Forwarded to the NWTree class.
        """
        if len(self._projTree) != len(newOrder):
            logger.warning("Sizes of new and old tree order do not match")
        self._projTree.setOrder(newOrder)
        self.setProjectChanged(True)
        return True

    def setLastEdited(self, tHandle):
        """Set last edited project item.
        """
        if self.lastEdited != tHandle:
            self.lastEdited = tHandle
            self.setProjectChanged(True)
        return True

    def setLastViewed(self, tHandle):
        """Set last viewed project item.
        """
        if self.lastViewed != tHandle:
            self.lastViewed = tHandle
            self.setProjectChanged(True)
        return True

    def setLastNovelViewed(self, tHandle):
        """Set last viewed novel root in the novel tree.
        """
        if self.lastNovel != tHandle:
            self.lastNovel = tHandle
            self.setProjectChanged(True)
        return True

    def setLastOutlineViewed(self, tHandle):
        """Set last viewed novel root in the outline view.
        """
        if self.lastOutline != tHandle:
            self.lastOutline = tHandle
            self.setProjectChanged(True)
        return True

    def setStatusColours(self, newCols, delCols):
        """Update the list of novel file status flags.
        """
        return self._setStatusImport(newCols, delCols, self.statusItems)

    def setImportColours(self, newCols, delCols):
        """Update the list of note file importance flags.
        """
        return self._setStatusImport(newCols, delCols, self.importItems)

    def setAutoReplace(self, autoReplace):
        """Update the auto-replace dictionary.
        """
        self.autoReplace = {}
        for key, entry in autoReplace.items():
            self.autoReplace[key] = simplified(entry)
        self.setProjectChanged(True)
        return True

    def setTitleFormat(self, titleFormat):
        """Set the formatting of titles in the project.
        """
        for valKey, valEntry in titleFormat.items():
            if valKey in self.titleFormat:
                self.titleFormat[valKey] = checkString(
                    simplified(valEntry), self.titleFormat[valKey]
                )
        return True

    def setProjectChanged(self, bValue):
        """Toggle the project changed flag, and propagate the
        information to the GUI statusbar.
        """
        self.projChanged = bValue
        self.mainGui.mainStatus.doUpdateProjectStatus(bValue)
        if bValue:
            # If we've changed the project at all, this should be True
            self.projAltered = True
        return self.projChanged

    ##
    #  Getters
    ##

    def getAuthors(self):
        """Return a formatted string of authors.
        """
        nAuth = len(self.bookAuthors)
        authString = ""

        if nAuth == 1:
            authString = self.bookAuthors[0]
        elif nAuth > 1:
            authString = "%s %s %s" % (
                ", ".join(self.bookAuthors[0:-1]), self.tr("and"), self.bookAuthors[-1]
            )

        return authString

    def getCurrentEditTime(self):
        """Get the total project edit time, including the time spent in
        the current session.
        """
        return round(self.editTime + time() - self.projOpened)

    def getProjectItems(self):
        """This function ensures that the item tree loaded is sent to
        the GUI tree view in such a way that the tree can be built. That
        is, the parent item must be sent before its child. In principle,
        a proper XML file will already ensure that, but in the event the
        order has been altered, or a file is orphaned, this function is
        capable of handling it.
        """
        sentItems = []
        iterItems = self._projTree.handles()
        n = 0
        nMax = min(len(iterItems), 10000)
        while n < nMax:
            tHandle = iterItems[n]
            tItem = self._projTree[tHandle]
            n += 1
            if tItem is None:
                # Technically a bug since treeOrder is built from the
                # same data as _projTree
                continue
            elif tItem.itemParent is None:
                # Item is a root, or already been identified as an
                # orphaned item
                sentItems.append(tHandle)
                yield tItem
            elif tItem.itemParent in sentItems:
                # Item's parent has been sent, so all is fine
                sentItems.append(tHandle)
                yield tItem
            elif tItem.itemParent in iterItems:
                # Item's parent exists, but hasn't been sent yet, so add
                # it again to the end, but make sure this doesn't get
                # out hand, so we cap at 10000 items
                logger.warning("Item '%s' found before its parent", tHandle)
                iterItems.append(tHandle)
                nMax = min(len(iterItems), 10000)
            else:
                # Item is orphaned
                logger.error("Item '%s' has no parent in current tree", tHandle)
                tItem.setParent(None)
                yield tItem

    ##
    #  Class Methods
    ##

    def updateWordCounts(self):
        """Update the total word count values.
        """
        wcNovel, wcNotes = self._projTree.sumWords()
        wcTotal = wcNovel + wcNotes
        if wcTotal != self.currWCount:
            self.currNovelWC = wcNovel
            self.currNotesWC = wcNotes
            self.currWCount  = wcTotal
            self.setProjectChanged(True)
        return

    def countStatus(self):
        """Count how many times the various status flags are used in the
        project tree. The counts themselves are kept in the NWStatus
        objects. This is essentially a refresh.
        """
        self.statusItems.resetCounts()
        self.importItems.resetCounts()
        for nwItem in self._projTree:
            if nwItem.isNovelLike():
                self.statusItems.increment(nwItem.itemStatus)
            else:
                self.importItems.increment(nwItem.itemImport)
        return

    def localLookup(self, theWord):
        """Look up a word in the translation map for the project and
        return it. The variable is cast to a string before lookup. If
        the word does not exist, it returns itself.
        """
        return self._langData.get(str(theWord), str(theWord))

    ##
    #  Internal Functions
    ##

    def _setStatusImport(self, new, delete, target):
        """Update the list of novel file status or importance flags, and
        delete those that have been requested deleted.
        """
        if not (new or delete):
            return False

        order = []
        for entry in new:
            key = entry.get("key", None)
            name = entry.get("name", "")
            cols = entry.get("cols", (100, 100, 100))
            if name:
                order.append(target.write(key, name, cols))

        for key in delete:
            target.remove(key)

        target.reorder(order)

        return True

    def _loadProjectLocalisation(self):
        """Load the language data for the current project language.
        """
        if self.projLang is None:
            self._langData = {}
            return False

        langFile = os.path.join(self.mainConf.nwLangPath, "project_%s.json" % self.projLang)
        if not os.path.isfile(langFile):
            langFile = os.path.join(self.mainConf.nwLangPath, "project_en_GB.json")

        try:
            with open(langFile, mode="r", encoding="utf-8") as inFile:
                self._langData = json.load(inFile)
            logger.debug("Loaded project language file: %s", os.path.basename(langFile))

        except Exception:
            logger.error("Failed to project language file")
            logException()
            return False

        return True

    def _readLockFile(self):
        """Reads the lock file in the project folder.
        """
        if self.projPath is None:
            return ["ERROR"]

        lockFile = os.path.join(self.projPath, nwFiles.PROJ_LOCK)
        if not os.path.isfile(lockFile):
            return []

        theLines = []
        try:
            with open(lockFile, mode="r", encoding="utf-8") as inFile:
                theData = inFile.read()
                theLines = theData.splitlines()
                if len(theLines) != 4:
                    return ["ERROR"]

        except Exception:
            logger.error("Failed to read project lockfile")
            logException()
            return ["ERROR"]

        return theLines

    def _writeLockFile(self):
        """Writes a lock file to the project folder.
        """
        if self.projPath is None:
            return False

        lockFile = os.path.join(self.projPath, nwFiles.PROJ_LOCK)
        try:
            with open(lockFile, mode="w+", encoding="utf-8") as outFile:
                outFile.write("%s\n" % self.mainConf.hostName)
                outFile.write("%s\n" % self.mainConf.osType)
                outFile.write("%s\n" % self.mainConf.kernelVer)
                outFile.write("%d\n" % time())

        except Exception:
            logger.error("Failed to write project lockfile")
            logException()
            return False

        return True

    def _clearLockFile(self):
        """Remove the lock file, if it exists.
        """
        if self.projPath is None:
            return False

        lockFile = os.path.join(self.projPath, nwFiles.PROJ_LOCK)
        if os.path.isfile(lockFile):
            try:
                os.unlink(lockFile)
            except Exception:
                logger.error("Failed to remove project lockfile")
                logException()
                return False

        return True

    def _checkFolder(self, thePath):
        """Check if a folder exists, and if it doesn't, create it.
        """
        if not os.path.isdir(thePath):
            try:
                os.mkdir(thePath)
                logger.debug("Created folder: %s", thePath)
            except Exception as exc:
                self.mainGui.makeAlert(self.tr(
                    "Could not create folder."
                ), nwAlert.ERROR, exception=exc)
                return False
        return True

    def _packProjectValue(self, xParent, theName, theValue, allowNone=True):
        """Pack a list of values into an xml element.
        """
        if not isinstance(theValue, list):
            theValue = [theValue]
        for aValue in theValue:
            if (aValue == "" or aValue is None) and not allowNone:
                continue
            xItem = etree.SubElement(xParent, theName)
            xItem.text = str(aValue)
        return

    def _packProjectKeyValue(self, xParent, theName, theDict):
        """Pack the entries of a dictionary into an xml element.
        """
        xAutoRep = etree.SubElement(xParent, theName)
        for aKey, aValue in theDict.items():
            if len(aKey) > 0:
                xEntry = etree.SubElement(xAutoRep, "entry", attrib={"key": aKey})
                xEntry.text = aValue
        return

    def _scanProjectFolder(self):
        """Scan the project folder and check that the files in it are
        also in the project XML file. If they aren't, import them as
        orphaned files so the user can either delete them, or put them
        back into the project tree.
        """
        if self.projPath is None:
            return False

        # Then check the files in the data folder
        logger.debug("Checking files in project content folder")
        orphanFiles = []
        self.projFiles = []
        for fileItem in os.listdir(self.projContent):
            if not fileItem.endswith(".nwd"):
                logger.warning("Skipping file: %s", fileItem)
                continue
            if len(fileItem) != 17:
                logger.warning("Skipping file: %s", fileItem)
                continue

            fHandle = fileItem[:13]
            if not isHandle(fHandle):
                logger.warning("Skipping file: %s", fileItem)
                continue

            if fHandle in self._projTree:
                self.projFiles.append(fHandle)
                logger.debug("Checking file %s, handle '%s': OK", fileItem, fHandle)
            else:
                logger.warning("Checking file %s, handle '%s': Orphaned", fileItem, fHandle)
                orphanFiles.append(fHandle)

        # Report status
        if len(orphanFiles) > 0:
            self.mainGui.makeAlert(self.tr(
                "Found {0} orphaned file(s) in project folder."
            ).format(len(orphanFiles)), nwAlert.WARN)
        else:
            logger.debug("File check OK")
            return

        # Handle orphans
        nOrph = 0
        noWhere = False
        oPrefix = self.tr("Recovered")
        for oHandle in orphanFiles:

            # Look for meta data
            oName = ""
            oParent = None
            oClass = None
            oLayout = None

            aDoc = NWDoc(self, oHandle)
            if aDoc.readDocument(isOrphan=True) is not None:
                oName, oParent, oClass, oLayout = aDoc.getMeta()

            if oName:
                oName = self.tr("[{0}] {1}").format(
                    oPrefix, oName.replace("[%s]" % oPrefix, "").strip()
                )
            else:
                nOrph += 1
                oName = self.tr("Recovered File {0}").format(nOrph)

            # Recover file meta data
            if oClass is None:
                oClass = nwItemClass.NOVEL

            if oLayout is None:
                oLayout = nwItemLayout.NOTE

            if oParent is None or oParent not in self._projTree:
                oParent = self._projTree.findRoot(oClass)
                if oParent is None:
                    oParent = self._projTree.findRoot(nwItemClass.NOVEL)

            # If the file still has no parent item, skip it
            if oParent is None:
                noWhere = True
                continue

            orphItem = NWItem(self)
            orphItem.setName(oName)
            orphItem.setType(nwItemType.FILE)
            orphItem.setClass(oClass)
            orphItem.setLayout(oLayout)
            self._projTree.append(oHandle, oParent, orphItem)
            self._projTree.updateItemData(orphItem.itemHandle)

        if noWhere:
            self.mainGui.makeAlert(self.tr(
                "One or more orphaned files could not be added back into the project. "
                "Make sure at least a Novel root folder exists."
            ), nwAlert.WARN)

        return True

    def _appendSessionStats(self, idleTime):
        """Append session statistics to the sessions log file.
        """
        if not self.ensureFolderStructure():
            return False

        sessionFile = os.path.join(self.projMeta, nwFiles.SESS_STATS)
        isFile = os.path.isfile(sessionFile)

        nowTime = time()
        sessDiff = self.currWCount - self.lastWCount
        sessTime = nowTime - self.projOpened

        logger.info("The session lasted %d sec and added %d words", int(sessTime), sessDiff)
        if sessTime < 300 and sessDiff == 0:
            logger.info("Session too short, skipping log entry")
            return False

        try:
            with open(sessionFile, mode="a+", encoding="utf-8") as outFile:
                if not isFile:
                    # It's a new file, so add a header
                    if self.lastWCount > 0:
                        outFile.write("# Offset %d\n" % self.lastWCount)
                    outFile.write("# %-17s  %-19s  %8s  %8s  %8s\n" % (
                        "Start Time", "End Time", "Novel", "Notes", "Idle"
                    ))

                outFile.write("%-19s  %-19s  %8d  %8d  %8d\n" % (
                    formatTimeStamp(self.projOpened),
                    formatTimeStamp(nowTime),
                    self.currNovelWC,
                    self.currNotesWC,
                    int(idleTime),
                ))

        except Exception:
            logger.error("Failed to write session stats file")
            logException()
            return False

        return True

    ##
    #  Legacy Data Structure Handlers
    ##

    def _legacyDataFolder(self, dataDir):
        """Clean up legacy data folders.
        """
        dataPath = os.path.join(self.projPath, dataDir)
        if not os.path.isdir(dataPath):
            return False

        logger.info("Old data folder found: %s", dataDir)

        # Move Documents to Content
        for dataItem in os.listdir(dataPath):
            dataFile = os.path.join(dataPath, dataItem)
            if not os.path.isfile(dataFile):
                continue

            if len(dataItem) == 21 and dataItem.endswith("_main.nwd"):
                tHandle = dataDir[-1] + dataItem[:12]
                newPath = os.path.join(self.projContent, f"{tHandle}.nwd")
                os.rename(dataFile, newPath)
                logger.info("Moved file: %s", dataFile)

            elif len(dataItem) == 21 and dataItem.endswith("_main.bak"):
                os.unlink(dataFile)
                logger.info("Deleted file: %s", dataFile)

        # Remove Data Folder
        if not os.listdir(dataPath):
            os.rmdir(dataPath)
            logger.info("Deleted folder: %s", dataDir)

        return True

    def _deprecatedFiles(self):
        """Delete files that are no longer used by novelWriter.
        """
        rmList = [
            os.path.join(self.projCache, "nwProject.nwx.0"),
            os.path.join(self.projCache, "nwProject.nwx.1"),
            os.path.join(self.projCache, "nwProject.nwx.2"),
            os.path.join(self.projCache, "nwProject.nwx.3"),
            os.path.join(self.projCache, "nwProject.nwx.4"),
            os.path.join(self.projCache, "nwProject.nwx.5"),
            os.path.join(self.projCache, "nwProject.nwx.6"),
            os.path.join(self.projCache, "nwProject.nwx.7"),
            os.path.join(self.projCache, "nwProject.nwx.8"),
            os.path.join(self.projCache, "nwProject.nwx.9"),
            os.path.join(self.projMeta, "mainOptions.json"),
            os.path.join(self.projMeta, "exportOptions.json"),
            os.path.join(self.projMeta, "outlineOptions.json"),
            os.path.join(self.projMeta, "timelineOptions.json"),
            os.path.join(self.projMeta, "docMergeOptions.json"),
            os.path.join(self.projMeta, "sessionLogOptions.json"),
            os.path.join(self.projPath, "ToC.json"),
        ]

        for rmFile in rmList:
            if os.path.isfile(rmFile):
                logger.info("Deleting: %s", rmFile)
                try:
                    os.unlink(rmFile)
                except Exception:
                    logger.error("Could not delete: %s", rmFile)
                    logException()
                    return False

        return True

# END Class NWProject
