import nvwave
import globalPluginHandler
import speech
import config
import os
import glob
import random
import wx
import ctypes
import configparser
import globalVars
import time
import unicodedata
from ctypes import wintypes
import addonHandler
import api
import gui
import logHandler
import textInfos
import controlTypes
from globalCommands import SCRCAT_CONFIG
from ui import message
from scriptHandler import script
from gui import NVDASettingsDialog, guiHelper, mainFrame
from gui.settingsDialogs import SettingsPanel
from controlTypes import STATE_READONLY, STATE_EDITABLE
from configobj.validate import VdtTypeError

addonHandler.initTranslation()
effects_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), "effects", "Typing")
numbering_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), "effects", "numbering")
controls = (8, 52, 82)
typingProtected = api.isTypingProtected

_original_speak = None
_suppress_digit_info = {"char": None, "time": 0}
_cached_speak_on_protected = True

def custom_speak(speechSequence, *args, **kwargs):
	now = time.time()
	target_char = _suppress_digit_info.get("char")
	last_time = _suppress_digit_info.get("time", 0)
	if target_char and (now - last_time) < 0.60:
		clean_text = ""
		if isinstance(speechSequence, str):
			clean_text = speechSequence.strip()
		elif isinstance(speechSequence, (list, tuple)):
			items = []
			for item in speechSequence:
				if isinstance(item, str):
					items.append(item.strip())
			clean_text = "".join(items)
		clean_text = clean_text.replace(" ", "").replace("\n", "").replace("\r", "")
		if clean_text and set(clean_text) == {target_char}:
			return
	if _original_speak:
		return _original_speak(speechSequence, *args, **kwargs)

def hook_speech():
	global _original_speak
	if _original_speak is None and hasattr(speech, 'speak'):
		_original_speak = speech.speak
		speech.speak = custom_speak

def unhook_speech():
	global _original_speak
	if _original_speak is not None and hasattr(speech, 'speak'):
		speech.speak = _original_speak
		_original_speak = None

def get_base_config_section():
	try:
		if "TypingSFX" not in config.conf:
			config.conf["TypingSFX"] = {}
		return config.conf["TypingSFX"]
	except Exception:
		if hasattr(config.conf, 'rootSection') and "TypingSFX" in config.conf.rootSection:
			return config.conf.rootSection["TypingSFX"]
		return {}

def get_nvda_profile_setting(key, default_val):
	try:
		sec = get_base_config_section()
		if key in sec:
			return sec[key]
	except Exception:
		pass
	if hasattr(config.conf, 'rootSection') and "TypingSFX" in config.conf.rootSection:
		try:
			if key in config.conf.rootSection["TypingSFX"]:
				return config.conf.rootSection["TypingSFX"][key]
		except Exception:
			pass
	return default_val

def _isWordChar(ch: str) -> bool:
	return bool(ch) and unicodedata.category(ch)[0] in "LMN"

def _getTypedWordBuffer():
	speechModule = getattr(speech, "speech", None)
	if speechModule is not None:
		buf = getattr(speechModule, "_curWordChars", None)
		if buf is not None:
			return buf
	return getattr(speech, "curWordChars", None)

def _append_to_typed_word_buffer(ch: str):
	speechModule = getattr(speech, "speech", None)
	if speechModule is not None:
		buf = getattr(speechModule, "_curWordChars", None)
		if buf is None:
			speechModule._curWordChars = [ch]
		else:
			buf.append(ch)
		return
	buf = getattr(speech, "curWordChars", None)
	if buf is None:
		speech.curWordChars = [ch]
	else:
		buf.append(ch)

def _isTypedWordEchoEnabled() -> bool:
	try:
		mode = config.conf["keyboard"]["speakTypedWords"]
	except KeyError:
		return False
	if isinstance(mode, bool):
		return mode
	try:
		from config.configFlags import TypingEcho
		if mode == TypingEcho.OFF.value:
			return False
		if mode == TypingEcho.ALWAYS.value:
			return True
	except ImportError:
		return bool(mode)
	isFocusEditable = getattr(getattr(speech, "speech", None), "isFocusEditable", None)
	if isFocusEditable:
		try:
			return isFocusEditable()
		except Exception:
			pass
	focus = api.getFocusObject()
	if focus:
		try:
			if hasattr(controlTypes, 'Role') and hasattr(controlTypes.Role, 'TERMINAL') and focus.role == controlTypes.Role.TERMINAL:
				return True
			if hasattr(controlTypes, 'ROLE_TERMINAL') and focus.role == controlTypes.ROLE_TERMINAL:
				return True
			if hasattr(focus, 'isEditable') and focus.isEditable:
				return True
		except Exception:
			pass
	return True

def _trailingWord(text: str) -> str:
	end = len(text)
	while end > 0 and not _isWordChar(text[end - 1]):
		end -= 1
	start = end
	while start > 0 and _isWordChar(text[start - 1]):
		start -= 1
	return text[start:end]

def get_number_sound_packs():
	return [folder for folder in os.listdir(numbering_dir) if os.path.isdir(os.path.join(numbering_dir, folder))]

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

def get_profiles_dir(create=False):
	try:
		path = os.path.join(globalVars.appArgs.configPath, "profiles", "Typing SFX")
	except Exception:
		path = os.path.join(os.path.abspath(os.path.dirname(__file__)), "profiles", "Typing SFX")
	if create and not os.path.exists(path):
		try:
			os.makedirs(path, exist_ok=True)
		except Exception:
			pass
	try:
		old_path = os.path.join(globalVars.appArgs.configPath, "Typing SFX")
		if os.path.isdir(old_path):
			ini_files = [f for f in os.listdir(old_path) if f.lower().endswith(".ini")]
			if ini_files:
				os.makedirs(path, exist_ok=True)
				for item in ini_files:
					src = os.path.join(old_path, item)
					dst = os.path.join(path, item)
					if not os.path.exists(dst):
						try:
							os.replace(src, dst)
						except Exception:
							pass
			try:
				if not os.listdir(old_path):
					os.rmdir(old_path)
			except Exception:
				pass
	except Exception:
		pass
	return path

def get_app_profile_path(app_name, create=False):
	clean_name = str(app_name).lower().replace(".exe", "").strip()
	return os.path.join(get_profiles_dir(create=create), f"{clean_name}.ini")

def get_user_profiles():
	p_dir = get_profiles_dir()
	profiles = []
	if os.path.isdir(p_dir):
		for f in os.listdir(p_dir):
			if f.lower().endswith(".ini"):
				app_name = f[:-4].lower()
				ini_path = os.path.join(p_dir, f)
				disp_name = app_name
				try:
					cp = configparser.ConfigParser()
					cp.read(ini_path, encoding="utf-8")
					if "TypingSFX" in cp and "display_name" in cp["TypingSFX"]:
						d = cp["TypingSFX"]["display_name"].strip()
						if d:
							disp_name = d
				except Exception:
					pass
				profiles.append((app_name, disp_name))
	return sorted(profiles, key=lambda x: x[1].lower())

