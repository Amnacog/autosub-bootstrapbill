#
# The Autosub scanDisk module
#

import logging
import os
import platform
import re
import time
import unicodedata
from library.requests.packages.chardet import detect
from collections import deque

# Autosub specific modules
import autosub
import autosub.Helpers as Helpers
from autosub.ProcessFilename import ProcessFilename
# Settings
log = logging.getLogger('thelogger')

def decodeName(name):
    if type(name) == str: # leave unicode ones alone
        try:
            name = name.decode('utf8')
        except:
            name = name.decode('windows-1252')
    return name

def WalkError(error):
    log.error('scanDir: Error walking the folders. Message is %s' % error)

def walkDir(path):
    SkipListFR    = autosub.SKIPSTRINGFR.split(",")  if len(autosub.SKIPSTRINGFR) > 0  else []
    SkipListEN    = autosub.SKIPSTRINGEN.split(",")  if len(autosub.SKIPSTRINGEN) > 0  else []

    # Check for dutch folder skip
    if len(autosub.SKIPFOLDERSFR) == 0:
        SkipFoldersFR = []
    else:
        SkipFoldersFR = autosub.SKIPFOLDERSFR.split(",") if len(autosub.SKIPFOLDERSFR) > 0  else []
        for idx,folder in enumerate(SkipFoldersFR):
            SkipFoldersFR[idx] = os.path.normpath(os.path.join(path,folder.strip(" \/")))

    # Check for english folder skip
    if len(autosub.SKIPFOLDERSEN) == 0:
        SkipFoldersEN = []
    else:
        SkipFoldersEN = autosub.SKIPFOLDERSEN.split(",") if len(autosub.SKIPFOLDERSEN) > 0  else []
        for idx,folder in enumerate(SkipFoldersEN):
            SkipFoldersEN[idx] = os.path.normpath(os.path.join(path,folder.strip(" \/")))

    for dirname, dirnames, filenames in os.walk(path, True, WalkError):
        #filenames = [decodeName(f) for f in filenames]
        SkipThisFolderFR = False
        for skip in SkipFoldersFR:
            if dirname.startswith(skip):
                SkipThisFolderFR = True
                break
        SkipThisFolderEN = False
        for skip in SkipFoldersEN:
            if dirname.startswith(skip):
                SkipThisFolderEN = True
                break

        log.debug("scanDisk: directory name: %s" %dirname)
        if re.search('_unpack_', dirname, re.IGNORECASE):
            log.debug("scanDisk: found a unpack directory, skipping.")
            continue

        if autosub.SKIPHIDDENDIRS and os.path.split(dirname)[1].startswith(u'.'):
            continue

        if re.search('_failed_', dirname, re.IGNORECASE):
            log.debug("scanDisk: found a failed directory, skipping.")
            continue

        if re.search('@eaDir', dirname, re.IGNORECASE):
            log.debug("scanDisk: found a Synology indexing directory, skipping.")
            tmpdirs = dirnames[:]
            for dir in tmpdirs:
                dirnames.remove(dir)
            continue

        if re.search("@.*thumb", dirname, re.IGNORECASE):
            log.debug("scanDisk: found a Qnap multimedia thumbnail folder, skipping.")
            continue
        langs = []
        FileDict = {}
        for filename in filenames:
            if autosub.SEARCHSTOP:
                log.info('scanDisk: Forced Stop by user')
                return
            try:
                root,ext = os.path.splitext(filename)
                if ext[1:] in ('avi', 'mkv', 'wmv', 'ts', 'mp4'):
                    if re.search('sample', filename):
                        continue
                    if not platform.system() == 'Windows':
                        # Get best ascii compatible character for special characters
                        try:
                            if not isinstance(filename, unicode):
                                coding = detect(filename)['encoding']
                                filename = unicode(filename.decode(coding),errors='replace')
                            correctedFilename = ''.join((c for c in unicodedata.normalize('NFD', filename) if unicodedata.category(c) != 'Mn'))
                            if filename != correctedFilename:
                                os.rename(os.path.join(dirname, filename), os.path.join(dirname, correctedFilename))
                                log.info("scanDir: Renamed file %s" % correctedFilename)
                                filename = correctedFilename
                        except:
                            log.error("scanDir: Skipping directory, file %s, %s" % (dirname,filename))
                            continue
                    # What subtitle files should we expect?
                    langs = []
                    FRext = u'.' + autosub.SUBFR  + u'.srt' if autosub.SUBFR  else u'.srt'
                    ENext = u'.' + autosub.SUBENG + u'.srt' if autosub.SUBENG else u'.srt'
                    ENext = u'.en.srt'if FRext == ENext and autosub.DOWNLOADFRENCH else ENext
                    if not os.access(dirname, os.W_OK):
                        log.error('scandisk: No write access to folder: %s' % dirname)
                        continue
                    # Check which languages we want to download based on user settings.
                    log.debug('scanDir: Processing file: %s' % filename)
                    if autosub.DOWNLOADFRENCH and not SkipThisFolderFR:
                        Skipped = False
                        for SkipItem in SkipListFR:
                            if not SkipItem: break
                            if re.search(SkipItem.lower(), filename.lower()):
                                Skipped = True
                                break
                        if Skipped:
                            log.info("scanDir: %s found in %s so skipped for French subs" % (SkipItem, filename))
                        elif os.path.exists(os.path.join(dirname, root + FRext)):
                            Skipped = True
                            log.debug("scanDir: %s skipped because the French subtitle already exists" % filename) 
                        else:
                            # If the French subtitle not skipped and doesn't exist, then add it to the wanted list
                            langs.append(autosub.FRENCH)

                    if (autosub.DOWNLOADENG or (autosub.FALLBACKTOENG and autosub.DOWNLOADFRENCH and not Skipped)) and not SkipThisFolderEN:
                        Skipped = False
                        for SkipItem in SkipListEN:
                            if not SkipItem: break
                            if re.search(SkipItem.lower(), filename.lower()):
                                Skipped = True
                                break
                        if Skipped:
                            log.info("scanDir: %s found in %s so skipped for English subs" % (SkipItem, filename))
                        elif os.path.exists(os.path.join(dirname, root + ENext)):
                            log.debug("scanDir: %s skipped because the English subtitle already exists" % filename) 
                        else:
                            # If the English subtitle not skipped and doesn't exist, then add it to the wanted list
                            if not os.path.exists(os.path.join(dirname, root + ENext)):
                                langs.append(autosub.ENGLISH)
                    if not langs:
                        # nothing to do for this file
                        continue
                    FileDict = ProcessFilename(os.path.splitext(filename)[0].strip(), ext)
                    if not FileDict:
                        log.debug('scanDisk: not enough info in the filename: %s' % filename)
                        continue
                    Skip = False
                    if   autosub.MINMATCHSCORE & 8 and not FileDict['source']    : Skip = True
                    elif autosub.MINMATCHSCORE & 4 and not FileDict['quality']   : Skip = True
                    elif autosub.MINMATCHSCORE & 2 and not FileDict['codec']     : Skip = True
                    elif autosub.MINMATCHSCORE & 1 and not FileDict['releasegrp']: Skip = True
                    if Skip:
                        log.debug('scanDisk: Filespec does not meet minmatchscore so skipping this one')

                    FileDict['timestamp'] = unicode(time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(os.path.getctime(os.path.join(dirname, filename)))))
                    FileDict['langs'] = langs
                    FileDict['FRext'] = FRext
                    FileDict['ENext'] = ENext
                    FileDict['file'] = root
                    FileDict['container'] = ext
                    FileDict['folder'] = dirname
                    FileDict['ImdbId'],FileDict['A7Id'], FileDict['TvdbId'], FileDict['title'] = Helpers.getShowid(FileDict['title'])
                    if autosub.Helpers.SkipShow(FileDict['ImdbId'],FileDict['title'], FileDict['season'], FileDict['episode']):
                        log.debug("scanDir: SKIPPED %s by Skipshow rules." % FileDict['file'])
                        continue
                    log.info("scanDir: %s WANTED FOR: %s" % (langs, filename))
                    autosub.WANTEDQUEUE.append(FileDict)
                    time.sleep(0)
            except Exception as error:
                log.error('scanDir: Problem scanning file %s. Error is: %s' %(filename, error))
    return


