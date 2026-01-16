from smartcard.System import readers
from smartcard.util import toHexString

def read_nfc_uid():
    r = readers()
    if not r:
        return None

    reader = r[0]
    connection = reader.createConnection()
    connection.connect()

    GET_UID = [0xFF, 0xCA, 0x00, 0x00, 0x00]
    data, sw1, sw2 = connection.transmit(GET_UID)

    if sw1 == 0x90:
        return toHexString(data).replace(" ", "")
    return None
