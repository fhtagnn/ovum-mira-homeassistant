from modbus_connection.model import NumberField


def ovum_boolean(address: int, *, stride: int = 0) -> NumberField[bool]:
    """Map OVUM's documented boolean semantics: zero is false, anything else true."""
    return NumberField(
        address,
        count=1,
        signed=False,
        convert=bool,
        stride=stride,
    )
