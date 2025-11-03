import nvwave
import globalPluginHandler
import speech
import config
import os, shutil
import glob
import wx
import addonHandler
import api
from random import randint
from globalCommands import SCRCAT_CONFIG
from ui import message
from scriptHandler import script
from gui import NVDASettingsDialog, guiHelper, mainFrame
from gui.settingsDialogs import SettingsPanel
from controlTypes import STATE_READONLY, STATE_EDITABLE
from .create import NewPack
from configobj.validate import VdtTypeError

def get_number_sound_packs():
	return [folder for folder in os.listdir(numbering_dir) if os.path.isdir(os.path.join(numbering_dir, folder))]

def confinit():
	confspec = {
		"typingsnd": "boolean(default=true)",
		"typing_sound": f"string(default={get_sounds_folders()[0]})",
		"speak_on_protected":"boolean(default=True)",
		"num_sound_mode": "integer(default=1, min=0, max=2)",
		"num_speak_on_protected": "integer(default=1, min=0, max=2)",
		"num_sound_pack": f"string(default={get_number_sound_packs()[0]})"
	}
	config.confspec["typing_sfx"] = confspec

addonHandler.initTranslation()
effects_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), "effects", "Typing")
numbering_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), "effects", "numbering")
controls = (8, 52, 82)
typingProtected = api.isTypingProtected

def get_sounds_folders():
	folders = []
	for folder in os.listdir(effects_dir):
		if os.path.isdir(os.path.join(effects_dir, folder)):
			folders.append(folder)
	return folders

def get_sounds(name):
	return [os.path.basename(sound) for sound in glob.glob(f"{effects_dir}/{name}/*.wav")]

def get_number_sounds(name):
	return [os.path.basename(sound) for sound in glob.glob(f"{numbering_dir}/{name}/*.wav")]

def RestoreTypingProtected():
	api.isTypingProtected = typingProtected

def IsTypingProtected():
	if config.conf["typing_sfx"]["speak_on_protected"]:
		return False
	focus = api.getFocusObject()
	if focus.isProtected:
		return True

