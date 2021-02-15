#!/usr/bin/python
import pulsectl
import tdb
import os
import sys
import gi
import struct
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GObject

pulse = pulsectl.Pulse('restore_manip')
currently_selected_map = 'sink-input-by-media-role'
restore_map = {}

# This covers the stream maps, not the devices volume restoration information.
# It would be good to add these too
# However, currently it is not possible to check these values or update it
# There is nothing in the native protocol extension that allows this similar to;
# inspire by: https://gitlab.freedesktop.org/pulseaudio/pulseaudio/-/blob/master/src/pulse/ext-stream-restore.c#L156
# Here it only allows editing the device formats
# https://gitlab.freedesktop.org/pulseaudio/pulseaudio/-/blob/master/src/pulse/ext-device-restore.c#L233
# What can be done instead is manipulate the TDB directly
# interpreting the format manually
# Structure: https://gitlab.freedesktop.org/pulseaudio/pulseaudio/-/blob/master/src/modules/module-device-restore.c#L363
# The list of tags is found here:
# https://gitlab.freedesktop.org/pulseaudio/pulseaudio/-/blob/master/src/pulsecore/tagstruct.h
# Helper methods:
# https://gitlab.freedesktop.org/pulseaudio/pulseaudio/-/blob/master/src/pulsecore/tagstruct.c
machine_id = open('/etc/machine-id','r').read().rstrip()
device_volumes_db = os.environ['HOME']+'/.config/pulse/'+machine_id+'-device-volumes.tdb'
db = tdb.open(device_volumes_db)


# Examples:
# version 1 - volume not valid (skip rest)
# 42 01 30 4e
#  x = db.get(b'sink:alsa_output.usb-C-Media_Electronics_Inc._Microsoft_LifeChat_LX-3000-00.iec958-stereo:iec958-stereo-output')
# bytes(x).hex()
# version 1 - volume valid yes - channel map 'm' - volume 'v' - muted valid yes - muted no - number of format 1
# format: tag format 'f' - encoding 01 - proplist 'P' - value
# '4201 31 6d020102 760200004a3d00004a3d 31 30 4201
# 66 4201 504e'
# mapping of device with port
# '4201 31 746d756c74696368616e6e656c2d696e70757400')

