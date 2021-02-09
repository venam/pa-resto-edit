import pulsectl
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk


pulse = pulsectl.Pulse('restore_manip')
restore_db = pulse.stream_restore_read()

restore_map = {
	'source-output-by-media-role': {},
	'source-output-by-application-name': {},
	'source-output-by-application-id': {},
	'source-output-by-media-name': {},
	'sink-input-by-media-role': {},
	'sink-input-by-application-name': {},
	'sink-input-by-application-id': {},
	'sink-input-by-media-name': {},
}

for a in range(len(restore_db)):
	assocition_type = restore_db[a].name.split(":")[0]
	name = "".join(restore_db[a].name.split(":")[1:])
	restore_map[assocition_type][name] = restore_db[a]

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

# TODO add all the information about this specific StreamRestoreInfo
# (name,volume,device) along with an edit and delete button on the right (with
# confirmation
class ListBoxRestorationInfo(Gtk.ListBoxRow):
	def __init__(self, restoration_name, restoration_row):
		super(Gtk.ListBoxRow, self).__init__()
		self.restoration_name = restoration_name
		self.add(Gtk.Label(label=restoration_name, xalign=0))

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
		self.show_all()

class RestoreDbUI(Gtk.Window):
	def __init__(self):
		Gtk.Window.__init__(self, title="PulseAudio Restoration DB Editor")
		self.set_default_size(700,400)

		box_outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
		self.add(box_outer)

		box_outer.pack_start(Gtk.Label(label="Pulse Audio Restoration DB Editor", xalign=0.5), False, True, 0)

		paned = Gtk.Paned()
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

		for key in restore_map[row.data]:
			self.right_listbox.add(ListBoxRestorationInfo(str(key), restore_map[row.data][key]))

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

