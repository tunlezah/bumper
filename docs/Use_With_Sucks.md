# Using Bumper with Sucks

**Note:** Sucks is no longer developed. Its own package description calls it "an abandoned library", and its last release (0.9.6) dates from May 2020, so it may need an older Python than Bumper does. Install it in its own environment. It has not been tested against this version of Bumper.

You'll need to use the bmartin5692 fork of sucks.  Especially if you have a newer bot like an Ozmo.

- Download and install [Sucks](https://github.com/bmartin5692/sucks)

- You can use Sucks CLI to control the bots

**Note:** When performing the login command you'll either want to set `verify_ssl` to `False` or provide the full path to your Bumper CA certificate (`certs/ca.crt`).

OR

- You can use Sucks as a library from your own script, for details see the [sucks project](https://github.com/wpietri/sucks)

```python
#!/usr/bin/env python3

from sucks import *


class BumperVacBot(VacBot):
    def __init__(self, server_address):
        self.server_address = server_address
        vacuum = {"did": "none", "class": "none"}
        super().__init__("sucks", "ecouser.net", "", "", vacuum, "")

    def connect_and_wait_until_ready(self):
        logging.info("connecting")
        self.xmpp.connect(self.server_address)
        self.xmpp.process()
        self.xmpp.wait_until_ready()


logging.basicConfig(level=logging.DEBUG, format="%(levelname)-8s %(message)s")
server_address = ("xxx.xxx.xxx.xxx", 5223)

# Initialize
vacbot = BumperVacBot(server_address)

# Connect
vacbot.connect_and_wait_until_ready()

# Send a command
vacbot.run(Clean())

```