class per_port_entry():
	PA_VOLUME_NORM = 0x10000
	def __init__(self, name, binary):
		parts = name.split(":")
		self.type = parts[0]
		self.name = parts[1]
		first_colon_loc = name.find(":")
		self.full_name = name[first_colon_loc+1:]
		self.port = parts[2] if len(parts) >= 3 else None
		self.binary = binary
		self.hex = self.binary.hex()
		self.is_valid = False
		self.is_port_format = False
		self.decode()

	def decode(self):
		actions = [self.parse_version,
			self.parse_volume_valid,
			self.parse_channel_map,
			self.parse_volume,
			self.parse_muted_valid,
			self.parse_muted,
			self.parse_number_of_formats,
			self.parse_formats]

		if chr(self.binary[3]) == 't' or  chr(self.binary[3]) == 'N':
			self.is_port_format = True
			actions = [self.parse_version,
				self.parse_port_valid,
				self.parse_port]

		for action in actions:
			if action() < 0:
				return
		self.is_valid = True

	def encode(self):
		output = bytearray()
		if self.is_port_format:
			output.append(0x42)
			output.append(self.version)
			output.append(self.set_bool(self.port_valid))
			if self.port_valid:
				output.append(0x74)
				for i in self.port.encode():
					output.append(i)
				output.append(0x00)
			else:
				output.append(0x4e)
		else:
			output.append(0x42)
			output.append(self.version)
			output.append(self.set_bool(self.volume_valid))
			output.append(0x6d)
			output.append(self.channel_map['channels'])
			for i in self.channel_map['map']:
				output.append(i)
			output.append(0x76)
			output.append(self.volume['channels'])
			for i in self.volume['values']:
				v = int(i * self.PA_VOLUME_NORM)
				output += struct.pack(">I", v)
			output.append(self.set_bool(self.muted_valid))
			output.append(self.set_bool(self.muted))
			output.append(0x42)
			output.append(self.number_of_formats)
			for i in self.formats:
				output.append(0x66)
				output.append(0x42)
				output.append(i['encoding'])
				output.append(0x50)
				# ignore the rest of the format for now
				output.append(0x4e)
		return output

	def get_u8(self):
		if chr(self.binary[0]) != 'B':
			return (-1, None)
		result = self.binary[1]
		self.binary = self.binary[2:]
		return (1, result)

	def get_bool(self):
		if chr(self.binary[0]) == '1':
			result = True
		elif chr(self.binary[0]) == '0':
			result = False
		else:
			return (-1, None)
		self.binary = self.binary[1:]
		return (1, result)

	def set_bool(self, val):
		if val:
			return 0x31
		else:
			return 0x30

	def parse_port_valid(self):
		(status, result) = self.get_bool()
		self.port_valid = result
		return status

	def parse_port(self):
		if chr(self.binary[0]) == 'N':
			self.binary = self.binary[1:]
			self.port = None
			return 1

		if chr(self.binary[0]) != 't':
			return -1
		self.binary = self.binary[1:]
		self.port = self.binary[:-1].decode()
		return 1

	def parse_version(self):
		(status, result) = self.get_u8()
		self.version = result
		return status

	def parse_volume_valid(self):
		(status, result) = self.get_bool()
		self.volume_valid = result
		return status

	def parse_channel_map(self):
		if chr(self.binary[0]) != 'm':
			return -1
		self.binary = self.binary[1:]
		channel_map = {}
		channel_map['channels'] = self.binary[0]
		self.binary = self.binary[1:]

		channel_map['map'] = []
		for i in range(channel_map['channels']):
			val = self.binary[0]
			channel_map['map'].append(val)
			self.binary = self.binary[1:]

		self.channel_map = channel_map
		return 1

	def parse_volume(self):
		if chr(self.binary[0]) != 'v':
			return -1
		self.binary = self.binary[1:]
		volume = {}
		volume['channels'] = self.binary[0]
		self.binary = self.binary[1:]

		volume['values'] = []
		for i in range(volume['channels']):
			val = struct.unpack('>I', self.binary[:4])[0]
			val = float(val)/self.PA_VOLUME_NORM
			volume['values'].append(val)
			self.binary = self.binary[4:]
		self.volume = volume
		return 1

	def parse_muted_valid(self):
		(status, result) = self.get_bool()
		self.muted_valid = result
		return status

	def parse_muted(self):
		(status, result) = self.get_bool()
		self.muted = result
		return status

	def parse_number_of_formats(self):
		(status, result) = self.get_u8()
		self.number_of_formats = result
		return status

	def parse_formats(self):
		self.formats = []
		for i in range(self.number_of_formats):
			if self.parse_format() < 0:
				return -1
		return 1

	def parse_format(self):
		new_format = {}
		if chr(self.binary[0]) != 'f':
			return -1
		self.binary = self.binary[1:]

		(status, result) = self.get_u8()
		if status < 0:
			return status
		new_format['encoding'] = result
		new_format['plist'] = {}

		if chr(self.binary[0]) != 'P':
			return -1
		self.binary = self.binary[1:]

		if chr(self.binary[0]) != 'N' and chr(self.binary[0]) != 't':
			return -1

		# 'N'/NULL return
		if chr(self.binary[0]) == 'N':
			self.binary = self.binary[1:]
			self.formats.append(new_format)
			return 1

		self.binary = self.binary[1:]
		# TODO this is mostly unused from what I can see in the DB
		# The only port information that make sense is the one in the name
		# Example: sink:alsa_output.usb-C-Media_Electronics_Inc._Microsoft_LifeChat_LX-3000-00.iec958-stereo:iec958-stereo-output
		# 't'/String, not NULL, continue parsing
		# read string till \0
		# length = self.get_u32
		# get arbitrary of length: PA_TAG_ARBITRARY read_u32(len) which == length?
		# read length len

		return 1

