#!/usr/bin/env python3
import pulsectl
import tdb
import os
import sys
import gi
import struct
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GObject
import json

pulse = pulsectl.Pulse('restore_manip')
currently_selected_map = 'sink-input-by-media-role'
currently_selected_device = ''
currently_selected_device_type = ''
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
default_sink = open(os.environ['HOME']+'/.config/pulse/'+machine_id+'-default-sink').read().rstrip()
default_source = open(os.environ['HOME']+'/.config/pulse/'+machine_id+'-default-source').read().rstrip()

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

class per_port_entry(dict):
	PA_VOLUME_NORM = 0x10000
	def __init__(self, name, binary):
		parts = name.split(":")
		self.type = parts[0]
		self.name = parts[1]
		first_colon_loc = name.find(":")
		self.full_name = name[first_colon_loc+1:]
		self.port = parts[2] if len(parts) >= 3 else None
		self.binary = binary
		self.version = 1
		self.hex = self.binary.hex() if self.binary else ''
		self.is_valid = False
		self.is_port_format = False
		self.volume_valid = None
		self.channel_map = {'channels':0, 'map':[]}
		self.volume = {'channels':0, 'values':[]}
		self.muted_valid = None
		self.muted = None
		self.number_of_formats = 1
		self.formats = [{'encoding': 1 }]
		self.port_valid = None
		self.decode()
		dict.__init__(self, type=self.type,
			#name=self.name,
			#full_name=self.full_name,
			port = self.port,
			#hex = self.hex,
			#is_valid = self.is_valid,
			#is_port_format = self.is_port_format,
			version = self.version,
			volume_valid = self.volume_valid,
			channel_map = self.channel_map,
			volume = self.volume,
			muted_valid = self.muted_valid,
			muted = self.muted,
			number_of_formats = self.number_of_formats,
			formats = self.formats,
			port_valid = self.port_valid,
			)

	def decode(self):
		if not self.binary:
			return
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

device_map = {}

#| sink   | default port
#|--------|------------------
#| source | all ports + info
# device_map {
#   'sink': {
#       'devicename': {
#           'default_port': {default port info }
#           'is_default_device': based on default sink/source
#           'ports': {
#               portname: {
#                   { port information }
#                   volume: [0.5,0.5]
#               }
#           }
#       }
#    }
# }
def refresh_device_map():
	global device_map
	global default_sink
	global default_source
	device_map.clear()
	device_map['source'] = {}
	device_map['sink'] = {}

	default_sink = open(os.environ['HOME']+'/.config/pulse/'+machine_id+'-default-sink').read().rstrip()
	default_source = open(os.environ['HOME']+'/.config/pulse/'+machine_id+'-default-source').read().rstrip()

	for key in db.keys():
		entry = db.get(key)
		ppe = per_port_entry(key.decode(), entry)
		if ppe.is_valid:
			if ppe.name not in device_map[ppe.type].keys():
				device_map[ppe.type][ppe.name] = {
					'is_default_device': ppe.name == default_sink or ppe.name == default_source,
					'default_port': None,
					'ports': {}
				}
			if ppe.is_port_format:
				device_map[ppe.type][ppe.name]['default_port'] = ppe
			else:
				device_map[ppe.type][ppe.name]['ports'][ppe.port] = ppe
		else:
			print("\e[0;31mcorrupted entry " + ppe.name + "in restoration DB\e[0;30m")
			pass


# DEBUG
def clean_nones(value):
    """
    Recursively remove all None values from dictionaries and lists, and returns
    the result as a new dictionary or list.
    """
    if isinstance(value, list):
        return [clean_nones(x) for x in value if x is not None]
    elif isinstance(value, dict):
        return {
            key: clean_nones(val)
            for key, val in value.items()
            if val is not None
        }
    else:
        return value