def rename_profile(app_name, new_display_name):
	profile_name = str(app_name).lower().replace(".exe", "").strip()
	if profile_name == "default":
		return
	ini_path = get_app_profile_path(profile_name)
	if os.path.isfile(ini_path):
		try:
			cp = configparser.ConfigParser()
			cp.read(ini_path, encoding="utf-8")
			if "TypingSFX" not in cp:
				cp["TypingSFX"] = {}
			cp["TypingSFX"]["display_name"] = str(new_display_name).strip()
			with open(ini_path, "w", encoding="utf-8") as f:
				cp.write(f)
		except Exception as e:
			logHandler.log.exception("Error renaming profile %s: %s" % (profile_name, e))

def load_profile(profile_name="default"):
	profile_name = str(profile_name).lower().replace(".exe", "").strip()
	sounds = get_sounds_folders()
	default_sound = sounds[0] if sounds else "Default"
	number_packs = get_number_sound_packs()
	default_num_pack = number_packs[0] if number_packs else "Default"

	g_typingsnd = bool(get_nvda_profile_setting("typingsnd", True))
	g_typing_sound = str(get_nvda_profile_setting("typing_sound", default_sound))
	g_speak_on_protected = bool(get_nvda_profile_setting("speak_on_protected", True))
	g_protected_symbol = str(get_nvda_profile_setting("protected_symbol", ""))
	try:
		g_num_sound_mode = int(get_nvda_profile_setting("num_sound_mode", 1))
	except Exception:
		g_num_sound_mode = 1
	try:
		g_num_speak_on_protected = int(get_nvda_profile_setting("num_speak_on_protected", 1))
	except Exception:
		g_num_speak_on_protected = 1
	g_num_sound_pack = str(get_nvda_profile_setting("num_sound_pack", default_num_pack))

	cfg = {
		"typingsnd": g_typingsnd,
		"typing_sound": g_typing_sound,
		"speak_on_protected": g_speak_on_protected,
		"protected_symbol": g_protected_symbol,
		"num_sound_mode": g_num_sound_mode,
		"num_speak_on_protected": g_num_speak_on_protected,
		"num_sound_pack": g_num_sound_pack,
	}

	if profile_name == "default":
		return cfg

	ini_path = get_app_profile_path(profile_name)
	if os.path.isfile(ini_path):
		try:
			cp = configparser.ConfigParser()
			cp.read(ini_path, encoding="utf-8")
			if "TypingSFX" in cp:
				sec = cp["TypingSFX"]
				if "typingsnd" in sec:
					cfg["typingsnd"] = sec.getboolean("typingsnd", fallback=cfg["typingsnd"])
				if "typing_sound" in sec:
					cfg["typing_sound"] = sec.get("typing_sound", fallback=cfg["typing_sound"])
				if "speak_on_protected" in sec:
					cfg["speak_on_protected"] = sec.getboolean("speak_on_protected", fallback=cfg["speak_on_protected"])
				if "protected_symbol" in sec:
					cfg["protected_symbol"] = str(sec.get("protected_symbol", fallback=cfg["protected_symbol"]))
				if "num_sound_mode" in sec:
					cfg["num_sound_mode"] = sec.getint("num_sound_mode", fallback=cfg["num_sound_mode"])
				if "num_speak_on_protected" in sec:
					cfg["num_speak_on_protected"] = sec.getint("num_speak_on_protected", fallback=cfg["num_speak_on_protected"])
				if "num_sound_pack" in sec:
					cfg["num_sound_pack"] = sec.get("num_sound_pack", fallback=cfg["num_sound_pack"])
		except Exception as e:
			logHandler.log.exception("Error loading profile ini for %s: %s" % (profile_name, e))

	return cfg

def save_profile(profile_name, cfg_data):
	global _cached_speak_on_protected
	profile_name = str(profile_name).lower().replace(".exe", "").strip()
	if "speak_on_protected" in cfg_data:
		_cached_speak_on_protected = bool(cfg_data["speak_on_protected"])
	if profile_name == "default":
		try:
			sec = get_base_config_section()
			for k, v in cfg_data.items():
				sec[k] = v
			config.conf.save()
		except Exception as e:
			logHandler.log.exception("Error saving NVDA profile config: %s" % e)
	else:
		ini_path = get_app_profile_path(profile_name, create=True)
		try:
			cp = configparser.ConfigParser()
			disp_name = profile_name
			if os.path.isfile(ini_path):
				try:
					existing_cp = configparser.ConfigParser()
					existing_cp.read(ini_path, encoding="utf-8")
					if "TypingSFX" in existing_cp and "display_name" in existing_cp["TypingSFX"]:
						disp_name = existing_cp["TypingSFX"]["display_name"]
				except Exception:
					pass

			current_cfg = load_profile(profile_name)
			current_cfg.update(cfg_data)

			cp["TypingSFX"] = {
				"display_name": str(disp_name),
				"typingsnd": str(current_cfg["typingsnd"]),
				"typing_sound": str(current_cfg["typing_sound"]),
				"speak_on_protected": str(current_cfg["speak_on_protected"]),
				"protected_symbol": str(current_cfg.get("protected_symbol", "")),
				"num_sound_mode": str(current_cfg["num_sound_mode"]),
				"num_speak_on_protected": str(current_cfg["num_speak_on_protected"]),
				"num_sound_pack": str(current_cfg["num_sound_pack"]),
			}
			with open(ini_path, "w", encoding="utf-8") as f:
				cp.write(f)
		except Exception as e:
			logHandler.log.exception("Error saving profile ini for %s: %s" % (profile_name, e))

def delete_profile(profile_name):
	profile_name = str(profile_name).lower().replace(".exe", "").strip()
	if profile_name == "default":
		return
	ini_path = get_app_profile_path(profile_name, create=False)
	if os.path.isfile(ini_path):
		try:
			os.remove(ini_path)
			p_dir = get_profiles_dir(create=False)
			if os.path.isdir(p_dir) and not os.listdir(p_dir):
				os.rmdir(p_dir)
		except Exception as e:
			logHandler.log.exception("Error deleting profile ini for %s: %s" % (profile_name, e))

def get_effective_config(app_name=None):
	if not app_name:
		focus = api.getFocusObject()
		if focus and hasattr(focus, 'appModule') and focus.appModule:
			app_name = focus.appModule.appName
	if app_name:
		return load_profile(app_name)
	return load_profile("default")

def get_active_profile_name():
	focus = api.getFocusObject()
	app_name = focus.appModule.appName if focus and hasattr(focus, 'appModule') and focus.appModule else None
	if app_name:
		clean_name = str(app_name).lower().replace(".exe", "").strip()
		ini_path = get_app_profile_path(clean_name)
		if os.path.isfile(ini_path):
			return clean_name
	return "default"

def IsTypingProtected():
	if _cached_speak_on_protected:
		return False
	try:
		return typingProtected()
	except Exception:
		focus = api.getFocusObject()
		return bool(focus and getattr(focus, 'isProtected', False))

def confinit():
	sounds = get_sounds_folders()
	default_sound = sounds[0] if sounds else "Default"
	number_packs = get_number_sound_packs()
	default_num_pack = number_packs[0] if number_packs else "Default"
	confspec = {
		"typingsnd": "boolean(default=true)",
		"typing_sound": f"string(default={default_sound})",
		"speak_on_protected": "boolean(default=True)",
		"protected_symbol": "string(default='')",
		"num_sound_mode": "integer(default=1, min=0, max=2)",
		"num_speak_on_protected": "integer(default=1, min=0, max=2)",
		"num_sound_pack": f"string(default={default_num_pack})"
	}
	config.confspec["TypingSFX"] = confspec

confinit()