device_map_empty = {
	'source': {},
	'sink': {},
}
per_port_map_empty = {
	'source': {},
	'sink': {},
}
device_map = {}
per_port_map = {}

def refresh_device_map():
	global device_map_empty
	global device_map
	global per_port_map_empty
	global per_port_map

	device_map = device_map_empty
	per_port_map = per_port_map_empty

	for key in db.keys():
		entry = db.get(key)
		ppe = per_port_entry(key.decode(), entry)
		if ppe.is_valid:
			if ppe.is_port_format:
				device_map[ppe.type][ppe.name] = ppe
			else:
				if ppe.name not in per_port_map[ppe.type].keys():
					per_port_map[ppe.type][ppe.name] = {}
				per_port_map[ppe.type][ppe.name][ppe.port] = ppe
		else:
			# TODO should we remove it from the DB?
			pass

refresh_device_map()

# Encoding tests

#for a in device_map['source'].keys():
#	d = device_map['source'][a]
#	print(a)
#	print(d)
#	print(d.hex)
#	print(d.encode().hex())
#	assert(d.hex == d.encode().hex())

#for a in per_port_map['sink'].keys():
#	print(a)
#	d = per_port_map['sink'][a]
#	for p in d.keys():
#		print(p)
#		val = d[p]
#		print(val.hex)
#		print(val.encode().hex())
#		assert(val.hex == val.encode().hex())


# pacmd list-clients to find more information
restore_map_empty = {
	'source-output-by-media-role': {},
	'source-output-by-application-name': {},
	'source-output-by-application-id': {},
	'source-output-by-media-name': {},
	'sink-input-by-media-role': {},
	'sink-input-by-application-name': {},
	'sink-input-by-application-id': {},
	'sink-input-by-media-name': {},
}

def refresh_restore_map():
	global pulse
	global restore_map
	global restore_map_empty
	if not pulse.connected:
		pulse = pulsectl.Pulse('restore_manip')

	restore_db = pulse.stream_restore_read()
	restore_map = restore_map_empty
	for a in range(len(restore_db)):
		association_type = restore_db[a].name.split(":")[0]
		first_colon_loc = restore_db[a].name.find(":")
		name = restore_db[a].name[first_colon_loc+1:]
		restore_map[association_type][name] = restore_db[a]

refresh_restore_map()


class ListBoxRowWithData(Gtk.ListBoxRow):
	def __init__(self, data):
		super(Gtk.ListBoxRow, self).__init__()
		self.data = data
		self.add(Gtk.Label(label=data, xalign=0))

