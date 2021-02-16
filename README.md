# PulseAudio Restoration DB Editor


An interface to easily edit the restoration/routing rules of PulseAudio.

![GUI](https://github.com/venam/pa-resto-edit/raw/master/assets/gui.png)

- [x] `module-stream-restore` (using core api)
- [ ] `module-device-restore` (using tdb - WIP)
- [ ] `module-default-device-restore` (simple files - WIP - can be done
  through other tools)
- [ ] `module-card-restore` (not covered)
- [ ] `module-device-manager` (not covered - isn't used by most distros)

The restoration process works as follows:

![stream](https://colin.guthr.ie/wp-content/uploads/2010/02/pa-initial-route.png)
![device](https://colin.guthr.ie/wp-content/uploads/2010/02/pa-new-device-route.png)

To know the values that will be used to route you can use `pacmd` to
inspect the sinks/sources, and clients.  
Example of properties:

```
pacmd list-clients
   properties:
      application.name = "application name"
      native-protocol.peer = "UNIX socket client"
      native-protocol.version = "34"
      application.icon_name = "application name"
      application.process.id = "99647"
      application.process.user = "username"
      application.process.host = "identity"
      application.process.binary = "application name"
      application.language = "en_US.UTF-8"
      window.x11.display = ":0"
      application.process.machine_id = "2e1f6f08abbe4c8293e832ead34de3ad"
      application.process.session_id = "3"
```

-----

Relies on [pulsectl](https://pypi.org/project/pulsectl/) and
[tdb](https://pypi.org/project/tdb/) libraries.

-----

Additional information:

- A sink is an output device (ex: speaker)
- A sink-input is the stream going towards an output device
- A source is an input device (ex: microphone)
- A source-output is the stream that comes out of the input device
- A sink-monitor is a source automatically created with a sink so that you
  can record it
- A profile is a state of function for a device (ex: output stereo,
  input mono)
- A client is an application that generates or consume a stream
- Properties can be attached on streams and devices. These can be used
  for restoration: automatically attaching streams to devices, setting
  volume, channel map, mute, on devices when connected