def get_process_name(pid):
	try:
		import appModuleHandler
		if hasattr(appModuleHandler, 'getAppNameFromProcessID'):
			name = appModuleHandler.getAppNameFromProcessID(pid)
			if name:
				return name
	except Exception:
		pass

	try:
		kernel32 = ctypes.windll.kernel32
		for access in (0x1000, 0x0400, 0x0010 | 0x0400):
			hProcess = kernel32.OpenProcess(access, False, pid)
			if hProcess:
				buf = ctypes.create_unicode_buffer(1024)
				size = wintypes.DWORD(1024)
				if hasattr(kernel32, 'QueryFullProcessImageNameW') and kernel32.QueryFullProcessImageNameW(hProcess, 0, buf, ctypes.byref(size)):
					kernel32.CloseHandle(hProcess)
					return os.path.basename(buf.value)
				try:
					if ctypes.windll.psapi.GetModuleFileNameExW(hProcess, 0, buf, 1024):
						kernel32.CloseHandle(hProcess)
						return os.path.basename(buf.value)
				except Exception:
					pass
				kernel32.CloseHandle(hProcess)
	except Exception:
		pass
	return None

def get_running_applications():
	apps = {}
	ignored_exes = {
		"nvda", "shellexperiencehost", "searchhost", "startmenuexperiencehost",
		"systemsettings", "textinputhost", "applicationframehost", "lockapp"
	}
	ignored_titles = {
		"program manager", "windows input experience", "settings", "microsoft text input application"
	}

	try:
		user32 = ctypes.windll.user32

		def enum_windows_callback(hwnd, lParam):
			try:
				if user32.IsWindowVisible(hwnd):
					length = user32.GetWindowTextLengthW(hwnd)
					if length > 0:
						pid = wintypes.DWORD()
						user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
						if pid.value:
							pname = get_process_name(pid.value)
							if pname:
								app_clean = str(pname).lower().replace(".exe", "").strip()
								if app_clean and app_clean not in ignored_exes:
									cls_buf = ctypes.create_unicode_buffer(256)
									user32.GetClassNameW(hwnd, cls_buf, 256)
									cls_name = cls_buf.value

									if cls_name in ("Shell_TrayWnd", "Progman", "WorkerW", "Shell_SecondaryTrayWnd"):
										return True

									if app_clean == "explorer" and cls_name not in ("CabinetWClass", "ExploreWClass"):
										return True

									title_buf = ctypes.create_unicode_buffer(length + 1)
									user32.GetWindowTextW(hwnd, title_buf, length + 1)
									w_title = title_buf.value.strip()
									if w_title and w_title.lower() not in ignored_titles:
										display = f"{app_clean} ({w_title})"
										if app_clean not in apps:
											apps[app_clean] = display
			except Exception as e:
				logHandler.log.exception("Error in window callback: %s" % e)
			return True

		WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
		user32.EnumWindows(WNDENUMPROC(enum_windows_callback), 0)
	except Exception as e:
		logHandler.log.exception("Error enumerating windows: %s" % e)

	if not apps:
		try:
			import appModuleHandler
			if hasattr(appModuleHandler, 'runningAppModules'):
				for app_name in appModuleHandler.runningAppModules:
					app_clean = str(app_name).lower().replace(".exe", "").strip()
					if app_clean and app_clean not in ignored_exes and app_clean not in apps:
						apps[app_clean] = app_clean
		except Exception as e:
			logHandler.log.exception("Error scanning runningAppModules: %s" % e)

	if not apps:
		try:
			focus = api.getFocusObject()
			if focus and hasattr(focus, 'appModule') and focus.appModule:
				fg_app = str(focus.appModule.appName).lower().replace(".exe", "").strip()
				if fg_app and fg_app not in ignored_exes and fg_app not in apps:
					apps[fg_app] = fg_app
		except Exception:
			pass

	return list(apps.items())