class ListBoxRestorationInfo(Gtk.ListBoxRow):
	__gsignals__ = {
		'refresh': (GObject.SignalFlags.RUN_LAST, GObject.TYPE_NONE, ())
	}
	def __init__(self, restoration_name, restoration_row):
		super(Gtk.ListBoxRow, self).__init__()
		self.restoration_name = restoration_name
		self.restoration_row = restoration_row

		grid = Gtk.Grid()
		grid.set_column_spacing(10)

		label_name = Gtk.Label(label=restoration_name, xalign=0)
		scroll = Gtk.ScrolledWindow(expand=True)
		scroll.add(label_name)
		grid.attach(scroll, 0, 0, 1, 1)

		# TODO do we include channel_map
		text_mute = "off" if restoration_row.mute else "on"
		label_mute = Gtk.Label(label=text_mute, xalign=0)
		scroll = Gtk.ScrolledWindow(expand=True)
		scroll.add(label_mute)
		grid.attach(scroll, 1, 0, 1, 1)

		label_volume = Gtk.Label(label=str(round(restoration_row.volume.value_flat * 100, 2))+"%", xalign=0)
		scroll = Gtk.ScrolledWindow(expand=True)
		scroll.add(label_volume)
		grid.attach(scroll, 2, 0, 1, 1)

		label_device = Gtk.Label(label=str(restoration_row.device), xalign=0)
		scroll = Gtk.ScrolledWindow(expand=True)
		scroll.add(label_device)
		grid.attach(scroll, 3, 0, 1, 1)

		edit_button = Gtk.Button(label="🖊")
		edit_button.connect("clicked", self.on_edit_clicked)
		grid.attach(edit_button, 4, 0, 1, 1)

		delete_button = Gtk.Button(label="🗑")
		delete_button.connect("clicked", self.on_delete_clicked)
		grid.attach(delete_button, 5, 0, 1, 1)

		self.add(grid)

	def on_edit_clicked(self, widget):
		global currently_selected_map
		global pulse
		rule_name = currently_selected_map+":"+self.restoration_name
		dialog = DialogEditRule(self, rule_name, self.restoration_row)
		response = dialog.run()
		if response == Gtk.ResponseType.OK:
			new_volume = float(dialog.volume_entry.get_text())/100.0
			if dialog.device_entry.get_text() != 'None':
				self.restoration_row.device = dialog.device_entry.get_text()
			if self.restoration_row.channel_count == 0 and new_volume > 0.0:
				# default to 2 channels
				self.restoration_row.channel_count = 2
				self.restoration_row.channel_list = ['front-left', 'front-right']
				self.restoration_row.volume = pulsectl.PulseVolumeInfo(struct_or_values=[0.50,0.50], channels=2)
			if new_volume > 0:
				for i in range(len(self.restoration_row.volume.values)):
					self.restoration_row.volume.values[i] = new_volume
			self.restoration_row.mute = 1 if dialog.mute_switch.get_state() else 0
			pulse.stream_restore_write(self.restoration_row, mode='replace')
			self.emit("refresh")
		dialog.destroy()

	def on_delete_clicked(self, widget):
		global currently_selected_map
		global pulse
		rule_name = currently_selected_map+":"+self.restoration_name
		dialog = DialogConfirmDeleteRule(self, rule_name)
		response = dialog.run()

		if response == Gtk.ResponseType.OK:
			pulse.stream_restore_delete(rule_name)
			self.emit("refresh")
		dialog.destroy()

GObject.type_register(ListBoxRestorationInfo)

class DialogEditRule(Gtk.Dialog):
	def __init__(self, parent, rule_name, restoration_row):
		Gtk.Dialog.__init__(self, title="Stream Rule Edit", flags=0)
		self.add_buttons(
			Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK
		)
		self.set_default_size(250, 160)
		label = Gtk.Label(label="Currently Editing:\n"+rule_name)
		a_area = self.get_content_area()
		a_area.add(label)

		box_outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
		a_area.add(box_outer)

		mute_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
		box_outer.add(mute_box)
		self.mute_switch = Gtk.Switch()
		self.mute_switch.set_state(restoration_row.mute == 1)
		mute_box.pack_start(Gtk.Label(label="Muted"), False, True, 0)
		mute_box.pack_start(self.mute_switch, False, True, 0)

		volume_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
		box_outer.add(volume_box)
		self.volume_entry = Gtk.Entry()
		self.volume_entry.set_text(str(restoration_row.volume.value_flat*100))
		volume_box.pack_start(Gtk.Label(label="Flat Volume"), False, True, 0)
		volume_box.pack_start(self.volume_entry, True, True, 0)

		device_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
		box_outer.add(device_box)
		self.device_entry = Gtk.Entry()
		self.device_entry.set_text(str(restoration_row.device))
		device_box.pack_start(Gtk.Label(label="device"), False, True, 0)
		device_box.pack_start(self.device_entry, True, True, 0)

		action_area= self.get_action_area()
		action_area.set_halign(Gtk.Align.CENTER)
		self.show_all()