class scanDisk():
    """
    Scan the specified path for episodes without French or (if wanted) English subtitles.
    If found add these French or English subtitles to the WANTEDQUEUE.
    """
    def run(self):
        log.info("scanDisk: Starting round of local disk checking at %s" % autosub.SERIESPATH)
        UseAddic= False
        if autosub.ADDIC7EDUSER and autosub.ADDIC7EDPASSWD and autosub.ADDIC7ED:
            try:
                # Sets autosub.DOWNLOADS_A7 and autosub.DOWNLOADS_A7MAX
                # and gives a True response if it's ok to download from a7
                autosub.ADDIC7EDAPI = autosub.Addic7ed.Addic7edAPI()
                autosub.ADDIC7EDLOGGED_IN = autosub.ADDIC7EDAPI.checkCurrentDownloads(logout=False)
            except:
                log.debug("checkSub: Couldn't connect with Addic7ed.com")
        else:
            autosub.ADDIC7EDLOGGED_IN = False
        seriespaths = [x.strip() for x in autosub.SERIESPATH.split(',')]
        for seriespath in seriespaths:

            if not os.path.exists(seriespath):
                log.error("scanDir: Root path %s does not exist, aborting..." % seriespath)
                continue

            try:
                walkDir(seriespath)
            except Exception as error:
                log.error('scanDir: Something went wrong scanning the folders. Message is: %s' % error)
                return False

        log.info("scanDir: Finished round of local disk checking")
        return True