class SoundProfileSettingsDialog(wx.Dialog):
	def __init__(self, parent, profile_name="Default"):
		self.profile_name = profile_name.lower().replace(".exe", "").strip()
		is_default = (self.profile_name == "default")
		title_str = _("Typing SFX Settings - Default") if is_default else _("Typing SFX Settings - {profile}").format(profile=self.profile_name)
		super().__init__(parent, title=title_str)

		self.cfg = load_profile(self.profile_name)

		mainSizer = wx.BoxSizer(wx.VERTICAL)
		sHelper = guiHelper.BoxSizerHelper(self, sizer=mainSizer)

		self.hidden_controls = []
		self.num_hidden_controls = []

		sHelper.addItem(wx.StaticText(self, label=_("Typing Sound Mode:")))
		self.playTypingSounds = sHelper.addItem(wx.Choice(self, choices=[_("Off"), _("On")]))
		self.playTypingSounds.SetSelection(1 if self.cfg["typingsnd"] else 0)

		self.tlable = sHelper.addItem(wx.StaticText(self, label=_("Typing Sound Pack:")))
		self.hidden_controls.append(self.tlable)
		self.typingSound = sHelper.addItem(wx.Choice(self))
		self.hidden_controls.append(self.typingSound)
		sounds = get_sounds_folders()
		self.typingSound.Set(sounds)
		if self.cfg["typing_sound"] in sounds:
			self.typingSound.SetStringSelection(self.cfg["typing_sound"])
		elif sounds:
			self.typingSound.SetSelection(0)

		self.slable = sHelper.addItem(wx.StaticText(self, label=_("sounds")))
		self.hidden_controls.append(self.slable)
		self.sounds = sHelper.addItem(wx.Choice(self))
		self.hidden_controls.append(self.sounds)

		sHelper.addItem(wx.StaticText(self, label=_("Number sound mode:")))
		self.num_sound_mode_choice = sHelper.addItem(wx.Choice(self, choices=[_("Off"), _("On"), _("On with speech")]))
		try:
			self.num_sound_mode_choice.SetSelection(int(self.cfg["num_sound_mode"]))
		except Exception:
			self.num_sound_mode_choice.SetSelection(1)

		self.num_speak_on_protected_label = sHelper.addItem(wx.StaticText(self, label=_("Play number sounds in protected fields:")))
		self.num_hidden_controls.append(self.num_speak_on_protected_label)
		self.num_speak_on_protected_choice = sHelper.addItem(wx.Choice(self, choices=[_("Off"), _("On"), _("On with speech")]))
		self.num_hidden_controls.append(self.num_speak_on_protected_choice)
		try:
			self.num_speak_on_protected_choice.SetSelection(int(self.cfg["num_speak_on_protected"]))
		except Exception:
			self.num_speak_on_protected_choice.SetSelection(1)

		self.num_sound_pack_label = sHelper.addItem(wx.StaticText(self, label=_("Number Sound Pack:")))
		self.num_hidden_controls.append(self.num_sound_pack_label)
		num_packs = get_number_sound_packs()
		self.num_sound_pack_choice = sHelper.addItem(wx.Choice(self, choices=num_packs))
		self.num_hidden_controls.append(self.num_sound_pack_choice)
		if self.cfg["num_sound_pack"] in num_packs:
			self.num_sound_pack_choice.SetStringSelection(self.cfg["num_sound_pack"])
		elif num_packs:
			self.num_sound_pack_choice.SetSelection(0)

		self.num_sounds_label = sHelper.addItem(wx.StaticText(self, label=_("Number sounds:")))
		self.num_hidden_controls.append(self.num_sounds_label)
		self.num_sounds_choice = sHelper.addItem(wx.Choice(self))
		self.num_hidden_controls.append(self.num_sounds_choice)

		sHelper.addItem(wx.StaticText(self, label=_("Speak passwords:")))
		self.speakPasswords = sHelper.addItem(wx.Choice(self, choices=[_("Off"), _("On")]))
		self.speakPasswords.SetSelection(1 if self.cfg["speak_on_protected"] else 0)

		self.protected_symbol_label = sHelper.addItem(wx.StaticText(self, label=_("Custom protected field text (leave blank for default):")))
		self.protectedSymbolText = sHelper.addItem(wx.TextCtrl(self, value=str(self.cfg.get("protected_symbol", ""))))

		self.OnChangeTypingSounds(None)
		self.onChange(None)
		self.onNumPackChange(None)
		self.OnNumSoundModeChange(None)
		self.OnChangeSpeakPasswords(None)
		self.playTypingSounds.Bind(wx.EVT_CHOICE, self.OnChangeTypingSounds)
		self.typingSound.Bind(wx.EVT_CHOICE, self.onChange)
		self.sounds.Bind(wx.EVT_CHOICE, self.onPlay)
		self.num_sound_mode_choice.Bind(wx.EVT_CHOICE, self.OnNumSoundModeChange)
		self.num_sound_pack_choice.Bind(wx.EVT_CHOICE, self.onNumPackChange)
		self.num_sounds_choice.Bind(wx.EVT_CHOICE, self.onNumSoundPlay)
		self.speakPasswords.Bind(wx.EVT_CHOICE, self.OnChangeSpeakPasswords)

		btnSizer = self.CreateButtonSizer(wx.OK | wx.CANCEL)
		if btnSizer:
			mainSizer.Add(btnSizer, 0, wx.ALL | wx.ALIGN_RIGHT, 10)
		self.SetSizerAndFit(mainSizer)
		self.playTypingSounds.SetFocus()
		self.Bind(wx.EVT_BUTTON, self.onSave, id=wx.ID_OK)

	def OnChangeSpeakPasswords(self, evt):
		is_speak_off = self.speakPasswords.GetSelection() == 0
		self.protected_symbol_label.Enable(is_speak_off)
		self.protectedSymbolText.Enable(is_speak_off)

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
		except Exception:
			pass

	def onNumPackChange(self, event):
		sounds = get_number_sounds(self.num_sound_pack_choice.GetStringSelection())
		self.num_sounds_choice.Set(sounds)
		try:
			self.num_sounds_choice.SetSelection(0)
		except Exception:
			pass

	def onNumSoundPlay(self, event):
		sound_sel = self.num_sounds_choice.GetStringSelection()
		pack_sel = self.num_sound_pack_choice.GetStringSelection()
		if sound_sel and pack_sel:
			nvwave.playWaveFile(os.path.join(numbering_dir, pack_sel, sound_sel), True)

	def onPlay(self, event):
		sound_sel = self.sounds.GetStringSelection()
		pack_sel = self.typingSound.GetStringSelection()
		if sound_sel and pack_sel:
			nvwave.playWaveFile(os.path.join(effects_dir, pack_sel, sound_sel), True)

	def onSave(self, event):
		cfg_data = {
			"typing_sound": self.typingSound.GetStringSelection(),
			"speak_on_protected": (self.speakPasswords.GetSelection() == 1),
			"protected_symbol": self.protectedSymbolText.GetValue().strip(),
			"typingsnd": (self.playTypingSounds.GetSelection() == 1),
			"num_sound_mode": self.num_sound_mode_choice.GetSelection(),
			"num_speak_on_protected": self.num_speak_on_protected_choice.GetSelection(),
			"num_sound_pack": self.num_sound_pack_choice.GetStringSelection()
		}
		save_profile(self.profile_name, cfg_data)
		self.EndModal(wx.ID_OK)

class NewProfileDialog(wx.Dialog):
	def __init__(self, parent):
		super().__init__(parent, title=_("Create New Sound Profile"))
		mainSizer = wx.BoxSizer(wx.VERTICAL)
		sHelper = guiHelper.BoxSizerHelper(self, sizer=mainSizer)

		sHelper.addItem(wx.StaticText(self, label=_("Profile Name:")))
		self.displayNameText = sHelper.addItem(wx.TextCtrl(self))

		sHelper.addItem(wx.StaticText(self, label=_("Select running application:")))
		self.running_apps = get_running_applications()
		choices = [item[1] for item in self.running_apps]
		if not choices:
			choices = [_("No running applications detected")]
		self.appChoice = sHelper.addItem(wx.Choice(self, choices=choices))
		if self.running_apps:
			self.appChoice.SetSelection(0)

		btnSizer = self.CreateButtonSizer(wx.OK | wx.CANCEL)
		if btnSizer:
			mainSizer.Add(btnSizer, 0, wx.ALL | wx.ALIGN_RIGHT, 10)
		self.SetSizerAndFit(mainSizer)

		self.timer = wx.Timer(self)
		self.Bind(wx.EVT_TIMER, self.onAutoRefresh, self.timer)
		self.Bind(wx.EVT_ACTIVATE, self.onActivate)
		self.Bind(wx.EVT_CLOSE, self.onClose)
		self.timer.Start(2000)

		self.displayNameText.SetFocus()

	def onActivate(self, event):
		if event.GetActive():
			self.refreshRunningApps()
		event.Skip()

	def onAutoRefresh(self, event):
		self.refreshRunningApps()

	def refreshRunningApps(self):
		new_apps = get_running_applications()
		if new_apps != self.running_apps:
			sel_app = None
			sel_idx = self.appChoice.GetSelection()
			if self.running_apps and sel_idx != wx.NOT_FOUND and sel_idx < len(self.running_apps):
				sel_app = self.running_apps[sel_idx][0]

			self.running_apps = new_apps
			choices = [item[1] for item in self.running_apps]
			if not choices:
				choices = [_("No running applications detected")]
			self.appChoice.Set(choices)

			new_idx = 0
			if sel_app and self.running_apps:
				for i, (app_code, _) in enumerate(self.running_apps):
					if app_code == sel_app:
						new_idx = i
						break
			if self.running_apps:
				self.appChoice.SetSelection(new_idx)

	def onClose(self, event):
		if hasattr(self, 'timer') and self.timer.IsRunning():
			self.timer.Stop()
		event.Skip()

	def get_selected_app(self):
		if hasattr(self, 'timer') and self.timer.IsRunning():
			self.timer.Stop()
		disp = self.displayNameText.GetValue().strip()
		app_name = None
		sel_idx = self.appChoice.GetSelection()
		if self.running_apps and sel_idx != wx.NOT_FOUND and sel_idx < len(self.running_apps):
			app_name = self.running_apps[sel_idx][0]
		if app_name:
			disp_name = disp if disp else app_name
			return app_name, disp_name
		return None, None

