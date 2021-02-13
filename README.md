# PulseAudio Restoration DB Editor


An interface to easily edit the restoration/routing rules of PulseAudio.

![GUI](https://github.com/venam/pa-resto-edit/raw/master/assets/gui.png)

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

