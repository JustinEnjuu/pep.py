from constants import actions
from constants import gameModes
from helpers import userHelper
from constants import serverPackets
from events import logoutEvent
from helpers import logHelper as log
from objects import glob
import uuid
import time
import threading

class token:
	"""Osu Token object

	token -- token string
	userID -- userID associated to that token
	username -- username relative to userID (cache)
	rank -- rank (permissions) relative to userID (cache)
	actionID -- current user action (see actions.py)
	actionText -- current user action text
	actionMd5 -- md5 relative to user action
	actionMods -- current acton mods
	gameMode -- current user game mode
	location -- [latitude,longitude]
	queue -- packets queue
	joinedChannels -- list. Contains joined channel names
	spectating -- userID of spectating user. 0 if not spectating.
	spectators -- list. Contains userIDs of spectators
	country -- osu country code. Use countryHelper to convert from letter country code to osu country code
	pingTime -- latest packet received UNIX time
	loginTime -- login UNIX time
	latestTillerino -- beatmap ID of latest song from tillerino bot
	"""


	def __init__(self, __userID, __token = None):
		"""
		Create a token object and set userID and token

		__userID -- user associated to this token
		__token -- 	if passed, set token to that value
					if not passed, token will be generated
		"""

		# Set stuff
		self.userID = __userID
		self.username = userHelper.getUsername(self.userID)
		self.rank = userHelper.getRankPrivileges(self.userID)
		self.loginTime = int(time.time())
		self.pingTime = self.loginTime
		self.lock = threading.Lock()	# <-- Sync primitive

		# Default variables
		self.spectators = []
		self.spectating = 0
		self.location = [0,0]
		self.joinedChannels = []
		self.actionID = actions.idle
		self.actionText = ""
		self.actionMd5 = ""
		self.actionMods = 0
		self.gameMode = gameModes.std
		self.country = 0
		self.location = [0,0]
		self.awayMessage = ""
		self.matchID = -1
		self.tillerino = [0,0,-1.0]	# beatmap, mods, acc
		self.silenceEndTime = 0
		self.queue = bytes()

		# Spam protection
		self.longMessageWarning = False
		self.spamRate = 0
		self.lastMessagetime = 0

		# Generate/set token
		if __token != None:
			self.token = __token
		else:
			self.token = str(uuid.uuid4())


	def enqueue(self, __bytes):
		"""
		Add bytes (packets) to queue

		__bytes -- (packet) bytes to enqueue
		"""

		self.queue += __bytes


	def resetQueue(self):
		"""Resets the queue. Call when enqueued packets have been sent"""
		self.queue = bytes()


	def joinChannel(self, __channel):
		"""Add __channel to joined channels list

		__channel -- channel name"""

		if __channel not in self.joinedChannels:
			self.joinedChannels.append(__channel)


	def partChannel(self, __channel):
		"""Remove __channel from joined channels list

		__channel -- channel name"""

		if __channel in self.joinedChannels:
			self.joinedChannels.remove(__channel)


	def setLocation(self, __location):
		"""Set location (latitude and longitude)

		__location -- [latitude, longitude]"""

		self.location = __location


	def getLatitude(self):
		"""Get latitude

		return -- latitude"""

		return self.location[0]


	def getLongitude(self):
		"""Get longitude

		return -- longitude"""
		return self.location[1]


	def startSpectating(self, __userID):
		"""Set the spectating user to __userID

		__userID -- target userID"""
		self.spectating = __userID


	def stopSpectating(self):
		"""Set the spectating user to 0, aka no user"""
		self.spectating = 0


	def addSpectator(self, __userID):
		"""Add __userID to our spectators

		userID -- new spectator userID"""

		# Add userID to spectators if not already in
		if __userID not in self.spectators:
			self.spectators.append(__userID)


	def removeSpectator(self, __userID):
		"""Remove __userID from our spectators

		userID -- old spectator userID"""

		# Remove spectator
		if __userID in self.spectators:
			self.spectators.remove(__userID)


	def setCountry(self, __countryID):
		"""Set country to __countryID

		__countryID -- numeric country ID. See countryHelper.py"""

		self.country = __countryID


	def getCountry(self):
		"""Get numeric country ID

		return -- numeric country ID. See countryHelper.py"""

		return self.country


	def updatePingTime(self):
		"""Update latest ping time"""
		self.pingTime = int(time.time())

	def setAwayMessage(self, __awayMessage):
		"""Set a new away message"""
		self.awayMessage = __awayMessage

	def joinMatch(self, __matchID):
		"""
		Set match to matchID

		__matchID -- new match ID
		"""
		self.matchID = __matchID

	def partMatch(self):
		"""Set match to -1"""
		self.matchID = -1

	def kick(self):
		"""Kick this user from the server"""
		# Send packet to target
		log.info("{} has been disconnected. (kick)".format(self.username))
		self.enqueue(serverPackets.notification("You have been kicked from the server. Please login again."))
		self.enqueue(serverPackets.loginFailed())

		# Logout event
		logoutEvent.handle(self, None)

	def silence(self, seconds, reason, author = 999):
		"""
		Silences this user (db, packet and token)

		seconds -- silence length in seconds
		reason -- silence reason
		author -- userID of who has silenced the target. Optional. Default: 999 (fokabot)
		"""
		# Silence in db and token
		self.silenceEndTime = int(time.time())+seconds
		userHelper.silence(self.userID, seconds, reason, author)

		# Send silence packet to target
		self.enqueue(serverPackets.silenceEndTime(seconds))

		# Send silenced packet to everyone else
		glob.tokens.enqueueAll(serverPackets.userSilenced(self.userID))

	def spamProtection(self, increaseSpamRate = True):
		"""
		Silences the user if is spamming.

		increaseSpamRate -- pass True if the user has sent a new message. Optional. Default: True
		"""
		if increaseSpamRate == True:
			# Reset spam rate every 10 seconds
			if int(time.time())-self.lastMessagetime >= 10:
				self.spamRate = 0
			else:
				self.spamRate += 1
			# Update last message time
			self.lastMessagetime = time.time()

		# Silence the user if needed
		if self.spamRate > 10:
			self.silence(1800, "Spamming (auto spam protection)")

	def isSilenced(self):
		"""
		Returns True if this user is silenced, otherwise False

		return -- True/False
		"""
		return self.silenceEndTime-int(time.time()) > 0

	def getSilenceSecondsLeft(self):
		"""
		Returns the seconds left for this user's silence
		(0 if user is not silenced)

		return -- silence seconds left
		"""
		return max(0, self.silenceEndTime-int(time.time()))