class ManageSoundConfigurationsDialog(wx.Dialog):
	def __init__(self, parent):
		super().__init__(parent, title=_("Typing SFX Profiles"))
		mainSizer = wx.BoxSizer(wx.VERTICAL)

		sHelper = guiHelper.BoxSizerHelper(self, sizer=mainSizer)
		sHelper.addItem(wx.StaticText(self, label=_("Profiles")))

		self.profilesListBox = wx.ListBox(self, style=wx.LB_SINGLE)
		mainSizer.Add(self.profilesListBox, 1, wx.EXPAND | wx.ALL, 10)

		btnBox = wx.BoxSizer(wx.HORIZONTAL)
		self.editBtn = wx.Button(self, label=_("&Edit Settings..."))
		self.renameBtn = wx.Button(self, label=_("&Rename..."))
		self.deleteBtn = wx.Button(self, label=_("&Delete"))
		self.newBtn = wx.Button(self, label=_("&New..."))
		self.closeBtn = wx.Button(self, id=wx.ID_CANCEL, label=_("&Close"))

		btnBox.Add(self.editBtn, 0, wx.RIGHT, 5)
		btnBox.Add(self.renameBtn, 0, wx.RIGHT, 5)
		btnBox.Add(self.deleteBtn, 0, wx.RIGHT, 5)
		btnBox.Add(self.newBtn, 0, wx.RIGHT, 5)
		btnBox.Add(self.closeBtn, 0)
		mainSizer.Add(btnBox, 0, wx.ALIGN_RIGHT | wx.ALL, 10)

		self.editBtn.Bind(wx.EVT_BUTTON, self.onEditProfile)
		self.renameBtn.Bind(wx.EVT_BUTTON, self.onRenameProfile)
		self.deleteBtn.Bind(wx.EVT_BUTTON, self.onDeleteProfile)
		self.newBtn.Bind(wx.EVT_BUTTON, self.onNewProfile)
		self.profilesListBox.Bind(wx.EVT_LISTBOX_DCLICK, self.onEditProfile)
		self.profilesListBox.Bind(wx.EVT_LISTBOX, self.onSelectProfile)
		self.profilesListBox.Bind(wx.EVT_KEY_DOWN, self.onProfilesListKeyDown)

		self.refreshProfiles()
		self.SetSizerAndFit(mainSizer)
		self.profilesListBox.SetFocus()

	def onProfilesListKeyDown(self, event):
		key = event.GetKeyCode()
		if key == wx.WXK_DELETE:
			self.onDeleteProfile(None)
		elif key == wx.WXK_F2:
			self.onRenameProfile(None)
		else:
			event.Skip()

	def refreshProfiles(self):
		self.profilesListBox.Clear()
		self.profilesListBox.Append(_("Default"), clientData="default")
		try:
			user_profiles = get_user_profiles()
			for app_name, disp_name in user_profiles:
				self.profilesListBox.Append(disp_name, clientData=app_name)
		except Exception as e:
			logHandler.log.exception("Error refreshing profiles: %s" % e)
		self.profilesListBox.SetSelection(0)
		self.onSelectProfile(None)

	def onSelectProfile(self, event):
		sel_idx = self.profilesListBox.GetSelection()
		is_custom = bool(sel_idx != wx.NOT_FOUND and sel_idx > 0)
		self.deleteBtn.Enable(is_custom)
		self.renameBtn.Enable(is_custom)

	def onNewProfile(self, event):
		dlg = NewProfileDialog(self)
		if dlg.ShowModal() == wx.ID_OK:
			app_name, disp_name = dlg.get_selected_app()
			dlg.Destroy()
			if app_name:
				editDlg = SoundProfileSettingsDialog(self, profile_name=app_name)
				if editDlg.ShowModal() == wx.ID_OK:
					rename_profile(app_name, disp_name)
					self.refreshProfiles()
					for i in range(self.profilesListBox.GetCount()):
						if self.profilesListBox.GetClientData(i) == app_name:
							self.profilesListBox.SetSelection(i)
							self.onSelectProfile(None)
							break
				editDlg.Destroy()
		else:
			dlg.Destroy()

	def onEditProfile(self, event):
		sel_idx = self.profilesListBox.GetSelection()
		if sel_idx == wx.NOT_FOUND:
			return
		app_name = self.profilesListBox.GetClientData(sel_idx)
		if not app_name:
			return
		dlg = SoundProfileSettingsDialog(self, profile_name=app_name)
		if dlg.ShowModal() == wx.ID_OK:
			self.refreshProfiles()
		dlg.Destroy()

	def onRenameProfile(self, event):
		sel_idx = self.profilesListBox.GetSelection()
		if sel_idx == wx.NOT_FOUND or sel_idx == 0:
			return
		app_name = self.profilesListBox.GetClientData(sel_idx)
		curr_disp = self.profilesListBox.GetString(sel_idx)
		dlg = wx.TextEntryDialog(
			self,
			_("Enter new name for profile '{app}':").format(app=app_name),
			_("Rename Profile"),
			value=curr_disp
		)
		if dlg.ShowModal() == wx.ID_OK:
			new_disp = dlg.GetValue().strip()
			if new_disp:
				rename_profile(app_name, new_disp)
				self.refreshProfiles()
				for i in range(self.profilesListBox.GetCount()):
					if self.profilesListBox.GetClientData(i) == app_name:
						self.profilesListBox.SetSelection(i)
						self.onSelectProfile(None)
						break
		dlg.Destroy()

	def onDeleteProfile(self, event):
		sel_idx = self.profilesListBox.GetSelection()
		if sel_idx == wx.NOT_FOUND or sel_idx == 0:
			return
		app_name = self.profilesListBox.GetClientData(sel_idx)
		disp_name = self.profilesListBox.GetString(sel_idx)
		if gui.messageBox(
			_("Are you sure you want to delete sound profile '{name}'?").format(name=disp_name),
			_("Confirm Delete"),
			wx.YES_NO | wx.ICON_QUESTION,
			self
		) == wx.YES:
			delete_profile(app_name)
			self.refreshProfiles()

def get_target_settings_profile():
	app = getattr(GlobalPlugin, "last_active_app", "default")
	if app and app != "default":
		ini_path = get_app_profile_path(app)
		if os.path.isfile(ini_path):
			return app
	return "default"