class DialogConfirmDeleteRule(Gtk.Dialog):
	def __init__(self, parent, rule_name):
		Gtk.Dialog.__init__(self, title="Stream Rule Deletion", flags=0)

		self.add_buttons(
			Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK
		)
		self.set_default_size(150, 100)
		label = Gtk.Label(label="Are you sure you want to delete:\n"+rule_name)
		a_area = self.get_content_area()
		a_area.add(label)
		action_area= self.get_action_area()
		action_area.set_halign(Gtk.Align.CENTER)
		self.show_all()

class DialogNewRoutingRule(Gtk.Dialog):
	def __init__(self, parent):
		Gtk.Dialog.__init__(self, title="New Stream Routing Rule", transient_for=parent, flags=0)
		self.add_buttons(
			Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK
		)
		self.set_default_size(250, 160)
		label = Gtk.Label(label="Enter the information about the new routing rule")
		a_area = self.get_content_area()
		a_area.add(label)

		box_outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
		a_area.add(box_outer)

		type_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
		box_outer.add(type_box)
		self.type_combo = Gtk.ComboBoxText()
		global restore_map_empty
		for rule_type in restore_map_empty.keys():
			self.type_combo.append_text(rule_type)
		type_box.pack_start(Gtk.Label(label="Entry Type"), False, True, 0)
		type_box.pack_start(self.type_combo, True, True, 0)

		name_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
		box_outer.add(name_box)
		self.name_entry = Gtk.Entry()
		self.name_entry.set_text("")
		name_box.pack_start(Gtk.Label(label="Entry Name"), False, True, 0)
		name_box.pack_start(self.name_entry, True, True, 0)

		mute_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
		box_outer.add(mute_box)
		self.mute_switch = Gtk.Switch()
		self.mute_switch.set_state(False)
		mute_box.pack_start(Gtk.Label(label="Muted"), False, True, 0)
		mute_box.pack_start(self.mute_switch, False, True, 0)

		volume_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
		box_outer.add(volume_box)
		self.volume_entry = Gtk.Entry()
		self.volume_entry.set_text("80.0")
		volume_box.pack_start(Gtk.Label(label="Flat Volume"), False, True, 0)
		volume_box.pack_start(self.volume_entry, True, True, 0)

		device_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
		box_outer.add(device_box)
		self.device_entry = Gtk.Entry()
		self.device_entry.set_text("None")
		device_box.pack_start(Gtk.Label(label="device"), False, True, 0)
		device_box.pack_start(self.device_entry, True, True, 0)

		action_area= self.get_action_area()
		action_area.set_halign(Gtk.Align.CENTER)
		self.show_all()


