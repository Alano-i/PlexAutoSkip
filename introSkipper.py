#!/usr/bin/python3

import logging
import time
from sslAlertListener import SSLAlertListener
from mediaWrapper import MediaWrapper
from xml.etree import ElementTree


class IntroSkipper():
    media_sessions = {}
    delete = []

    def __init__(self, server, leftOffset=0, rightOffset=0, timeout=60 * 2, log=None):
        self.server = server
        self.log = log or logging.getLogger(__name__)
        self.leftOffset = leftOffset
        self.rightOffset = rightOffset
        self.timeout = timeout
        self.timeoutWithoutCheck = True

    def getDataFromSessions(self, sessionKey):
        try:
            for media in self.server.sessions():
                if media.sessionKey == sessionKey:
                    return media
        except:
            self.log.exception("getDataFromSessions Error")
        return None

    def start(self, sslopt=None):
        self.listener = SSLAlertListener(self.server, self.processAlert, self.error, sslopt=sslopt)
        try:
            self.listener.start()
        except KeyboardInterrupt:
            self.listener.stop()
        except:
            self.log.exception("Exception caught")
        while self.listener.is_alive():
            for k in self.media_sessions:
                self.checkMedia(self.media_sessions[k])
            time.sleep(1)
            for d in self.delete:
                del self.media_sessions[d]
            self.delete.clear()

    def checkMedia(self, mediaWrapper):
        if hasattr(mediaWrapper.media, 'chapters'):
            for chapter in [x for x in mediaWrapper.media.chapters if x.title.lower() == 'advertisement']:
                self.log.debug("Checking chapter %s (%d-%d)" % (chapter.title, chapter.start, chapter.end))
                if (chapter.start + self.leftOffset) <= mediaWrapper.viewOffset <= chapter.end:
                    self.log.info("Found an advertisement chapter for media %s with range %d-%d and viewOffset %d" % (mediaWrapper.media.key, chapter.start + self.leftOffset, chapter.end, mediaWrapper.viewOffset))
                    self.seekTo(mediaWrapper, chapter.end)
                    return

        if hasattr(mediaWrapper.media, 'markers'):
            for marker in [x for x in mediaWrapper.media.markers if x.type.lower() == 'intro']:
                self.log.debug("Checking marker %s (%d-%d)" % (marker.type, marker.start, marker.end))
                if (marker.start + self.leftOffset) <= mediaWrapper.viewOffset <= marker.end:
                    self.log.info("Found an intro marker for media %s with range %d-%d and viewOffset %d" % (mediaWrapper.media.key, marker.start + self.leftOffset, marker.end, mediaWrapper.viewOffset))
                    self.seekTo(mediaWrapper, marker.end)
                    return

        if mediaWrapper.sinceLastUpdate > self.timeout:
            self.log.debug("Session %d hasn't been updated in %d seconds, checking if still playing" % (mediaWrapper.media.sessionKey, self.timeout))
            try:
                if self.timeoutWithoutCheck or not self.stillPlaying(mediaWrapper):
                    self.log.debug("Session %s will be removed from cache" % (mediaWrapper.media.sessionKey))
                    self.delete.append(mediaWrapper.media.sessionKey)
            except:
                self.log.error("Error checking player status, removing session %s anyway" % (mediaWrapper.media.sessionKey))
                self.delete.append(mediaWrapper.media.sessionKey)

    def seekTo(self, mediaWrapper, targetOffset):
        for player in mediaWrapper.media.players:
            try:
                player.proxyThroughServer(True, self.server)
                if player.isPlayingMedia(False) and player.timeline.key == mediaWrapper.media.key:
                    mediaWrapper.seeking = True
                    self.log.info("Seeking player %s from %d to %d" % (player.title, mediaWrapper.viewOffset, (targetOffset + self.rightOffset)))
                    try:
                        player.seekTo(targetOffset + self.rightOffset)
                    except ElementTree.ParseError:
                        self.log.debug("ParseError, seems to be certain players but still functional, continuing")
                    mediaWrapper.updateOffset(targetOffset + self.rightOffset)
            except:
                self.log.exception("Error seeking")
        mediaWrapper.seeking = False

    def stillPlaying(self, mediaWrapper):
        for player in mediaWrapper.media.players:
            try:
                player.proxyThroughServer(True, self.server)
                if player.isPlayingMedia(False) and player.timeline.key == mediaWrapper.media.key:
                    return True
            except:
                self.log.exception("Error while checking player")
        return False

    def processAlert(self, data):
        if data['type'] == 'playing':
            sessionKey = int(data['PlaySessionStateNotification'][0]['sessionKey'])
            try:
                media = self.getDataFromSessions(sessionKey)
                if media and media.session and len(media.session) > 0 and media.session[0].location == 'lan':
                    wrapper = MediaWrapper(media)
                    if sessionKey not in self.media_sessions:
                        self.log.info("Found a new LAN session %d with viewOffset %d" % (sessionKey, media.viewOffset))
                        self.media_sessions[sessionKey] = wrapper
                    elif not self.media_sessions[sessionKey].seeking:
                        self.log.debug("Updating an existing media session %s with viewOffset %d (previous %d)" % (sessionKey, media.viewOffset, self.media_sessions[sessionKey].viewOffset))
                        self.media_sessions[sessionKey] = wrapper
                    else:
                        self.log.debug("Skipping update as session %s appears to be actively seeking" % (sessionKey))
                else:
                    pass
            except:
                self.log.exception("Unexpected error getting media data from session alert")

    def error(self, data):
        self.log.error(data)