class TypingSettingsPanel(SettingsPanel):
	title = _("Typing SFX")
	supportedInProfile = True

	@classmethod
	def isSupportedInProfile(cls, profile=None):
		return True

	def makeSettings(self, settingsSizer):
		self.target_profile = get_target_settings_profile()
		cfg = load_profile(self.target_profile)
		self.hidden_controls = []
		self.num_hidden_controls = []
		sHelper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)

		if self.target_profile == "default":
			sHelper.addItem(wx.StaticText(self, label=_("Changes made here will be saved to the Default profile.")))
		else:
			sHelper.addItem(wx.StaticText(self, label=_("Changes made here will be saved to profile: {profile}").format(profile=self.target_profile)))

		sHelper.addItem(wx.StaticText(self, label=_("Typing Sound Mode:")))
		self.playTypingSounds = sHelper.addItem(wx.Choice(self, choices=[_("Off"), _("On")]))
		self.playTypingSounds.SetSelection(1 if cfg.get("typingsnd", True) else 0)

		self.tlable = sHelper.addItem(wx.StaticText(self, label=_("Typing Sound Pack:")))
		self.hidden_controls.append(self.tlable)
		self.typingSound = sHelper.addItem(wx.Choice(self))
		self.hidden_controls.append(self.typingSound)
		sounds = get_sounds_folders()
		self.typingSound.Set(sounds)
		current_sound = str(cfg.get("typing_sound", ""))
		if current_sound in sounds:
			self.typingSound.SetStringSelection(current_sound)
		elif sounds:
			self.typingSound.SetSelection(0)

		self.slable = sHelper.addItem(wx.StaticText(self, label=_("sounds")))
		self.hidden_controls.append(self.slable)
		self.sounds = sHelper.addItem(wx.Choice(self))
		self.hidden_controls.append(self.sounds)

		sHelper.addItem(wx.StaticText(self, label=_("Number sound mode:")))
		self.num_sound_mode_choice = sHelper.addItem(wx.Choice(self, choices=[_("Off"), _("On"), _("On with speech")]))
		try:
			self.num_sound_mode_choice.SetSelection(int(cfg.get("num_sound_mode", 1)))
		except Exception:
			self.num_sound_mode_choice.SetSelection(1)

		self.num_speak_on_protected_label = sHelper.addItem(wx.StaticText(self, label=_("Play number sounds in protected fields:")))
		self.num_hidden_controls.append(self.num_speak_on_protected_label)
		self.num_speak_on_protected_choice = sHelper.addItem(wx.Choice(self, choices=[_("Off"), _("On"), _("On with speech")]))
		self.num_hidden_controls.append(self.num_speak_on_protected_choice)
		try:
			self.num_speak_on_protected_choice.SetSelection(int(cfg.get("num_speak_on_protected", 1)))
		except Exception:
			self.num_speak_on_protected_choice.SetSelection(1)

		self.num_sound_pack_label = sHelper.addItem(wx.StaticText(self, label=_("Number Sound Pack:")))
		self.num_hidden_controls.append(self.num_sound_pack_label)
		num_packs = get_number_sound_packs()
		self.num_sound_pack_choice = sHelper.addItem(wx.Choice(self, choices=num_packs))
		self.num_hidden_controls.append(self.num_sound_pack_choice)
		current_num_pack = str(cfg.get("num_sound_pack", ""))
		if current_num_pack in num_packs:
			self.num_sound_pack_choice.SetStringSelection(current_num_pack)
		elif num_packs:
			self.num_sound_pack_choice.SetSelection(0)

		self.num_sounds_label = sHelper.addItem(wx.StaticText(self, label=_("Number sounds:")))
		self.num_hidden_controls.append(self.num_sounds_label)
		self.num_sounds_choice = sHelper.addItem(wx.Choice(self))
		self.num_hidden_controls.append(self.num_sounds_choice)

		sHelper.addItem(wx.StaticText(self, label=_("Speak passwords:")))
		self.speakPasswords = sHelper.addItem(wx.Choice(self, choices=[_("Off"), _("On")]))
		self.speakPasswords.SetSelection(1 if cfg.get("speak_on_protected", True) else 0)

		self.protected_symbol_label = sHelper.addItem(wx.StaticText(self, label=_("Custom protected field text (leave blank for default):")))
		self.protectedSymbolText = sHelper.addItem(wx.TextCtrl(self, value=str(cfg.get("protected_symbol", ""))))

		self.OnChangeTypingSounds(None)
		self.onChange(None)
		self.onNumPackChange(None)
		self.OnNumSoundModeChange(None)
		self.OnChangeSpeakPasswords(None)
		self.playTypingSounds.Bind(wx.EVT_CHOICE, self.OnChangeTypingSounds)
		self.typingSound.Bind(wx.EVT_CHOICE, self.onChange)
		self.sounds.Bind(wx.EVT_CHOICE, self.onPlay)
		self.num_sound_mode_choice.Bind(wx.EVT_CHOICE, self.OnNumSoundModeChange)
		self.num_sound_pack_choice.Bind(wx.EVT_CHOICE, self.onNumPackChange)
		self.num_sounds_choice.Bind(wx.EVT_CHOICE, self.onNumSoundPlay)
		self.speakPasswords.Bind(wx.EVT_CHOICE, self.OnChangeSpeakPasswords)

	def postInit(self):
		self.playTypingSounds.SetFocus()

	def OnChangeSpeakPasswords(self, evt):
		is_speak_off = self.speakPasswords.GetSelection() == 0
		self.protected_symbol_label.Enable(is_speak_off)
		self.protectedSymbolText.Enable(is_speak_off)

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
		except Exception:
			pass

	def onNumPackChange(self, event):
		sounds = get_number_sounds(self.num_sound_pack_choice.GetStringSelection())
		self.num_sounds_choice.Set(sounds)
		try:
			self.num_sounds_choice.SetSelection(0)
		except Exception:
			pass

	def onNumSoundPlay(self, event):
		sound_sel = self.num_sounds_choice.GetStringSelection()
		pack_sel = self.num_sound_pack_choice.GetStringSelection()
		if sound_sel and pack_sel:
			nvwave.playWaveFile(os.path.join(numbering_dir, pack_sel, sound_sel), True)

	def onPlay(self, event):
		sound_sel = self.sounds.GetStringSelection()
		pack_sel = self.typingSound.GetStringSelection()
		if sound_sel and pack_sel:
			nvwave.playWaveFile(os.path.join(effects_dir, pack_sel, sound_sel), True)

	def onSave(self):
		cfg_data = {
			"typing_sound": self.typingSound.GetStringSelection(),
			"speak_on_protected": (self.speakPasswords.GetSelection() == 1),
			"protected_symbol": self.protectedSymbolText.GetValue().strip(),
			"typingsnd": (self.playTypingSounds.GetSelection() == 1),
			"num_sound_mode": self.num_sound_mode_choice.GetSelection(),
			"num_speak_on_protected": self.num_speak_on_protected_choice.GetSelection(),
			"num_sound_pack": self.num_sound_pack_choice.GetStringSelection()
		}
		target = getattr(self, "target_profile", "default")
		save_profile(target, cfg_data)