refresh_device_map()
#print(json.dumps(clean_nones(device_map)))
#sys.exit(0)

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
	def __init__(self, data, extra = None):
		super(Gtk.ListBoxRow, self).__init__()
		self.data = data
		label = Gtk.Label(label=data, xalign=0)
		if extra:
			label.set_markup(extra)
		self.add(label)

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
		dialog = DialogConfirmDeleteRule(self, rule_name, "Stream Rule Deletion")
		response = dialog.run()

		if response == Gtk.ResponseType.OK:
			pulse.stream_restore_delete(rule_name)
			self.emit("refresh")
		dialog.destroy()


class ListBoxDevicePortInfo(Gtk.ListBoxRow):
	__gsignals__ = {
		'refresh': (GObject.SignalFlags.RUN_LAST, GObject.TYPE_NONE, ())
	}
	def __init__(self, device_name, device_type, port_name, port_info):
		super(Gtk.ListBoxRow, self).__init__()
		global device_map
		# for now show only muted, volume, nb_channels
		self.device_name = device_name
		self.device_type = device_type
		self.port_name = port_name
		self.port_info = port_info

		grid = Gtk.Grid()
		grid.set_column_spacing(10)
		self.add(grid)

		label_name = Gtk.Label(label=port_name, xalign=0)
		default_port = device_map[device_type][device_name]['default_port']['port'] or 'null'
		if port_name == default_port:
			label_name.set_markup("<b>"+port_name+"</b>")
		scroll = Gtk.ScrolledWindow(expand=True)
		scroll.add(label_name)
		grid.attach(scroll, 0, 0, 1, 1)

		text_mute = "off" if self.port_info.muted else "on"
		label_mute = Gtk.Label(label=text_mute, xalign=0)
		scroll = Gtk.ScrolledWindow(expand=True)
		scroll.add(label_mute)
		grid.attach(scroll, 1, 0, 1, 1)

		volume = 0.0
		if len(self.port_info.volume['values']) > 0:
			volume = round(sum(self.port_info.volume['values'])*100/len(self.port_info.volume['values']), 2)
		label_volume = Gtk.Label(label=str(volume)+"%", xalign=0)
		scroll = Gtk.ScrolledWindow(expand=True)
		scroll.add(label_volume)
		grid.attach(scroll, 2, 0, 1, 1)

		label_channels = Gtk.Label(label="#channels:"+str(self.port_info.channel_map['channels']), xalign=0)
		scroll = Gtk.ScrolledWindow(expand=True)
		scroll.add(label_channels)
		grid.attach(scroll, 3, 0, 1, 1)

		edit_button = Gtk.Button(label="🖊")
		edit_button.connect("clicked", self.edit_port_button_clicked)
		grid.attach(edit_button, 4, 0, 1, 1)

		delete_button = Gtk.Button(label="🗑")
		delete_button.connect("clicked", self.delete_port_button_clicked)
		grid.attach(delete_button, 5, 0, 1, 1)

	def delete_port_button_clicked(self, widget):
		global db
		global device_map
		full_device_name = self.device_type+":"+self.device_name
		dialog = DialogConfirmDeleteRule(self, full_device_name+"\nport => "+self.port_name, "Device Port Rule Deletion")
		response = dialog.run()
		if response == Gtk.ResponseType.OK:
			db.delete((full_device_name+":"+self.port_name).encode())
			self.emit("refresh")
		dialog.destroy()

	def edit_port_button_clicked(self, widget):
		# we can edit mute,volume,channel map?
		global db
		global device_map
		dialog = DialogPortEditRule(self, self.device_type, self.device_name, self.port_name)
		response = dialog.run()
		if response == Gtk.ResponseType.OK:
			channel_map_str = dialog.channel_entry.get_text().rstrip()
			channel_map = []
			if channel_map_str != '':
				channel_map = [int(element) for element in channel_map_str.split(',')]
			port_row = device_map[self.device_type][self.device_name]['ports'][self.port_name]

			port_row.muted_valid = dialog.muted_valid.get_active()
			port_row.muted = dialog.mute_switch.get_state()
			port_row.volume_valid = dialog.volume_valid.get_active()
			port_row.volume['channels'] = len(channel_map)
			port_row.channel_map['channels'] = port_row.volume['channels']
			port_row.channel_map['map'] = channel_map
			vol = float(dialog.volume_entry.get_text())/100.0
			port_row.volume['values'] = [vol for i in range(port_row.volume['channels'])]

			key_of_entry = (self.device_type+":"+self.device_name+":"+self.port_name).encode()
			to_replace = bytes(port_row.encode())
			db.store(key_of_entry, to_replace, tdb.REPLACE)

			self.emit("refresh")
		dialog.destroy()