confinit()
class TypingSettingsPanel(SettingsPanel):
	title = _("Typing SFX")

	def makeSettings(self, settingsSizer):
		self.hidden_controls = []
		self.num_hidden_controls = []
		sHelper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)

		sHelper.addItem(wx.StaticText(self, label=_("Typing Sound Mode:")))
		self.playTypingSounds = sHelper.addItem(wx.Choice(self, choices=[_("Off"), _("On")]))
		self.playTypingSounds.SetSelection(config.conf["typing_sfx"]["typingsnd"])

		self.tlable = sHelper.addItem(wx.StaticText(self, label=_("Typing Sound Pack:")))
		self.hidden_controls.append(self.tlable)
		self.typingSound = sHelper.addItem(wx.Choice(self))
		self.hidden_controls.append(self.typingSound)
		sounds = get_sounds_folders()
		self.typingSound.Set(sounds)
		self.typingSound.SetStringSelection(config.conf["typing_sfx"]["typing_sound"])

		self.slable = sHelper.addItem(wx.StaticText(self, label=_("sounds")))
		self.hidden_controls.append(self.slable)
		self.sounds = sHelper.addItem(wx.Choice(self))
		self.hidden_controls.append(self.sounds)

		sHelper.addItem(wx.StaticText(self, label=_("Number sound mode:")))
		self.num_sound_mode_choice = sHelper.addItem(wx.Choice(self, choices=[
			_("Off"),
			_("On"),
			_("On with speech")
		]))
		try:
			self.num_sound_mode_choice.SetSelection(config.conf["typing_sfx"]["num_sound_mode"])
		except VdtTypeError:
			config.conf["typing_sfx"]["num_sound_mode"] = 1
			self.num_sound_mode_choice.SetSelection(1)

		self.num_speak_on_protected_label = sHelper.addItem(wx.StaticText(self, label=_("Play number sounds in protected fields:")))
		self.num_hidden_controls.append(self.num_speak_on_protected_label)
		self.num_speak_on_protected_choice = sHelper.addItem(wx.Choice(self, choices=[
			_("Off"),
			_("On"),
			_("On with speech")
		]))
		self.num_hidden_controls.append(self.num_speak_on_protected_choice)
		try:
			self.num_speak_on_protected_choice.SetSelection(config.conf["typing_sfx"]["num_speak_on_protected"])
		except VdtTypeError:
			config.conf["typing_sfx"]["num_speak_on_protected"] = 1
			self.num_speak_on_protected_choice.SetSelection(1)

		self.num_sound_pack_label = sHelper.addItem(wx.StaticText(self, label=_("Number Sound Pack:")))
		self.num_hidden_controls.append(self.num_sound_pack_label)
		self.num_sound_pack_choice = sHelper.addItem(wx.Choice(self, choices=get_number_sound_packs()))
		self.num_hidden_controls.append(self.num_sound_pack_choice)
		self.num_sound_pack_choice.SetStringSelection(config.conf["typing_sfx"]["num_sound_pack"])

		self.num_sounds_label = sHelper.addItem(wx.StaticText(self, label=_("Number sounds:")))
		self.num_hidden_controls.append(self.num_sounds_label)
		self.num_sounds_choice = sHelper.addItem(wx.Choice(self))
		self.num_hidden_controls.append(self.num_sounds_choice)

		sHelper.addItem(wx.StaticText(self, label=_("Speak passwords:")))
		self.speakPasswords = sHelper.addItem(wx.Choice(self, choices=[_("Off"), _("On")]))
		self.speakPasswords.SetSelection(config.conf["typing_sfx"]["speak_on_protected"])

		self.OnChangeTypingSounds(None)
		self.onChange(None)
		self.onNumPackChange(None)
		self.OnNumSoundModeChange(None)

		self.playTypingSounds.Bind(wx.EVT_CHOICE, self.OnChangeTypingSounds)
		self.typingSound.Bind(wx.EVT_CHOICE, self.onChange)
		self.sounds.Bind(wx.EVT_CHOICE, self.onPlay)
		self.num_sound_mode_choice.Bind(wx.EVT_CHOICE, self.OnNumSoundModeChange)
		self.num_sound_pack_choice.Bind(wx.EVT_CHOICE, self.onNumPackChange)
		self.num_sounds_choice.Bind(wx.EVT_CHOICE, self.onNumSoundPlay)


	def postInit(self):
		self.typingSound.SetFocus()

	def OnChangeTypingSounds(self, evt):
		is_on = self.playTypingSounds.GetSelection() == 1
		for control in self.hidden_controls:
			control.Show(is_on)

	def OnNumSoundModeChange(self, evt):
		is_on = self.num_sound_mode_choice.GetSelection() != 0
		for control in self.num_hidden_controls:
			control.Show(is_on)
		if not is_on:
			self.num_speak_on_protected_choice.SetSelection(0)

	def onChange(self, event):
		sounds = get_sounds(self.typingSound.GetStringSelection())
		self.sounds.Set(sounds)
		try:
			self.sounds.SetSelection(0)
		except: pass

	def onNumPackChange(self, event):
		sounds = get_number_sounds(self.num_sound_pack_choice.GetStringSelection())
		self.num_sounds_choice.Set(sounds)
		try:
			self.num_sounds_choice.SetSelection(0)
		except: pass

	def onNumSoundPlay(self, event):
		nvwave.playWaveFile(f"{numbering_dir}/{self.num_sound_pack_choice.GetStringSelection()}/{self.num_sounds_choice.GetStringSelection()}", True)

	def OnDelete(self, event):
		index = self.typingSound.Selection
		Pack = f"{effects_dir}/{self.typingSound.GetStringSelection()}"
		msg = wx.MessageBox(_("Are you sure you want to delete {pack}?").format(pack=os.path.basename(Pack)), _("confirm"), style=wx.YES_NO)
		if msg == wx.YES:
			shutil.rmtree(Pack)
			self.typingSound.Delete(self.typingSound.Selection)
			try:
				self.typingSound.Selection = index-1
			except:
				self.typingSound.Selection = 0

	def OnNumPackDelete(self, event):
		index = self.num_sound_pack_choice.Selection
		Pack = f"{numbering_dir}/{self.num_sound_pack_choice.GetStringSelection()}"
		msg = wx.MessageBox(_("Are you sure you want to delete {pack}?").format(pack=os.path.basename(Pack)), _("confirm"), style=wx.YES_NO)
		if msg == wx.YES:
			shutil.rmtree(Pack)
			self.num_sound_pack_choice.Delete(self.num_sound_pack_choice.Selection)
			try:
				self.num_sound_pack_choice.Selection = index-1
			except:
				self.num_sound_pack_choice.Selection = 0

	def onPlay(self, event):
		nvwave.playWaveFile(f"{effects_dir}/{self.typingSound.GetStringSelection()}/{self.sounds.GetStringSelection()}", True)

	def OnCreate(self, event):
		wx.CallAfter(NewPack, mainFrame, False)

	def OnNumPackCreate(self, event):
		wx.CallAfter(NewPack, mainFrame, True)

	def onSave(self):
		config.conf["typing_sfx"]["typing_sound"] = self.typingSound.GetStringSelection()
		config.conf["typing_sfx"]["speak_on_protected"] = self.speakPasswords.GetSelection()
		config.conf["typing_sfx"]["typingsnd"] = self.playTypingSounds.GetSelection()
		config.conf["typing_sfx"]["num_sound_mode"] = self.num_sound_mode_choice.GetSelection()
		config.conf["typing_sfx"]["num_speak_on_protected"] = self.num_speak_on_protected_choice.GetSelection()
		config.conf["typing_sfx"]["num_sound_pack"] = self.num_sound_pack_choice.GetStringSelection()

