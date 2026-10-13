"""The addresses under which other devices in the network reach the admin interface."""

import socket


def lan_addresses():
    """The machine's LAN IPv4 address (from the default route) and its .local name, if any."""
    addresses = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            # connect() on UDP sends nothing; it only picks the outgoing interface.
            probe.connect(("192.0.2.1", 9))
            address = probe.getsockname()[0]
            if not address.startswith("127."):
                addresses.append(address)
    except OSError:
        pass
    hostname = socket.gethostname()
    if hostname and hostname != "localhost":
        # Raspberry Pi OS announces <hostname>.local via Avahi.
        addresses.append(f"{hostname}.local")
    return addresses