GObject.type_register(ListBoxRestorationInfo)
GObject.type_register(ListBoxDevicePortInfo)

class DialogPortEditRule(Gtk.Dialog):
	def __init__(self, parent, device_type, device_name, port_name):
		Gtk.Dialog.__init__(self, title="Stream Rule Edit", flags=0)
		self.add_buttons(
			Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK
		)
		self.set_default_size(250, 160)
		rule_name = device_type+":"+device_name
		label = Gtk.Label(label="Rule For Device:\n"+rule_name)

		a_area = self.get_content_area()
		a_area.add(label)
		a_area.pack_start(Gtk.Separator(), False, True, 0)

		box_outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
		a_area.add(box_outer)

		global device_map

		if port_name != '':
			port_row = device_map[device_type][device_name]['ports'][port_name]
		else:
			port_row = per_port_entry(device_type+":"+device_name, None)

		port_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
		box_outer.add(port_box)
		self.port_entry = Gtk.Entry()
		self.port_entry.set_text(port_name)
		if port_name != '':
			self.port_entry.set_editable(False)
		port_box.pack_start(Gtk.Label(label="Port Name"), False, True, 0)
		port_box.pack_start(self.port_entry, True, True, 0)

		mute_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
		box_outer.add(mute_box)
		self.mute_switch = Gtk.Switch()
		self.mute_switch.set_state(port_row.muted)
		self.muted_valid = Gtk.CheckButton(label="valid")
		self.muted_valid.set_active(port_row.muted_valid)
		mute_box.pack_start(Gtk.Label(label="Muted"), False, True, 0)
		mute_box.pack_start(self.muted_valid, False, True, 0)
		mute_box.pack_start(self.mute_switch, False, True, 0)

		volume = 0.0
		if len(port_row.volume['values']) > 0:
			volume = round(sum(port_row.volume['values'])*100/len(port_row.volume['values']), 2)
		volume_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
		box_outer.add(volume_box)
		self.volume_entry = Gtk.Entry()
		self.volume_entry.set_text(str(volume))
		self.volume_valid = Gtk.CheckButton(label="valid")
		self.volume_valid.set_active(port_row.volume_valid)
		volume_box.pack_start(Gtk.Label(label="Flat Volume"), False, True, 0)
		volume_box.pack_start(self.volume_valid, True, True, 0)
		volume_box.pack_start(self.volume_entry, True, True, 0)

		str_map = [str(element) for element in port_row.channel_map['map']]
		channel_map = ','.join(str_map)
		channel_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
		box_outer.add(channel_box)
		self.channel_entry = Gtk.Entry()
		self.channel_entry.set_text(channel_map)
		channel_box.pack_start(Gtk.Label(label="Channel Map (comma separated)"), False, True, 0)
		channel_box.pack_start(self.channel_entry, True, True, 0)

		action_area= self.get_action_area()
		action_area.set_halign(Gtk.Align.CENTER)
		self.show_all()


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
	def __init__(self, parent, rule_name, dialog_title):
		Gtk.Dialog.__init__(self, title=dialog_title, flags=0)

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

		label = Gtk.Label(label="Pulse Audio Restoration DB Editor", xalign=0.5)
		box_outer.pack_start(label, False, True, 0)

		notebook = Gtk.Notebook()
		box_outer.pack_start(notebook, True, True, 0)

		box_streams = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
		notebook.append_page(box_streams, Gtk.Label(label="Streams Restore Rules"))

		box_devices = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
		notebook.append_page(box_devices, Gtk.Label(label="Device Restore Rules"))

		# Device Restoration

		self.selected_device_label = Gtk.Label(label="", xalign=0.5)
		box_devices.pack_start(self.selected_device_label, False, True, 0)

		paned = Gtk.Paned()
		paned.set_wide_handle(True)
		paned.set_position(240)
		left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
		paned.pack1(left_box, True, False)
		right_pane_scroll = Gtk.ScrolledWindow()
		paned.pack2(right_pane_scroll, True, False)
		box_devices.pack_start(paned, True, True, 10)


		right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
		right_pane_scroll.add(right_box)

		left_box.pack_start(Gtk.Label(label="Sinks", xalign=0), False, True, 0)
		scroll = Gtk.ScrolledWindow()
		self.listbox_sink = Gtk.ListBox()
		self.listbox_sink.set_selection_mode(Gtk.SelectionMode.NONE)
		scroll.add(self.listbox_sink)
		left_box.pack_start(scroll, True, True, 0)

		left_separator = Gtk.Separator()
		left_box.pack_start(left_separator, False, True, 0)

		left_box.pack_start(Gtk.Label(label="Sources", xalign=0), False, True, 0)
		scroll = Gtk.ScrolledWindow()
		self.listbox_source = Gtk.ListBox()
		self.listbox_source.set_selection_mode(Gtk.SelectionMode.NONE)
		scroll.add(self.listbox_source)
		left_box.pack_start(scroll, True, True, 0)

		self.refresh_listbox_sink()
		self.refresh_listbox_source()

		default_port_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
		right_box.pack_start(default_port_box, False, True, 0)
		default_port_box.pack_start(Gtk.Label(label="Default Port", xalign=0.5), False, True, 0)
		self.default_port_entry = Gtk.Entry()
		self.default_port_entry.set_text("")
		default_port_box.pack_start(self.default_port_entry, True, True, 0)
		save_default_port_button = Gtk.Button(label="Save Default Port")
		save_default_port_button.connect("clicked", self.save_default_port_clicked)
		default_port_box.pack_start(save_default_port_button, False, True, 0)

		right_box.pack_start(Gtk.Separator(), False, True, 0)

		right_box.pack_start(Gtk.Label(label="Available Ports", xalign=0.5), False, False, 0)
		scroll = Gtk.ScrolledWindow()
		self.listbox_available_ports = Gtk.ListBox()
		scroll.add(self.listbox_available_ports)
		right_box.pack_start(scroll, True, True, 0)

		device_button_edit_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
		add_new_port_button = Gtk.Button(label="Add New Port")
		add_new_port_button.connect("clicked", self.add_new_port_clicked)
		set_as_default_device_button = Gtk.Button(label="Set As Fallback Device")
		set_as_default_device_button.connect("clicked", self.set_default_device_clicked)
		delete_device_button = Gtk.Button(label="🗑")
		delete_device_button.connect("clicked", self.delete_device_clicked)
		device_button_edit_box.pack_start(add_new_port_button, True, True, 0)
		device_button_edit_box.pack_start(set_as_default_device_button, False, True, 0)
		device_button_edit_box.pack_start(delete_device_button, False, True, 0)
		right_box.pack_start(device_button_edit_box, False, True, 0)

		# Stream Restoration

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
		left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
		left_pane_scroll.add(left_box)
		self.right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
		right_pane_scroll.add(self.right_box)

		add_new_rule_button = Gtk.Button(label="New Routing Rule")
		add_new_rule_button.connect("clicked", self.on_add_new_rule_clicked)
		box_streams.pack_start(add_new_rule_button, False, False, 10)


		left_box.pack_start(Gtk.Label(label="Sink Inputs"), False, True, 0)
		listbox_sink_input = Gtk.ListBox()
		listbox_sink_input.set_selection_mode(Gtk.SelectionMode.NONE)
		left_box.pack_start(listbox_sink_input, True, True, 0)

		left_separator = Gtk.Separator()
		left_box.pack_start(left_separator, False, True, 0)

		left_box.pack_start(Gtk.Label(label="Source Outputs"), False, True, 0)
		listbox_source_output = Gtk.ListBox()
		listbox_source_output.set_selection_mode(Gtk.SelectionMode.NONE)
		left_box.pack_start(listbox_source_output, True, True, 0)


		self.right_listbox = Gtk.ListBox()
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

	def refresh_listbox_sink(self):
		global device_map
		children = self.listbox_sink.get_children()
		for child in children:
			self.listbox_sink.remove(child)

		for name in device_map['sink'].keys():
			if device_map['sink'][name]['is_default_device']:
				self.listbox_sink.add(ListBoxRowWithData(name, "<b>"+name+"</b>"))
			else:
				self.listbox_sink.add(ListBoxRowWithData(name))
		self.listbox_sink.connect("row-activated", self.on_selected_sink)
		self.listbox_sink.show_all()

	def refresh_listbox_source(self):
		global device_map
		children = self.listbox_source.get_children()
		for child in children:
			self.listbox_source.remove(child)

		for name in device_map['source'].keys():
			if device_map['source'][name]['is_default_device']:
				self.listbox_source.add(ListBoxRowWithData(name, "<b>"+name+"</b>"))
			else:
				self.listbox_source.add(ListBoxRowWithData(name))
		self.listbox_source.connect("row-activated", self.on_selected_source)
		self.listbox_source.show_all()

	def on_selected_sink(self, widget, row):
		global device_map
		self.show_selected_device(row.data, device_map['sink'][row.data], 'sink')

	def on_selected_source(self, widget, row):
		global device_map
		self.show_selected_device(row.data, device_map['source'][row.data], 'source')

	def show_selected_device(self, name, device, device_type):
		global currently_selected_device
		global currently_selected_device_type
		currently_selected_device = name
		currently_selected_device_type = device_type
		self.selected_device_label.set_label(name)

		children = self.listbox_available_ports.get_children()
		for child in children:
			self.listbox_available_ports.remove(child)

		if device == None:
			return

		default_port = device['default_port']['port']
		if default_port:
			self.default_port_entry.set_text(default_port)
		else:
			self.default_port_entry.set_text("null")

		ports = device['ports']
		for i in ports.keys():
			device_port_listbox = ListBoxDevicePortInfo(name, device_type, i, ports[i])
			self.listbox_available_ports.add(device_port_listbox)
			device_port_listbox.connect("refresh", self.on_refreshed_device_port_listbox)
		self.listbox_available_ports.show_all()

	def save_default_port_clicked(self, widget):
		global db
		global currently_selected_device
		global currently_selected_device_type
		if currently_selected_device == '':
			return
		new_default_port = self.default_port_entry.get_text()
		if new_default_port == "null":
			new_default_port = None
		current_default_port = device_map[currently_selected_device_type][currently_selected_device]['default_port'].port
		if new_default_port == current_default_port:
			return

		if new_default_port == None:
			device_map[currently_selected_device_type][currently_selected_device]['default_port'].port = None
			device_map[currently_selected_device_type][currently_selected_device]['default_port'].port_valid = False
		else:
			device_map[currently_selected_device_type][currently_selected_device]['default_port'].port = new_default_port
			device_map[currently_selected_device_type][currently_selected_device]['default_port'].port_valid = True

		key_of_default = (currently_selected_device_type+":"+currently_selected_device).encode()
		to_replace = bytes(device_map[currently_selected_device_type][currently_selected_device]['default_port'].encode())
		db.store(key_of_default, to_replace, tdb.REPLACE)

		refresh_device_map()
		self.show_selected_device(
			currently_selected_device,
			device_map[currently_selected_device_type][currently_selected_device],
			currently_selected_device_type)

	def set_default_device_clicked(self, widget):
		global pulse
		global machine_id
		global currently_selected_device
		global currently_selected_device_type
		if currently_selected_device == '' or currently_selected_device == None:
			return
		if currently_selected_device_type == 'sink':
			pulse.sink_default_set(currently_selected_device)
			open(os.environ['HOME']+'/.config/pulse/'+machine_id+'-default-sink','w').write(currently_selected_device)
		else:
			pulse.source_default_set(currently_selected_device)
			open(os.environ['HOME']+'/.config/pulse/'+machine_id+'-default-source','w').write(currently_selected_device)

		refresh_device_map()
		self.refresh_listbox_sink()
		self.refresh_listbox_source()
		self.show_selected_device(
			currently_selected_device,
			device_map[currently_selected_device_type][currently_selected_device],
			currently_selected_device_type)

	def delete_device_clicked(self, widget):
		global db
		global device_map
		global currently_selected_device
		global currently_selected_device_type
		full_device_name = currently_selected_device_type+":"+currently_selected_device
		dialog = DialogConfirmDeleteRule(self, full_device_name, "Device Rule Deletion")
		response = dialog.run()

		if response == Gtk.ResponseType.OK:
			# for the default port rule
			db.delete(full_device_name.encode())
			# for individual ports
			for port in device_map[currently_selected_device_type][currently_selected_device]['ports'].keys():
				db.delete((full_device_name+":"+port).encode())
			refresh_device_map()
			self.refresh_listbox_sink()
			self.refresh_listbox_source()
			self.show_selected_device("", None, "")

		dialog.destroy()

	def add_new_port_clicked(self, widget):
		global db
		global device_map
		global currently_selected_device
		global currently_selected_device_type
		if currently_selected_device == '':
			return
		full_device_name = currently_selected_device_type+":"+currently_selected_device

		dialog = DialogPortEditRule(self, currently_selected_device_type, currently_selected_device, '')
		response = dialog.run()
		if response == Gtk.ResponseType.OK:
			channel_map_str = dialog.channel_entry.get_text().rstrip()
			channel_map = []
			if channel_map_str != '':
				channel_map = [int(element) for element in channel_map_str.split(',')]

			new_port_name = dialog.port_entry.get_text()
			port_row = per_port_entry(full_device_name+":"+new_port_name, None)

			port_row.muted_valid = dialog.muted_valid.get_active()
			port_row.muted = dialog.mute_switch.get_state()
			port_row.volume_valid = dialog.volume_valid.get_active()
			port_row.volume['channels'] = len(channel_map)
			port_row.channel_map['channels'] = port_row.volume['channels']
			port_row.channel_map['map'] = channel_map
			vol = float(dialog.volume_entry.get_text())/100.0
			port_row.volume['values'] = [vol for i in range(port_row.volume['channels'])]

			key_of_entry = (full_device_name+":"+new_port_name).encode()
			to_replace = bytes(port_row.encode())
			db.store(key_of_entry, to_replace, tdb.REPLACE)
			self.on_refreshed_device_port_listbox(None)

		dialog.destroy()


	def on_refreshed_device_port_listbox(self, listbox_widget):
		global currently_selected_device
		global currently_selected_device_type
		refresh_device_map()
		self.refresh_listbox_sink()
		self.refresh_listbox_source()
		self.show_selected_device(
			currently_selected_device,
			device_map[currently_selected_device_type][currently_selected_device],
			currently_selected_device_type)



win = RestoreDbUI()
win.connect("destroy", Gtk.main_quit)
win.show_all()
Gtk.main()