class RestoreDbUI(Gtk.Window):
	def __init__(self):
		Gtk.Window.__init__(self, title="PulseAudio Restoration DB Editor")
		self.set_default_size(950,500)

		box_outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
		self.add(box_outer)

		box_outer.pack_start(Gtk.Label(label="Pulse Audio Restoration DB Editor", xalign=0.5), False, True, 0)

		notebook = Gtk.Notebook()
		box_outer.pack_start(notebook, True, True, 0)

		box_streams = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
		notebook.append_page(box_streams, Gtk.Label(label="Streams Restore Rules"))

		box_devices = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
		notebook.append_page(box_devices, Gtk.Label(label="Device Restore Rules"))

		self.currently_select_map_label = Gtk.Label(label="", xalign=0.5)
		box_streams.pack_start(self.currently_select_map_label, False, True, 0)

		paned = Gtk.Paned()
		paned.set_wide_handle(True)
		paned.set_position(240)
		left_pane_scroll = Gtk.ScrolledWindow()
		paned.pack1(left_pane_scroll, True, False)

		right_pane_scroll = Gtk.ScrolledWindow()
		paned.pack2(right_pane_scroll, True, False)

		box_streams.pack_start(paned, True, True, 10)

		add_new_rule_button = Gtk.Button(label="New Routing Rule")
		add_new_rule_button.connect("clicked", self.on_add_new_rule_clicked)
		box_streams.pack_start(add_new_rule_button, False, False, 10)

		left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
		left_pane_scroll.add(left_box)

		self.right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
		right_pane_scroll.add(self.right_box)

		listbox_sink_input = Gtk.ListBox()
		listbox_sink_input.set_selection_mode(Gtk.SelectionMode.NONE)
		left_box.pack_start(listbox_sink_input, True, True, 0)

		left_separator = Gtk.Separator()
		left_box.pack_start(left_separator, False, True, 0)

		listbox_source_output = Gtk.ListBox()
		listbox_source_output.set_selection_mode(Gtk.SelectionMode.NONE)
		left_box.pack_start(listbox_source_output, True, True, 0)


		self.right_listbox = Gtk.ListBox()
		items = "Sink and Source restoration info".split()
		for item in items:
			self.right_listbox.add(ListBoxRowWithData(item))
		self.right_box.pack_start(self.right_listbox, True, True, 0)

		listbox_sink_input.add(ListBoxRowWithData("sink-input-by-media-role"))
		listbox_sink_input.add(ListBoxRowWithData("sink-input-by-application-name"))
		listbox_sink_input.add(ListBoxRowWithData("sink-input-by-application-id"))
		listbox_sink_input.add(ListBoxRowWithData("sink-input-by-media-name"))
		listbox_sink_input.connect("row-activated", self.restore_db_sub_selection)

		listbox_source_output.add(ListBoxRowWithData("source-output-by-media-role"))
		listbox_source_output.add(ListBoxRowWithData("source-output-by-application-name"))
		listbox_source_output.add(ListBoxRowWithData("source-output-by-application-id"))
		listbox_source_output.add(ListBoxRowWithData("source-output-by-media-name"))
		listbox_source_output.connect("row-activated", self.restore_db_sub_selection)

	def restore_db_sub_selection(self, listbox_widget, row):
		children = self.right_listbox.get_children()
		for child in children:
			self.right_listbox.remove(child)
		self.match_right_pane_to_data(row.data)

	def on_refreshed_listbox(self, listbox_widget):
		global currently_selected_map
		refresh_restore_map()
		children = self.right_listbox.get_children()
		for child in children:
			self.right_listbox.remove(child)
		self.match_right_pane_to_data(currently_selected_map)

	def match_right_pane_to_data(self, selected_map):
		global currently_selected_map
		currently_selected_map = selected_map
		self.currently_select_map_label.set_label(selected_map)
		for key in restore_map[selected_map]:
			resto_info_listbox = ListBoxRestorationInfo(str(key), restore_map[selected_map][key])
			self.right_listbox.add(resto_info_listbox)
			resto_info_listbox.connect("refresh", self.on_refreshed_listbox)

		self.right_listbox.show_all()

	def on_add_new_rule_clicked(self, widget):
		dialog = DialogNewRoutingRule(self)
		response = dialog.run()

		if response == Gtk.ResponseType.OK:
			rule_type = dialog.type_combo.get_active_text()
			rule_name = dialog.name_entry.get_text()
			vol = float(dialog.volume_entry.get_text())/100.0
			device = None if dialog.device_entry.get_text() == "None" else dialog.device_entry.get_text()
			muted = dialog.mute_switch.get_state()
			new_rule = pulsectl.PulseExtStreamRestoreInfo(
					struct_or_name=rule_type+":"+rule_name,
					device=device,
					volume=[vol,vol],
					mute=muted,
					channel_list=['front-left', 'front-right']
			)
			pulse.stream_restore_write(new_rule, mode='replace')
			self.on_refreshed_listbox(None)

		dialog.destroy()

win = RestoreDbUI()
win.connect("destroy", Gtk.main_quit)
win.show_all()
Gtk.main()

