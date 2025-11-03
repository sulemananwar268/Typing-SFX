import addonHandler
import wx
import os
import shutil
from ui import message as m
from nvwave import playWaveFile as playsound
from random import randint

addonHandler.initTranslation()

effects_dir_typing = os.path.join(os.path.abspath(os.path.dirname(__file__)), "effects", "Typing")
effects_dir_numbering = os.path.join(os.path.abspath(os.path.dirname(__file__)), "effects", "numbering")

class NewPack(wx.Dialog):
	def __init__(self, parent, is_number_pack=False):
		self.is_number_pack = is_number_pack
		self.effects_dir = effects_dir_numbering if self.is_number_pack else effects_dir_typing

		self.name = wx.GetTextFromUser(_("enter the new soundpack name"), _("soundpack name"))
		if not self.name: return self.Destroy()
		if os.path.isdir(os.path.join(self.effects_dir, self.name)):
			return wx.MessageBox(_("This soundpack name already exists, please choose another one."), _("soundpack exists"), style=wx.ICON_ERROR)
		super().__init__(parent, -1, _("Create a new soundpack"))
		p = wx.Panel(self)
		if self.is_number_pack:
			slist = [f"{i}:: {_('no sound')}" for i in range(10)]
		else:
			slist = [_("back space:: ")+_("no sound"), _("space:: ")+_(" no sound"), _("return key:: ")+_("no sound"), _("typing sound:: ")+_("no sound")]
		wx.StaticText(p, -1, _("sounds list"))
		self.soundsList = wx.ListBox(p, -1, choices=slist)
		ok = wx.Button(p, -1, _("create"))
		cancel = wx.Button(p, wx.ID_CANCEL, _("cancel"))
		self.soundsList.Selection = 0
		ok.Bind(wx.EVT_BUTTON, self.OnOk)
		self.Bind(wx.EVT_MENU, self.OnList)
		self.Bind(wx.EVT_CHAR_HOOK, self.OnShortcuts)
		self.Show()

	def OnOk(self, event):
		files = []
		for i in self.soundsList.Strings:
			i = i.split("::")[1].strip()
			files.append(i)
		try:
			os.mkdir(os.path.join(self.effects_dir, self.name))
			if self.is_number_pack:
				for i, file in enumerate(files):
					if os.path.exists(file):
						shutil.copy(file, os.path.join(self.effects_dir, self.name, f"{i}.wav"))
			else:
				for file in files:
					shutil.copy(file, os.path.join(self.effects_dir, self.name, self.get_name(files.index(file))))
				index = 0
				if self.soundsList.Strings[-1].count(" :: ")>1:
					for file in self.soundsList.Strings[-1].split(" :: "):
						try:
							shutil.copy(file, os.path.join(self.effects_dir, self.name, f"typing_{index}.wav"))
						except:pass
						index +=1
				else:
					try:
						file = self.soundsList.Strings[-1].split(" :: ")[1]
						shutil.copy(file, os.path.join(self.effects_dir, self.name, f"typing.wav"))
					except Exception as e:
						m(str(e))
			wx.MessageBox(_("soundpack created successfully"), _("success"))
			self.Destroy()
		except Exception as e:
			return m(str(e))

	def get_name(self, index):
		if index == 0:
			return "delete.wav"
		elif index == 1:
			return "space.wav"
		elif index ==2:
			return "return.wav"
		else:
			return 0

	def OnShortcuts(self, event):
		key = event.GetKeyCode()
		if key == wx.WXK_SPACE and self.FindFocus() == self.soundsList:
			try:
				if len(self.soundsList.StringSelection.split(":: "))>2:
					snd = self.soundsList.StringSelection.split(":: ")[randint(2, len(self.soundsList.StringSelection.split(":: ")))-1]
					m(str(self.soundsList.StringSelection.split(":: ").index(snd)))
				else:
					snd = self.soundsList.StringSelection.split(":: ")[1]
				playsound(snd, True)
			except Exception as e: m(str(e))
		event.Skip()

	def OnList(self, event):
		if not self.FindFocus() == self.soundsList: return
		path = wx.FileSelector(_("select sound"), wildcard=_("wav file(.wav)|*.wav"), parent = self)
		if not path: return
		if not self.is_number_pack and self.soundsList.Selection == 3:
			if not " :: " in self.soundsList.StringSelection:
				sound = self.soundsList.StringSelection.split("::")[0]+" :: "+path
			else:
				sound = self.soundsList.StringSelection+" :: "+path
		else:
			sound = self.soundsList.StringSelection.split("::")[0]+":: "+path
		index = self.soundsList.Selection
		self.soundsList.Delete(index)
		self.soundsList.Insert(sound, index)
		self.soundsList.Selection = index