class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		NVDASettingsDialog.categoryClasses.append(TypingSettingsPanel)

	def IsEditable(self, object):
		return (object.role in controls or STATE_EDITABLE in object.states) and not STATE_READONLY in object.states

	def get_sound_path(self, sound_name):
		return os.path.join(numbering_dir, config.conf["typing_sfx"]["num_sound_pack"], sound_name)

	def event_gainFocus(self, object, nextHandler):
		api.isTypingProtected = IsTypingProtected
		nextHandler()

	def event_typedCharacter(self, obj, nextHandler, ch):
		try:
			num_sound_mode = config.conf["typing_sfx"]["num_sound_mode"]
		except VdtTypeError:
			num_sound_mode = 1
			config.conf["typing_sfx"]["num_sound_mode"] = 1

		if num_sound_mode != 0:
			try:
				num_speak_on_protected = config.conf["typing_sfx"]["num_speak_on_protected"]
			except VdtTypeError:
				num_speak_on_protected = 1
				config.conf["typing_sfx"]["num_speak_on_protected"] = 1

			focus = api.getFocusObject()
			mode = num_sound_mode
			if focus.isProtected:
				mode = num_speak_on_protected

			if mode != 0 and self.IsEditable(focus) and ch.isdigit():
				sound_path = self.get_sound_path(f"{ch}.wav")
				if not os.path.exists(sound_path):
					sound_path = self.get_sound_path("Numbering.wav")

				if os.path.exists(sound_path):
					nvwave.playWaveFile(sound_path, True)
					if mode == 1:
						return  # No speech, no typing sound
					else:  # mode == 2
						return nextHandler()  # Speech, but no typing sound

		if self.IsEditable(obj) and config.conf["typing_sfx"]["typingsnd"]:
			if ch == " ":
				nvwave.playWaveFile(os.path.join(effects_dir, config.conf['typing_sfx']['typing_sound'], "space.wav"), True)
			elif ch == "\b":
				nvwave.playWaveFile(os.path.join(effects_dir, config.conf['typing_sfx']['typing_sound'], "delete.wav"), True)
			elif os.path.isfile(os.path.join(effects_dir, config.conf['typing_sfx']['typing_sound'], "return.wav")) and (ord(ch) == 13 or ch == "\n"):
				nvwave.playWaveFile(os.path.join(effects_dir, config.conf['typing_sfx']['typing_sound'], "return.wav"), True)
			else:
				count = self.SoundsCount(config.conf["typing_sfx"]["typing_sound"])
				nvwave.playWaveFile(os.path.join(effects_dir, config.conf['typing_sfx']['typing_sound'], "typing.wav" if count<=0 else f"typing_{randint(1, count)}.wav"), True)
		nextHandler()

	def SoundsCount(self, name):
		path = f"{effects_dir}/{name}"
		files = len([file for file in os.listdir(path) if file.startswith("typing_")])
		return files


	@script(
		description = _("Toggles the typing sounds mode."),
		category=_("Typing SFX"),
		gestures=["kb:nvda+shift+k"])
	def script_toggle_typing_sounds(self, gesture):
		current = config.conf["typing_sfx"]["typingsnd"]
		if current:
			config.conf["typing_sfx"]["typingsnd"] = False
			message(_("typing sounds off"))
		else:
			config.conf["typing_sfx"]["typingsnd"] = True
			message(_("typing sounds on"))

	@script(
		description=_("Toggles the Number sounds mode."),
		category="Typing SFX",
		gesture="kb:nvda+shift+n")
	def script_toggleNumSounds(self, gesture):
		num_sound_mode = config.conf["typing_sfx"]["num_sound_mode"]
		num_sound_mode = (num_sound_mode + 1) % 3
		config.conf["typing_sfx"]["num_sound_mode"] = num_sound_mode
		if num_sound_mode == 0:
			message(_("Number sound off"))
		elif num_sound_mode == 1:
			message(_("Number sound on"))
		else:
			message(_("Number sound on with speech"))

	@script(
		description=_("Toggles the protected sounds mode."),
		category="Typing SFX",
		gesture="kb:nvda+shift+o")
	def script_toggleNumProtectedSounds(self, gesture):
		try:
			num_sound_mode = config.conf["typing_sfx"]["num_sound_mode"]
		except VdtTypeError:
			num_sound_mode = 1
			config.conf["typing_sfx"]["num_sound_mode"] = 1

		if num_sound_mode == 0:
			message(_("please enable the number sound first"))
			return

		try:
			num_speak_on_protected = config.conf["typing_sfx"]["num_speak_on_protected"]
		except VdtTypeError:
			num_speak_on_protected = 1
			config.conf["typing_sfx"]["num_speak_on_protected"] = 1

		num_speak_on_protected = (num_speak_on_protected + 1) % 3
		config.conf["typing_sfx"]["num_speak_on_protected"] = num_speak_on_protected
		if num_speak_on_protected == 0:
			message(_("Protected number sound off"))
		elif num_speak_on_protected == 1:
			message(_("Protected number sound on"))
		else:
			message(_("Protected number sound on with speech"))

	@script(
		description = _("Toggles the protected Speak mode."),
		category = _("Typing SFX"),
		gestures = ["kb:nvda+shift+p"])
	def script_toggle_speak_passwords(self, gesture):
		if config.conf["typing_sfx"]["speak_on_protected"]:
			config.conf["typing_sfx"]["speak_on_protected"] = False
			message(_("speak passwords off"))
		else:
			config.conf["typing_sfx"]["speak_on_protected"] = True
			message(_("speak passwords on"))

	def terminate(self):
		RestoreTypingProtected()
		NVDASettingsDialog.categoryClasses.remove(TypingSettingsPanel)