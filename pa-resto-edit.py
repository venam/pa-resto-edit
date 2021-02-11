#!/usr/bin/python
import pulsectl
import tdb
import os
import gi
from ctypes import *
gi.require_version("Gtk", "3.0")
#import gobject
from gi.repository import Gtk, GObject

pulse = pulsectl.Pulse('restore_manip')
currently_selected_map = ''
restore_map = {}

# TODO: this covers the stream maps, not the devices volume restoration information.
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
# https://stackoverflow.com/questions/17244488/reading-struct-in-python-from-created-struct-in-c#17246128
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
#db_keys = list(db.keys())
# Example
#PA_CHANNELS_MAX = 32
#
#class PA_CHANNEL_MAP(Structure):
#	_fields_ = [
#		('channels', c_uint8),
#		('map', c_int * PA_CHANNELS_MAX)
#	]
#
#class PA_CVOLUME(Structure):
#	_fields_ = [
#		('channels', c_uint8),
#		('values', c_uint32 * PA_CHANNELS_MAX)
#	]
#
#class PA_PER_PORT_ENTRY(Structure):
#	_fields_ = [
#		('version', c_uint8),
#		('volume_valid', c_int),
#		('channel_map', PA_CHANNEL_MAP),
#		('volume', PA_CVOLUME),
#		('muted_valid', c_int),
#		('muted', c_int),
#		('number_of_formats', c_uint8),
#		# TODO https://gitlab.freedesktop.org/pulseaudio/pulseaudio/-/blob/master/src/pulsecore/tagstruct.c#L337
#	]

def refresh_restore_map():
	global pulse
	global restore_map
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

# TODO test data remove
#a = pulsectl.PulseExtStreamRestoreInfo(struct_or_name="sink-input-by-application-name:Firefox",volume=50.0, device="media")
#a = restore_db[19]
# a.volume = pulsectl.PulseVolumeInfo(struct_or_values=[0.50,0.50], channels=2)
#pulse.stream_restore_write(a, mode='replace')


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

		# TODO do we include channel_map and mute
		label_volume = Gtk.Label(label=str(round(restoration_row.volume.value_flat * 100, 2))+"%", xalign=0)
		scroll = Gtk.ScrolledWindow(expand=True)
		scroll.add(label_volume)
		grid.attach(scroll, 1, 0, 1, 1)

		label_device = Gtk.Label(label=str(restoration_row.device), xalign=0)
		scroll = Gtk.ScrolledWindow(expand=True)
		scroll.add(label_device)
		grid.attach(scroll, 2, 0, 1, 1)

		edit_button = Gtk.Button(label="🖊")
		edit_button.connect("clicked", self.on_edit_clicked)
		grid.attach(edit_button, 3, 0, 1, 1)

		delete_button = Gtk.Button(label="🗑")
		delete_button.connect("clicked", self.on_delete_clicked)
		grid.attach(delete_button, 4, 0, 1, 1)

		self.add(grid)

	def on_edit_clicked(self, widget):
		global currently_selected_map
		global pulse
		rule_name = currently_selected_map+":"+self.restoration_name

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

# TODO have a window to fill the new routing information
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

# TODO have a window to fill the new routing information
class DialogNewRoutingRule(Gtk.Dialog):
	def __init__(self, parent):
		Gtk.Dialog.__init__(self, title="New Routing Rule", transient_for=parent, flags=0)
		self.add_buttons(
			Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK
		)
		self.set_default_size(150, 100)
		label = Gtk.Label(label="Enter the information about the new routing rule")
		box = self.get_content_area()
		box.add(label)
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

		self.currently_select_map_label = Gtk.Label(label="", xalign=0.5)
		box_outer.pack_start(self.currently_select_map_label, False, True, 0)

		paned = Gtk.Paned()
		paned.set_wide_handle(True)
		paned.set_position(240)
		left_pane_scroll = Gtk.ScrolledWindow()
		paned.pack1(left_pane_scroll, True, False)

		right_pane_scroll = Gtk.ScrolledWindow()
		paned.pack2(right_pane_scroll, True, False)

		box_outer.pack_start(paned, True, True, 10)

		add_new_rule_button = Gtk.Button(label="New Routing Rule")
		add_new_rule_button.connect("clicked", self.on_add_new_rule_clicked)
		box_outer.pack_start(add_new_rule_button, False, False, 10)

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
			print("The OK button was clicked")
		elif response == Gtk.ResponseType.CANCEL:
			print("The Cancel button was clicked")

		dialog.destroy()

win = RestoreDbUI()
win.connect("destroy", Gtk.main_quit)
win.show_all()
Gtk.main()