class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	last_active_app = "default"

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		NVDASettingsDialog.categoryClasses.append(TypingSettingsPanel)
		self.number_sounds = {}
		self.current_number_pack = None
		self.typing_sounds = {}
		self.current_typing_pack = None
		self._last_played_sound = {}
		self.toolsMenuItem = None

		try:
			self.toolsMenuItem = mainFrame.sysTrayIcon.toolsMenu.Append(
				wx.ID_ANY,
				_("Typing SFX Profiles(&T)..."),
				_("Manage per-application sound profiles for Typing SFX")
			)
			mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.onManageSoundConfigurations, id=self.toolsMenuItem.GetId())
		except Exception as e:
			logHandler.log.exception("Error adding Typing SFX tools menu item: %s" % e)

		hook_speech()

	@script(
		description=_("Opens the Typing SFX Profiles dialog."),
		category=_("Typing SFX"),
		gesture="kb:nvda+shift+c"
	)
	def script_manageSoundConfigurations(self, gesture):
		wx.CallAfter(self._openManageSoundConfigurations)

	def onManageSoundConfigurations(self, evt):
		wx.CallAfter(self._openManageSoundConfigurations)

	def _openManageSoundConfigurations(self):
		try:
			gui.mainFrame.prePopup()
			dlg = ManageSoundConfigurationsDialog(gui.mainFrame)
			dlg.ShowModal()
			dlg.Destroy()
			gui.mainFrame.postPopup()
		except Exception as e:
			logHandler.log.exception("Error opening Typing SFX Profiles dialog: %s" % e)

	def load_number_sounds(self, pack_name):
		if self.current_number_pack == pack_name:
			return
		self.current_number_pack = pack_name
		self.number_sounds.clear()
		path = os.path.join(numbering_dir, pack_name)
		if os.path.isdir(path):
			for i in range(10):
				if os.path.exists(os.path.join(path, f"{i}.wav")):
					self.number_sounds[str(i)] = os.path.join(path, f"{i}.wav")
			if os.path.exists(os.path.join(path, "Numbering.wav")):
				self.number_sounds["default"] = os.path.join(path, "Numbering.wav")

	def load_typing_sounds(self, pack_name):
		if self.current_typing_pack == pack_name and self.typing_sounds:
			return
		self.current_typing_pack = pack_name
		self.typing_sounds = {
			"space": [],
			"delete": [],
			"return": [],
			"letter": [],
			"number": [],
			"typing": [],
		}
		path = os.path.join(effects_dir, pack_name)
		if not os.path.isdir(path):
			return
		try:
			files = sorted(os.listdir(path))
		except Exception:
			return
		all_wavs = []
		for f in files:
			if not f.lower().endswith(".wav"):
				continue
			full_path = os.path.join(path, f)
			if not os.path.isfile(full_path):
				continue
			all_wavs.append(full_path)
			stem = f[:-4].lower().strip()
			if stem.startswith("space") or "spaceba" in stem or "spacebar" in stem:
				self.typing_sounds["space"].append(full_path)
			elif stem.startswith("delete") or stem.startswith("backspace") or stem in ("del", "bs"):
				self.typing_sounds["delete"].append(full_path)
			elif stem.startswith("return") or stem.startswith("enter") or stem in ("bill", "bell", "cr"):
				self.typing_sounds["return"].append(full_path)
			elif stem.startswith("letter"):
				self.typing_sounds["letter"].append(full_path)
			elif stem.startswith("number") or stem.startswith("digit"):
				self.typing_sounds["number"].append(full_path)
			else:
				self.typing_sounds["typing"].append(full_path)
		if not self.typing_sounds["typing"]:
			if self.typing_sounds["letter"]:
				self.typing_sounds["typing"] = list(self.typing_sounds["letter"])
			elif all_wavs:
				self.typing_sounds["typing"] = list(all_wavs)

	def _pick_sound(self, category):
		candidates = self.typing_sounds.get(category)
		if not candidates:
			candidates = self.typing_sounds.get("typing", [])
		if not candidates:
			return None
		if len(candidates) == 1:
			return candidates[0]
		last = self._last_played_sound.get(category)
		pool = [s for s in candidates if s != last]
		chosen = random.choice(pool if pool else candidates)
		self._last_played_sound[category] = chosen
		return chosen

	def _get_typing_sound_for_char(self, ch):
		if ch == " ":
			return self._pick_sound("space")
		elif ch in ("\b", "\u007f"):
			return self._pick_sound("delete")
		elif ord(ch) == 13 or ch == "\n":
			if self.typing_sounds.get("return"):
				return self._pick_sound("return")
			return self._pick_sound("typing")
		elif ch.isdigit() and self.typing_sounds.get("number"):
			return self._pick_sound("number")
		elif ch.isalpha() and self.typing_sounds.get("letter"):
			return self._pick_sound("letter")
		return self._pick_sound("typing")

	def IsEditable(self, object):
		if not object:
			return False
		try:
			if hasattr(object, 'isEditable') and object.isEditable:
				return True
			if hasattr(controlTypes, 'Role') and hasattr(controlTypes.Role, 'TERMINAL') and object.role == controlTypes.Role.TERMINAL:
				return True
			if hasattr(controlTypes, 'ROLE_TERMINAL') and object.role == controlTypes.ROLE_TERMINAL:
				return True
		except Exception:
			pass
		return (object.role in controls or STATE_EDITABLE in object.states) and not STATE_READONLY in object.states

	def AcceptsTabCharacter(self, obj, focus=None):
		target = focus or obj
		if not target:
			return False

		if getattr(target, 'isProtected', False) or (obj and getattr(obj, 'isProtected', False)):
			return False
		states = getattr(target, 'states', set())
		if hasattr(controlTypes, 'State'):
			if hasattr(controlTypes.State, 'PROTECTED') and controlTypes.State.PROTECTED in states:
				return False
		if hasattr(controlTypes, 'STATE_PROTECTED') and controlTypes.STATE_PROTECTED in states:
			return False

		app_name = ""
		for o in (target, obj, focus):
			if o and hasattr(o, 'appModule') and o.appModule and hasattr(o.appModule, 'appName'):
				app_name = str(o.appModule.appName).lower().replace(".exe", "").strip()
				if app_name:
					break

		non_tab_apps = {
			"chrome", "msedge", "firefox", "brave", "opera", "vivaldi", "waterfox",
			"whatsapp", "telegram", "discord", "slack", "teams", "skype"
		}
		if app_name in non_tab_apps:
			w_class = str(getattr(target, 'windowClassName', '') or '')
			role = getattr(target, 'role', None)
			is_terminal = False
			if hasattr(controlTypes, 'Role') and hasattr(controlTypes.Role, 'TERMINAL') and role == controlTypes.Role.TERMINAL:
				is_terminal = True
			if hasattr(controlTypes, 'ROLE_TERMINAL') and role == controlTypes.ROLE_TERMINAL:
				is_terminal = True
			if not is_terminal and "Scintilla" not in w_class:
				return False

		tab_editor_apps = {
			"notepad", "winword", "wordpad", "code", "devenv", "notepad++", "sublime_text",
			"idea64", "pycharm64", "clion64", "webstorm64", "rider64", "studio64", "datagrip64",
			"goland64", "rubymine64", "phpstorm64", "eclipse", "soffice.bin", "textpad",
			"ultraedit", "geany", "notepad2", "notepad3", "cmd", "powershell",
			"windowsterminal", "mintty", "conhost", "bash"
		}
		if app_name in tab_editor_apps:
			return self.IsEditable(target)

		w_class = str(getattr(target, 'windowClassName', '') or '')
		if "Scintilla" in w_class:
			return self.IsEditable(target)

		hwnd = getattr(target, 'windowHandle', None) or (obj and getattr(obj, 'windowHandle', None))
		if hwnd:
			try:
				dlg_code = ctypes.windll.user32.SendMessageW(hwnd, 0x0087, 0x09, 0)
				if dlg_code & 0x0002:
					return self.IsEditable(target)
			except Exception:
				pass

		role = getattr(target, 'role', None)
		if hasattr(controlTypes, 'Role') and hasattr(controlTypes.Role, 'TERMINAL') and role == controlTypes.Role.TERMINAL:
			return self.IsEditable(target)
		if hasattr(controlTypes, 'ROLE_TERMINAL') and role == controlTypes.ROLE_TERMINAL:
			return self.IsEditable(target)

		return False

	def event_gainFocus(self, object, nextHandler):
		global _cached_speak_on_protected
		api.isTypingProtected = IsTypingProtected
		if object and hasattr(object, 'appModule') and object.appModule:
			app = str(object.appModule.appName).lower().replace(".exe", "").strip()
			if app and app != "nvda":
				GlobalPlugin.last_active_app = app
		try:
			app_name = object.appModule.appName if object and hasattr(object, 'appModule') and object.appModule else None
			cfg = get_effective_config(app_name)
			_cached_speak_on_protected = bool(cfg.get("speak_on_protected", True))
		except Exception:
			_cached_speak_on_protected = True
		nextHandler()

	def event_typedCharacter(self, obj, nextHandler, ch):
		if not ch or ch == "\x1b" or (len(ch) == 1 and ord(ch) == 27):
			nextHandler()
			return

		focus = api.getFocusObject()
		is_protected = bool((focus and getattr(focus, 'isProtected', False)) or (obj and getattr(obj, 'isProtected', False)))

		if ch == "\t" or (len(ch) == 1 and ord(ch) == 9):
			if not self.AcceptsTabCharacter(obj, focus):
				nextHandler()
				return

		try:
			self._speakWholeWord(obj, ch)
		except Exception:
			logHandler.log.debugWarning("wholeWordEcho: failed to speak whole word", exc_info=True)

		app_name = obj.appModule.appName if obj and hasattr(obj, 'appModule') and obj.appModule else None
		cfg = get_effective_config(app_name)

		self.load_number_sounds(cfg["num_sound_pack"])

		custom_sym = cfg.get("protected_symbol", "").strip() if not cfg["speak_on_protected"] else ""

		num_sound_mode = cfg["num_sound_mode"]
		num_played = False
		if num_sound_mode != 0:
			num_speak_on_protected = cfg["num_speak_on_protected"]
			mode = num_sound_mode
			if is_protected:
				mode = num_speak_on_protected
			if mode != 0 and self.IsEditable(focus or obj) and ch.isdigit():
				sound_path = self.number_sounds.get(ch)
				if not sound_path:
					sound_path = self.number_sounds.get("default")
				if sound_path:
					nvwave.playWaveFile(sound_path, True)
					num_played = True
					if mode == 1:
						_suppress_digit_info["char"] = ch
						_suppress_digit_info["time"] = time.time()
						speech.cancelSpeech()
						_append_to_typed_word_buffer(ch)
						return
					elif mode == 2:
						if is_protected and custom_sym:
							speech.cancelSpeech()
							speech.speakText(custom_sym)
							return
						nextHandler()
						return

		if is_protected and custom_sym and ch not in ("\b", "\r", "\n", "\t", "\x1b"):
			if self.IsEditable(obj) and cfg["typingsnd"] and not num_played:
				self.load_typing_sounds(cfg["typing_sound"])
				sound_to_play = self._get_typing_sound_for_char(ch)
				if sound_to_play and os.path.isfile(sound_to_play):
					nvwave.playWaveFile(sound_to_play, True)
			speech.cancelSpeech()
			speech.speakText(custom_sym)
			return

		if self.IsEditable(obj) and cfg["typingsnd"] and not num_played:
			self.load_typing_sounds(cfg["typing_sound"])
			sound_to_play = self._get_typing_sound_for_char(ch)
			if sound_to_play and os.path.isfile(sound_to_play):
				nvwave.playWaveFile(sound_to_play, True)
		nextHandler()

	def _speakWholeWord(self, obj, ch: str) -> None:
		if not ch or ch in ("\b", "\u007f", "\x1b") or (len(ch) == 1 and ord(ch) == 27) or _isWordChar(ch):
			return
		if api.isTypingProtected():
			return
		buf = _getTypedWordBuffer()
		if not buf:
			return
		if not _isTypedWordEchoEnabled():
			return
		bufferedWord = "".join(buf)
		word = self._getWordBeforeCaret(obj)
		if not word or word == bufferedWord:
			return
		if len(word) > 100:
			return
		if not word.endswith(bufferedWord):
			return
		speech.clearTypedWordBuffer()
		speech.speakText(word)

	def _getWordBeforeCaret(self, obj) -> str:
		if obj is None:
			obj = api.getFocusObject()
		if not obj:
			return ""
		try:
			caret = obj.makeTextInfo(textInfos.POSITION_CARET)
		except Exception:
			try:
				caret = obj.makeTextInfo(textInfos.POSITION_SELECTION)
			except Exception:
				caret = None
		if not caret:
			return ""
		try:
			lineStart = caret.copy()
			lineStart.expand(textInfos.UNIT_LINE)
			textBeforeCaret = caret.copy()
			textBeforeCaret.setEndPoint(lineStart, "startToStart")
			text = textBeforeCaret.text or ""
			word = _trailingWord(text)
			if word:
				return word
		except Exception:
			pass
		return ""

	@script(description=_("Toggles the typing sounds mode."), category=_("Typing SFX"), gestures=["kb:nvda+shift+k"])
	def script_toggle_typing_sounds(self, gesture):
		target_profile = get_active_profile_name()
		cfg = load_profile(target_profile)
		current = cfg["typingsnd"]
		new_val = not current
		save_profile(target_profile, {"typingsnd": new_val})
		message(_("typing sounds off") if not new_val else _("typing sounds on"))

	@script(description=_("Toggles the Number sounds mode."), category=_("Typing SFX"), gesture="kb:nvda+shift+n")
	def script_toggleNumSounds(self, gesture):
		target_profile = get_active_profile_name()
		cfg = load_profile(target_profile)
		try:
			num_sound_mode = int(cfg["num_sound_mode"])
		except Exception:
			num_sound_mode = 1
		num_sound_mode = (num_sound_mode + 1) % 3
		save_profile(target_profile, {"num_sound_mode": num_sound_mode})
		if num_sound_mode == 0:
			message(_("Number sound off"))
		elif num_sound_mode == 1:
			message(_("Number sound on"))
		else:
			message(_("Number sound on with speech"))

	@script(description=_("Toggles the protected sounds mode."), category=_("Typing SFX"), gesture="kb:nvda+shift+o")
	def script_toggleNumProtectedSounds(self, gesture):
		target_profile = get_active_profile_name()
		cfg = load_profile(target_profile)
		try:
			num_sound_mode = int(cfg["num_sound_mode"])
		except Exception:
			num_sound_mode = 1
		if num_sound_mode == 0:
			message(_("please enable the number sound first"))
			return
		try:
			num_speak_on_protected = int(cfg["num_speak_on_protected"])
		except Exception:
			num_speak_on_protected = 1
		num_speak_on_protected = (num_speak_on_protected + 1) % 3
		save_profile(target_profile, {"num_speak_on_protected": num_speak_on_protected})
		if num_speak_on_protected == 0:
			message(_("Protected number sound off"))
		elif num_speak_on_protected == 1:
			message(_("Protected number sound on"))
		else:
			message(_("Protected number sound on with speech"))

	@script(description=_("Toggles the protected Speak mode."), category=_("Typing SFX"), gestures=["kb:nvda+shift+p"])
	def script_toggle_speak_passwords(self, gesture):
		global _cached_speak_on_protected
		target_profile = get_active_profile_name()
		cfg = load_profile(target_profile)
		current = cfg["speak_on_protected"]
		new_val = not current
		save_profile(target_profile, {"speak_on_protected": new_val})
		_cached_speak_on_protected = new_val
		message(_("speak passwords off") if not new_val else _("speak passwords on"))

	def terminate(self):
		RestoreTypingProtected()
		unhook_speech()
		if self.toolsMenuItem:
			try:
				mainFrame.sysTrayIcon.toolsMenu.Remove(self.toolsMenuItem)
			except Exception:
				pass
		try:
			NVDASettingsDialog.categoryClasses.remove(TypingSettingsPanel)
		except ValueError:
			pass
